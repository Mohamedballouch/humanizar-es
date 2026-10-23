#!/usr/bin/env python3
"""Rewrite with a local BASE model (HIP), no API and no GPU.

Detectors mostly recognize the fingerprint of chat training: text from a base model
(without that training) looks human to them. HIP is Qwen3-4B-Base with a LoRA
adapter trained to paraphrase back toward human prose (Xu et al., 2026, «Base
Models Look Human To AI Detectors», arXiv:2605.19516; MIT code, Apache-2.0 adapter).

It was trained in English: left alone it translates Spanish into English. That is
why each paragraph starts with its first two original words, so the model keeps
writing in the language of the original.

A single pass per paragraph: with more passes the text drifts from the meaning. If
a paragraph loses a concept from --concepts or comes out truncated, it is retried;
if nothing works, the original is kept and a warning names the concept it kept losing.
HIP sometimes copies long stretches of the original word for word; a try that copies
more than --max-copied of its words in runs of 8+ words is retried too, and if every
try copies that much, the least copied one is kept and a warning is printed.

Runs on CPU (-ngl 0) at low priority. About 30 s per paragraph on an M4 Mac.
Install first: python3 scripts/install_model.py  (about 4.6 GB in ~/.cache/humanizar-es/hip)

usage:
  python3 scripts/rewrite.py original.txt -o rewritten.txt --concepts concepts.txt
  python3 scripts/join.py rewritten.txt -o final.txt --concepts concepts.txt
"""
import argparse
import collections
import difflib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check  # noqa: E402
import join  # noqa: E402
import tells  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # so a Windows console does not choke on «» or ñ
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")

BASE = "Qwen3-4B-Base.Q8_0.gguf"
ADAPTER = "hip-qwen3-4b-base.gguf"
MODEL_FILES = (BASE, ADAPTER)


def _has_model(directory):
    return all(os.path.isfile(os.path.join(directory, f)) for f in MODEL_FILES)


def resolve_model_dir(environ=None, home=None):
    """Where the model lives: $HUMANIZE_MODEL_DIR (or the old $HUMANIZAR_HIP_DIR), else
    ~/.cache/humanizar-es/hip, the folder every version has used, so nobody downloads
    4.6 GB again."""
    environ = os.environ if environ is None else environ
    custom = environ.get("HUMANIZE_MODEL_DIR") or environ.get("HUMANIZAR_HIP_DIR")
    if custom:
        return custom
    return os.path.join(home or os.path.expanduser("~"), ".cache", "humanizar-es", "hip")


MODEL_DIR = resolve_model_dir()


def build_prompt(paragraph, lead_words=2, lead=None, lang=None):
    """The format HIP was trained on, plus the first words of the paragraph so the
    model keeps writing in the language of the original. `lead` replaces those words:
    the original's own opening («Uno de los problemas más importantes…») ties the model
    to the stock sentence a detector flags; another opening («Desde la») frees it.
    In English, a paragraph that opens with a filler («Moreover, the…») leads with the
    words after it: HIP needs no lead to stay in English, and the filler is a tell."""
    if not lead:
        words = paragraph.split()
        filler = next((f for f in join.FILLERS.get(lang, ()) if paragraph.startswith(f)), None)
        if filler and len(words) > len(filler.split()) + lead_words:
            words = words[len(filler.split()):]
            if not join.keeps_capital(words[0], ()):
                words[0] = words[0][0].upper() + words[0][1:]
        lead = " ".join(words[:lead_words])
    prompt = f"<source_text>\n{paragraph.strip()}\n</source_text>\n\n<target_text>\n{lead}"
    return prompt, lead


def clean_output(lead, generated):
    text = (lead + generated).split("</target_text>")[0]
    return " ".join(text.split())


HOW_TO_INSTALL_LLAMA = ("On macOS or Linux: brew install llama.cpp. On Windows: winget install "
                        "llama.cpp and open a new terminal. If it is already installed in another "
                        "folder, put its path in the HUMANIZE_LLAMA variable.")


def llama_binary():
    """llama-completion (or llama-cli, in old versions). Looks in HUMANIZE_LLAMA (or the old
    HUMANIZAR_LLAMA), in the PATH and, on Windows, in the winget folder, which does not
    reach the PATH until another terminal is opened."""
    custom = os.environ.get("HUMANIZE_LLAMA") or os.environ.get("HUMANIZAR_LLAMA")
    if custom:
        return custom if os.path.isfile(custom) else None
    paths = [None]
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        paths.append(os.path.join(local, "Microsoft", "WinGet", "Links"))
    for path in paths:
        for b in ("llama-completion", "llama-cli"):
            found = shutil.which(b, path=path)
            if found:
                return found
    return None


class LlamaError(RuntimeError):
    """llama.cpp exited with an error: a setup problem, not a bad paragraph."""


def context_size(paragraph, generated):
    """Tokens of context for the prompt plus the output, with room to spare. A fixed 4096
    overflows on paragraphs of ~700+ words; Qwen3-4B takes 32k."""
    need = 2 * len(paragraph.split()) + generated + 256
    return max(4096, -(-need // 1024) * 1024)


def rewrite_paragraph(paragraph, threads=4, temperature=1.0, lead=None, lang=None):
    prompt, lead = build_prompt(paragraph, lead=lead, lang=lang)
    # The prompt goes in a UTF-8 file and not on the command line: on Windows accents
    # and quotes get mangled when passed as an argument.
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as fh:
        fh.write(prompt)
    try:
        return clean_output(lead, _run_llama(fh.name, paragraph, threads, temperature))
    finally:
        os.remove(fh.name)


def _run_llama(prompt_file, paragraph, threads, temperature):
    llama = llama_binary()
    generated = int(len(paragraph.split()) * 3) + 100
    cmd = [llama, "-m", os.path.join(MODEL_DIR, BASE),
           "--lora", os.path.join(MODEL_DIR, ADAPTER),
           "-ngl", "0", "-dev", "none", "-t", str(threads),
           "-c", str(context_size(paragraph, generated)), "-n", str(generated),
           "--temp", str(temperature), "--top-p", "0.95",
           "-no-cnv", "--no-display-prompt", "-r", "</target_text>", "-f", prompt_file]
    if llama.endswith(".py"):  # a fake llama, for the tests
        cmd = [sys.executable] + cmd
    extra = {}
    if os.name == "nt":  # low priority, like nice on macOS and Linux
        extra["creationflags"] = subprocess.BELOW_NORMAL_PRIORITY_CLASS
    elif shutil.which("nice"):
        cmd = ["nice", "-n", "15"] + cmd
    # llama.cpp writes UTF-8; without an encoding, Windows would read it as cp1252.
    r = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace",
                       stdin=subprocess.DEVNULL, **extra)
    # A failing llama.cpp used to look like a «truncated» try, six times per paragraph. Output
    # with a bad exit code is still used: some builds crash on exit after generating.
    if r.returncode != 0 and not r.stdout.strip():
        tail = "\n".join((r.stderr or "").strip().splitlines()[-6:])
        raise LlamaError(f"llama.cpp exited with code {r.returncode}:\n{tail}")
    return r.stdout


def restore_percent_signs(original, rewritten):
    """The HIP adapter eats the % sign: «60%» comes out as «60». If the original had
    that number with %, it is given back. Numbers the original did not have with %
    are left alone."""
    for n in set(re.findall(r"(\d+(?:[.,]\d+)?)\s?%", original)):
        if not re.search(rf"(?<![\d.,]){re.escape(n)}\s?%", rewritten):
            rewritten = re.sub(rf"(?<![\d.,]){re.escape(n)}(?![\d.,]*\d)(?!\s?%)",
                               n + "%", rewritten, count=1)
    return rewritten


def concepts_in(text, concepts):
    t = check.norm(text)
    return {n for n, variants in concepts if any(check.pattern(v).search(t) for v in variants)}


COPY_RUN = 8  # words in a row that count as copied, not as a shared phrase or a name


def copied_share(original, rewritten, run=COPY_RUN):
    """Share of the rewritten words that sit in runs of `run`+ words copied from the
    original. Calibrated on four essays: HIP's real rewrites copy 0.12-0.45; a paragraph
    it left half untouched, 0.80."""
    a = re.findall(r"\w+", original.lower())
    b = re.findall(r"\w+", rewritten.lower())
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return sum(m.size for m in sm.get_matching_blocks() if m.size >= run) / max(1, len(b))


QUOTE = re.compile(r'["“«]([^"”»]{12,})["”»]')
PARENTHESES = re.compile(r"\(([^()]*)\)")
ROMAN = re.compile(r"c{0,3}(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})", re.I)


def references(text):
    """What is in brackets and looks like a reference: a number, or a roman numeral
    («III», «cap. vi»; a lone «i» only next to a comma, as in «libro i,»). Words made of
    those letters, like «(civil)» or «(I think)», are not numerals."""
    found = []
    for inner in PARENTHESES.findall(text):
        words = re.findall(r"\w+", inner)
        if any(w.isdigit() or (ROMAN.fullmatch(w) and (len(w) > 1 or "," in inner))
               for w in words):
            found.append(inner)
    return found


def citation_problem(original, rewritten):
    """A quotation of the original that is no longer verbatim, or a reference in
    brackets the original never had («(De Anima, libro i, cap. vi)»). HIP did both on a
    test essay; a changed quote or an invented source is worse than any detector score."""
    norm = lambda s: " ".join(s.lower().split()).strip(" .,;:")  # noqa: E731
    have = norm(rewritten)
    for q in QUOTE.findall(original):
        if norm(q) not in have:
            return "(quote changed)"
    known = {norm(r) for r in references(original)}
    for r in references(rewritten):
        if norm(r) not in known:
            return "(invented reference)"
    return None


def acceptable(p, r, wanted, concepts, max_copied, max_tells=None, lang="en"):
    """(problem, copied share) for one try: problem is None when the try can be used.
    With max_tells, a try that scores more than that in tells.py is «(AI tells)»."""
    if len(r.split()) < 0.6 * len(p.split()) or len(r.split()) > 1.6 * len(p.split()) + 10:
        return "(truncated or too long)", 0.0
    missing = wanted - concepts_in(r, concepts)
    if missing:
        return sorted(missing)[0], 0.0
    problem = citation_problem(p, r)
    if problem:
        return problem, 0.0
    share = copied_share(p, r)
    if share > max_copied:
        return "(copied)", share
    if max_tells is not None and tells.score(r, lang) > max_tells:
        return "(AI tells)", share
    return None, share


is_title = tells.is_title


def main():
    ap = argparse.ArgumentParser(description="Rewrite with a local base model (HIP), paragraph by paragraph.")
    ap.add_argument("original")
    ap.add_argument("-o", "--output", "--salida", dest="output", required=True)
    ap.add_argument("--concepts", "--conceptos", dest="concepts",
                    help="file of concepts that must not be lost")
    ap.add_argument("--tries", "--intentos", dest="tries", type=int, default=6,
                    help="tries per paragraph (6); only a paragraph that fails uses more than one")
    ap.add_argument("--max-copied", dest="max_copied", type=float, default=0.6,
                    help="retry a try that copies more than this share of the original (0.6)")
    ap.add_argument("--threads", "--hilos", dest="threads", type=int, default=4,
                    help="CPU threads (4)")
    ap.add_argument("--only", help="redo only these paragraphs (e.g. 7,11) of an existing output, "
                    "from the original, keeping the others and their hand fixes")
    ap.add_argument("--lead", help="opening words for the rewritten paragraphs instead of the "
                    "original's first two (e.g. \"Desde la\"); use it with --only")
    ap.add_argument("--temperature", type=float, default=1.0,
                    help="sampling temperature (1.0); 1.1-1.2 gives more varied candidates")
    ap.add_argument("--candidates", type=int, metavar="N",
                    help="with --only: write N acceptable versions of each paragraph to "
                    "<output>.candidates/ instead of changing the output")
    ap.add_argument("--take", metavar="N=FILE",
                    help="put the text of FILE in paragraph N of the output (no model needed)")
    ap.add_argument("--max-tells", dest="max_tells", type=int, metavar="N",
                    help="retry a try that scores more than N in scripts/tells.py; if every try "
                    "does, the one with the fewest tells is kept")
    args = ap.parse_args()

    if args.take:
        return take(args.original, args.output, args.take)
    for flag, value in (("--candidates", args.candidates), ("--lead", args.lead)):
        if value and not args.only:
            print(f"ERROR: {flag} needs --only (which paragraphs)", file=sys.stderr)
            return 2

    if not llama_binary():
        print("ERROR: llama.cpp is missing. " + HOW_TO_INSTALL_LLAMA, file=sys.stderr)
        return 2
    for f in MODEL_FILES:
        if not os.path.isfile(os.path.join(MODEL_DIR, f)):
            print(f"ERROR: {f} is missing in {MODEL_DIR}; run scripts/install_model.py",
                  file=sys.stderr)
            return 2

    with open(args.original, encoding="utf-8") as fh:
        text = fh.read()
    concepts = check.load_concepts(args.concepts) if args.concepts else []
    paragraphs = [x.strip() for x in re.split(r"\n\s*\n", text) if x.strip()]
    lang = join.detect_language(text)
    kept, only = None, None
    if args.only:
        only = parse_only(args.only, len(paragraphs))
        if only is None:
            return 2
        if not os.path.isfile(args.output):
            print(f"ERROR: --only needs the existing {args.output}", file=sys.stderr)
            return 2
        with open(args.output, encoding="utf-8") as fh:
            kept = [x.strip() for x in re.split(r"\n\s*\n", fh.read()) if x.strip()]
        if len(kept) != len(paragraphs):
            print(f"ERROR: {args.output} has {len(kept)} paragraphs and the original "
                  f"{len(paragraphs)}; --only needs the same count", file=sys.stderr)
            return 2
    try:
        return run_paragraphs(args, paragraphs, kept, only, concepts, lang)
    except LlamaError as e:
        print(f"ERROR: {e}\nThe paragraphs finished before it are saved in {args.output}. "
              "Check that llama.cpp runs: " + HOW_TO_INSTALL_LLAMA, file=sys.stderr)
        return 2


def parse_only(spec, count):
    """{paragraph numbers} from «7,11», or None after printing why it is wrong."""
    try:
        only = {int(n) for n in spec.split(",") if n.strip()}
    except ValueError:
        print(f"ERROR: --only takes paragraph numbers separated by commas, like 7,11; got {spec}",
              file=sys.stderr)
        return None
    wrong = sorted(n for n in only if not 1 <= n <= count)
    if wrong or not only:
        print(f"ERROR: --only {spec}: the original has {count} paragraphs (1 to {count})",
              file=sys.stderr)
        return None
    return only


def run_paragraphs(args, paragraphs, kept, only, concepts, lang):
    output, untouched, copied, tellish, t0 = [], [], [], [], time.time()
    for i, p in enumerate(paragraphs, 1):
        if kept is not None and i not in only:
            output.append(kept[i - 1])
            continue
        if is_title(p):
            output.append(p)
            continue
        wanted = concepts_in(p, concepts)
        if args.candidates:
            write_candidates(args, i, p, wanted, concepts, lang)
            output.append(kept[i - 1])
            continue
        chosen, mostly_copied, with_tells, lost = None, [], [], collections.Counter()
        for n in range(1, args.tries + 1):
            r = restore_percent_signs(p, rewrite_paragraph(p, args.threads, args.temperature,
                                                           args.lead, lang))
            problem, share = acceptable(p, r, wanted, concepts, args.max_copied,
                                        args.max_tells, lang)
            if problem == "(copied)":
                mostly_copied.append((share, r))
                continue
            if problem == "(AI tells)":
                with_tells.append((tells.score(r, lang), r))
                continue
            if problem:
                lost[problem] += 1
                continue
            chosen = r
            break
        fallback = ""
        if chosen is None and with_tells:  # faithful and not copied: better than the rest
            score, chosen = min(with_tells, key=lambda c: c[0])
            tellish.append(f"{i} (score {score})")
            fallback = "fewest tells of "
        if chosen is None and mostly_copied:
            share, chosen = min(mostly_copied, key=lambda c: c[0])
            copied.append(f"{i} ({share:.0%})")
            fallback = "least copied of "
        if chosen is None:
            untouched.append(f"{i} (" + ", ".join(c for c, _ in lost.most_common(2)) + ")")
            chosen = p
        output.append(chosen)
        with open(args.output, "w", encoding="utf-8") as fh:  # saves after every paragraph
            fh.write("\n\n".join(output + (kept or paragraphs)[i:]) + "\n")
        status = ("unchanged" if chosen == p else f"done, {fallback}{n} tries" if fallback
                  else f"done, try {n}" if n > 1 else "done")
        print(f"Paragraph {i} of {len(paragraphs)}: {status} ({time.time() - t0:.0f} s)", flush=True)

    if args.candidates:
        print(f"\nCandidates in {args.output}.candidates/ — the output was not changed. Measure them\n"
              "joined and inside the whole text, then adopt one with --take N=FILE.")
        return 0
    print(f"\nWritten: {args.output}")
    if untouched:
        print("WARNING: kept as the original, the concept they kept losing in brackets: "
              + "; ".join(untouched) + ". Check the spelling of that concept in the concepts file.")
    if copied:
        print("WARNING: every try copied long stretches of the original; the least copied one "
              "was kept: " + "; ".join(copied) + ". Redo them with --only and more --tries.")
    if tellish:
        print("WARNING: every try kept AI tells above --max-tells; the one with the fewest was "
              "kept: " + "; ".join(tellish) + ".")
    strong = [(n, tells.find(x, lang)) for n, x in enumerate(output, 1)
              if (only is None or n in only) and not is_title(x)]
    strong = [(n, h) for n, h in strong if sum(w for _, w, _ in h) >= tells.STRONG]
    if strong:
        print("AI tells left (scripts/tells.py shows them all; regenerate, don't fix by hand): "
              + "; ".join(f"{n} ({tells.summary(h)})" for n, h in strong))
    print("Next step: reread against the original and fix by hand what changed (HIP\n"
          "sometimes changes a detail, like «they clean» into «they wash the dishes»);\n"
          "then scripts/join.py.")
    return 0


def write_candidates(args, i, p, wanted, concepts, lang="en"):
    """Up to N acceptable versions of paragraph i, each in its own file. A detector can
    score two samples of the same paragraph 0% and 100%; measuring several and keeping the
    one that passes adds no chat fingerprint, since the same base model wrote them all."""
    folder = args.output + ".candidates"
    os.makedirs(folder, exist_ok=True)
    found, tries, written = 0, 0, []
    while found < args.candidates and tries < args.candidates * args.tries:
        tries += 1
        r = restore_percent_signs(p, rewrite_paragraph(p, args.threads, args.temperature,
                                                       args.lead, lang))
        problem, share = acceptable(p, r, wanted, concepts, args.max_copied, args.max_tells, lang)
        if problem:
            continue
        found += 1
        path = os.path.join(folder, f"p{i:02d}-{found}.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(r + "\n")
        hits = tells.find(r, lang)
        score = sum(w for _, w, _ in hits)
        written.append((score, path))
        print(f"Paragraph {i}: {path} (copied {share:.0%}, tells {score}"
              + (f": {tells.summary(hits)}" if hits else "") + ")", flush=True)
    if found < args.candidates:
        print(f"Paragraph {i}: only {found} acceptable of {tries} tries", flush=True)
    if len(written) > 1:
        print(f"Paragraph {i}, fewest tells first (read them all against the original; "
              "measure before adopting): " + ", ".join(
                  f"{os.path.basename(path)} ({score})" for score, path in sorted(written)),
              flush=True)


def take(original, output, spec):
    """Paragraph N of the output becomes the text of FILE; everything else stays."""
    n, _, path = spec.partition("=")
    if not n.isdigit() or not os.path.isfile(path):
        print("ERROR: --take needs N=FILE with an existing FILE", file=sys.stderr)
        return 2
    with open(output, encoding="utf-8") as fh:
        paragraphs = [x.strip() for x in re.split(r"\n\s*\n", fh.read()) if x.strip()]
    with open(original, encoding="utf-8") as fh:
        count = len([x for x in re.split(r"\n\s*\n", fh.read()) if x.strip()])
    if count != len(paragraphs):
        print(f"ERROR: {output} has {len(paragraphs)} paragraphs and the original {count}; "
              "--take needs the same count", file=sys.stderr)
        return 2
    if not 1 <= int(n) <= len(paragraphs):
        print(f"ERROR: {output} has {len(paragraphs)} paragraphs", file=sys.stderr)
        return 2
    with open(path, encoding="utf-8") as fh:
        paragraphs[int(n) - 1] = " ".join(fh.read().split())
    with open(output, "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(paragraphs) + "\n")
    print(f"Paragraph {n} of {output} now comes from {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

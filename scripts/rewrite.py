#!/usr/bin/env python3
"""Rewrite with a local BASE model (HIP), no API; on the CPU unless HUMANIZE_GPU is set.

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
try copies that much, the least copied one is kept and a warning is printed. A try
that drops a figure of the original (a year, an amount) is retried; if all do, the one
missing the fewest is kept and the warning names the figure to put back (a one-word fix).
A try that adds a figure the original never had, or changes one («0.50» -> «0.5», «1.5»
-> «15»), is never used.
A try that changes a URL, a link or `inline code` is never used.

Markdown is respected: code, tables, headings, quotations and HTML are kept as they are,
and a list is rewritten item by item, keeping its markers (scripts/blocks.py).

A LaTeX paper (.tex) is rewritten paragraph by paragraph too: the preamble, sections,
equations, figures, tables, theorems, comments and bibliography are kept byte for byte,
and inside a paragraph the model sees placeholders for math, citations, references and
every other command (scripts/latex.py). A try that loses, repeats or adds a placeholder is
not used, so $\\beta$, \\cite{…} or \\ref{…} cannot change.

Runs on CPU (-ngl 0) at low priority. About 30 s per paragraph on an M4 Mac, 1-3 min on
an older PC. HUMANIZE_GPU=1 puts the model on the GPU (a llama.cpp built for it, ~5 GB of
free GPU memory); HUMANIZE_GPU=20 puts only 20 of its 36 layers there.
Install first: python3 scripts/install_model.py  (about 4.6 GB in ~/.cache/humanizar-es/hip)

usage:
  python3 scripts/rewrite.py original.txt -o rewritten.txt --concepts concepts.txt
  python3 scripts/tells.py original.txt rewritten.txt
  python3 scripts/join.py rewritten.txt -o final.txt --concepts concepts.txt --pauses 2
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
import blocks  # noqa: E402
import check  # noqa: E402
import join  # noqa: E402
import latex  # noqa: E402
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
    ~/.cache/humanizar-es/hip, the folder every version has used (the skill's name until
    3.4), so nobody downloads
    4.6 GB again."""
    environ = os.environ if environ is None else environ
    custom = environ.get("HUMANIZE_MODEL_DIR") or environ.get("HUMANIZAR_HIP_DIR")
    if custom:
        return custom
    return os.path.join(home or os.path.expanduser("~"), ".cache", "humanizar-es", "hip")


MODEL_DIR = resolve_model_dir()


def base_model_path(environ=None):
    """The base model: $HUMANIZE_BASE_MODEL, a GGUF of Qwen3-4B-Base the user already has (any
    quantization: the HIP adapter fits them all), or Qwen3-4B-Base.Q8_0.gguf in MODEL_DIR."""
    environ = os.environ if environ is None else environ
    return environ.get("HUMANIZE_BASE_MODEL") or os.path.join(MODEL_DIR, BASE)


def adapter_path(environ=None):
    """The HIP adapter: $HUMANIZE_ADAPTER, an adapter in GGUF for a bigger base model (it must
    be the one trained for that model: Qwen3-8B-Base, say), or hip-qwen3-4b-base.gguf."""
    environ = os.environ if environ is None else environ
    return environ.get("HUMANIZE_ADAPTER") or os.path.join(MODEL_DIR, ADAPTER)


def device_args(environ=None):
    """Where llama.cpp runs the model. The CPU by default: on a Mac the GPU froze the screen
    while the model ran. HUMANIZE_GPU=1 (or yes, on, all) puts every layer on the GPU;
    a number from 2 up puts that many of the 36 there, for a GPU with less than ~5 GB free.
    HUMANIZE_GPU_DEVICE=Vulkan1 (a name from `llama-completion --list-devices`) pins the run
    to that GPU, for a laptop that lists an integrated one too."""
    environ = os.environ if environ is None else environ
    gpu = environ.get("HUMANIZE_GPU", "").strip().lower()
    device = environ.get("HUMANIZE_GPU_DEVICE", "").strip()
    pin = ["-dev", device] if device else []
    if gpu in ("1", "yes", "on", "true", "all"):
        return ["-ngl", "99"] + pin
    if gpu.isdigit() and int(gpu) > 1:
        return ["-ngl", gpu] + pin
    return ["-ngl", "0", "-dev", "none"]


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
    cmd = [llama, "-m", base_model_path(),
           "--lora", adapter_path(),
           *device_args(), "-t", str(threads),
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


PERCENT_WORDS = re.compile(r"\s+(?:percent|per\s+cent|por\s+ciento|porciento)\b", re.I)


def restore_percent_signs(original, rewritten):
    """The HIP adapter eats the % sign: «60%» comes out as «60». If the original had
    that number with %, it is given back, to the occurrence that is that figure: not to
    «60 percent» (the sign is in words) nor to «the 5 years» when the original also says
    «5 years». Numbers the original did not have with % are left alone."""
    for n in set(re.findall(r"(\d+(?:[.,]\d+)?)\s?%", original)):
        num = rf"(?<![\d.,]){re.escape(n)}"
        if re.search(num + r"\s?%", rewritten):
            continue
        other = {w.lower() for w in re.findall(num + r"\s+(\w+)", original)}
        for m in re.finditer(num + r"(?![\d.,]*\d)(?!\s?%)", rewritten):
            after = rewritten[m.end():]
            if PERCENT_WORDS.match(after):
                break
            word = re.match(r"\s+(\w+)", after)
            if word and word.group(1).lower() in other:
                continue
            rewritten = rewritten[:m.start()] + n + "%" + rewritten[m.end():]
            break
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


QUOTE = re.compile(r'"([^"\n]{0,800})"|“([^”\n]{0,800})”|«([^»\n]{0,800})»')
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


def quotations(text):
    """Quoted passages of 12+ characters, paired in order: in «called it "naive" while
    others said "bold"» there are two short quotes, not one long one between them."""
    found = []
    for m in QUOTE.finditer(text):
        q = next(g for g in m.groups() if g is not None)
        if len(q) >= 12:
            found.append(q)
    return found


def citation_problem(original, rewritten):
    """A quotation of the original that is no longer verbatim, or a reference in
    brackets that brings a number, a numeral or a name the original never had
    («(De Anima, libro i, cap. vi)»). HIP did both on a test essay; a changed quote or an
    invented source is worse than any detector score. A bracket the try only rewords
    («(from 5% to 30% within two years)») is not a new reference."""
    norm = lambda s: " ".join(s.replace("’", "'").replace("‘", "'").lower().split()).strip(" .,;:")  # noqa: E731
    have = norm(rewritten)
    for q in quotations(original):
        if norm(q) not in have:
            return "(quote changed)"
    words = re.findall(r"\w+", original)
    lower = {w.lower() for w in words}
    for r in references(rewritten):
        for w in re.findall(r"\w+", r):
            numeral = w.isdigit() or (ROMAN.fullmatch(w) and (len(w) > 1 or "," in r))
            if (numeral and w.lower() not in lower) or (
                    not numeral and w[:1].isupper() and len(w) >= 3 and w not in words):
                return "(invented reference)"
    return None


URL = re.compile(r"(?:https?://|www\.)[^\s<>()\[\]\"«»“”'’]+")
LINK_TARGET = re.compile(r"\]\(([^)\s]+)\)")
INLINE_CODE = re.compile(r"`[^`\n]+`")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def markup_problem(original, rewritten):
    """A URL, link target, e-mail address or `inline code` of the original that is not
    in the try verbatim: a rewritten link or command is broken, whatever a detector says."""
    for pat in (URL, LINK_TARGET, INLINE_CODE, EMAIL):
        for token in pat.findall(original):
            if token.rstrip(".,;:!?") not in rewritten:
                return "(link or code changed)"
    return None


STRAY = "$\\{}#*_|~^<>@"


def symbols_added(original, rewritten):
    """Markup characters the try has more of than the original («$», «\\», «{»…): the
    model sometimes wraps a figure in «$…$» or starts a list. A one-character fix each."""
    return [c for c in STRAY if rewritten.count(c) > original.count(c)]


numbers_lost = check.numbers_lost  # a try that drops a year or an amount is retried
numbers_added = check.numbers_added  # a try that invents one is never used


# Problems that still leave a usable try, best first: if every try has one, the best is
# kept and a warning says what to look at. Any other problem means the try is not used.
SOFT = ("(symbols added)", "(AI tells)", "(number changed)", "(copied)")
FALLBACK_STATUS = {"(AI tells)": "fewest tells of", "(number changed)": "a figure to put back, best of",
                   "(copied)": "least copied of", "(symbols added)": "stray symbols to remove, best of"}


def acceptable(p, r, wanted, concepts, max_copied, max_tells=None, lang="en"):
    """(problem, copied share) for one try: problem is None when the try can be used.
    With max_tells, a try that scores more than that in tells.py is «(AI tells)»."""
    if len(r.split()) < 0.6 * len(p.split()) or len(r.split()) > 1.6 * len(p.split()) + 10:
        return "(truncated or too long)", 0.0
    missing = wanted - concepts_in(r, concepts)
    if missing:
        return sorted(missing)[0], 0.0
    problem = citation_problem(p, r) or markup_problem(p, r)
    if problem:
        return problem, 0.0
    if numbers_added(p, r):
        return "(figure added)", 0.0
    share = copied_share(p, r)
    if share > max_copied:
        return "(copied)", share
    if numbers_lost(p, r):
        return "(number changed)", share
    if max_tells is not None and tells.score(r, lang) > max_tells:
        return "(AI tells)", share
    if symbols_added(p, r):
        return "(symbols added)", share
    return None, share


is_title = tells.is_title


def short_item(text):
    """A list item too short to rewrite («Fast setup»). Longer bullets are rewritten even
    without a final period: most AI bullets are fragments of 6 to 12 words."""
    return len(text.split()) <= 5


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
    ap.add_argument("--max-words", dest="max_words", type=int, default=0, metavar="N",
                    help="rewrite a paragraph longer than N words in runs of whole sentences "
                         "and put it back as one paragraph (for a long abstract that keeps "
                         "losing terms; try 100)")
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
    if args.tries < 1:
        print("ERROR: --tries must be 1 or more", file=sys.stderr)
        return 2

    if not llama_binary():
        print("ERROR: llama.cpp is missing. " + HOW_TO_INSTALL_LLAMA, file=sys.stderr)
        return 2
    for path in (base_model_path(), adapter_path()):
        if not os.path.isfile(path):
            print(f"ERROR: {path} is missing; run scripts/install_model.py", file=sys.stderr)
            return 2

    with open(args.original, encoding="utf-8-sig") as fh:
        text = fh.read()
    concepts = check.load_concepts(args.concepts) if args.concepts else []
    args.fmt = blocks.format_of(args.original)
    frame, paragraphs = blocks.parse(text, args.fmt)
    lang = join.detect_language(" ".join(blocks.prose_of(b, args.fmt) for b in paragraphs))
    kept, kept_frame, only = None, None, None
    if args.only:
        only = parse_only(args.only, len(paragraphs))
        if only is None:
            return 2
        if not os.path.isfile(args.output):
            print(f"ERROR: --only needs the existing {args.output}", file=sys.stderr)
            return 2
        with open(args.output, encoding="utf-8-sig") as fh:
            kept_frame, kept = blocks.parse(fh.read(), args.fmt)
        if len(kept) != len(paragraphs):
            print(f"ERROR: {args.output} has {len(kept)} paragraphs and the original "
                  f"{len(paragraphs)}; --only needs the same count", file=sys.stderr)
            return 2
    try:
        return run_paragraphs(args, kept_frame or frame, paragraphs, kept, only, concepts, lang)
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


def one_try(p, args, concepts, lang, lead=None):
    """(problem, copied share, text, (plain p, plain try)) for one model call on paragraph
    or item p. In LaTeX the model sees the prose with placeholders; a try that breaks one
    is «(LaTeX changed)», and the text returned is the try put back in LaTeX. The checks
    read the plain prose, so a placeholder's number is not taken for a figure."""
    if getattr(args, "fmt", "text") == "latex":
        visible, pieces = latex.protect(p)
        plain_p = latex.strip_placeholders(visible)
    else:
        visible, pieces, plain_p = p, None, p
    r = restore_percent_signs(visible, rewrite_paragraph(visible, args.threads, args.temperature,
                                                         lead, lang))
    if pieces is None:
        text, plain_r = r, r
    else:
        text = None if latex.problem(visible, r, pieces) else latex.restore(r, pieces)
        if text is None:
            return "(LaTeX changed)", 0.0, None, None
        plain_r = latex.strip_placeholders(r)
    problem, share = acceptable(plain_p, plain_r, concepts_in(plain_p, concepts), concepts,
                                args.max_copied, args.max_tells, lang)
    return problem, share, text, (plain_p, plain_r)


def rewrite_unit(p, args, concepts, lang, lead=None):
    """One paragraph or list item through its tries: (text, tries used, fallback, lost).
    fallback is the soft problem of a kept try that was not clean (None if it was);
    lost counts the problems of the tries when the original had to be kept. --lead is
    for paragraphs: every item of a list opening with the same words would be a tell."""
    soft, lost = [], collections.Counter()
    for n in range(1, args.tries + 1):
        problem, share, text, plain = one_try(p, args, concepts, lang, lead)
        if problem is None:
            return text, n, None, lost
        if problem in SOFT:
            pp, pr = plain
            metric = (tells.score(pr, lang) if problem == "(AI tells)" else
                      len(numbers_lost(pp, pr)) if problem == "(number changed)" else
                      len(symbols_added(pp, pr)) if problem == "(symbols added)" else share)
            soft.append((SOFT.index(problem), metric, text, problem))
        else:
            lost[problem] += 1
    if soft:
        _, _, r, problem = min(soft, key=lambda c: (c[0], c[1]))
        return r, args.tries, problem, lost
    return p, args.tries, None, lost


def note(report, label, p, text, fallback, lost, lang, fmt="text"):
    """Adds what the user has to look at for one paragraph or item to the report."""
    if fallback and fmt == "latex":
        p, text = latex.plain(p), latex.plain(text)
    if fallback == "(copied)":
        report["copied"].append(f"{label} ({copied_share(p, text):.0%})")
    elif fallback == "(AI tells)":
        report["tells"].append(f"{label} (score {tells.score(text, lang)})")
    elif fallback == "(number changed)":
        report["numbers"].append(f"{label} ({', '.join(numbers_lost(p, text))})")
    elif fallback == "(symbols added)":
        report["symbols"].append(f"{label} ({' '.join(symbols_added(p, text))})")
    elif text == p:
        report["untouched"].append(f"{label} (" + ", ".join(c for c, _ in lost.most_common(2)) + ")")


SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9ÁÉÍÓÚÑ¿¡«\"“(\\])")


AUTO_PARTS, AUTO_PARTS_WORDS = 150, 100  # a paragraph this long that fails is redone in parts


def parts(p, fmt, max_words):
    """A long paragraph in runs of whole sentences of up to max_words words each (a longer
    sentence is a run alone), to be rewritten one by one and put back as ONE paragraph: the
    model loses terms on long paragraphs, and an abstract must stay a single paragraph.
    [p] when it is short, or a LaTeX paragraph with a comment (a line end matters there)."""
    if not max_words or len(p.split()) <= max_words:
        return [p]
    if fmt == "latex":
        if re.search(r"(?<!\\)%", p):
            return [p]
        sentences = latex.sentence_lines(re.sub(r"\s*\n\s*", " ", p.strip())).split("\n")
    else:
        sentences = []
        for s in SENTENCE_END.split(" ".join(p.split())):
            if sentences and join.no_period_end(sentences[-1]):
                sentences[-1] += " " + s  # «et al. Smith», «Fig. 3»: not a sentence end
            else:
                sentences.append(s)
    runs = []
    for s in sentences:
        if runs and len(runs[-1].split()) + len(s.split()) <= max_words:
            runs[-1] += " " + s
        else:
            runs.append(s)
    return runs


def rewrite_block(i, p, args, concepts, lang, report):
    """(rewritten block, status) for block i. Code, tables, headings, quotations and
    titles stay; a list is rewritten item by item and keeps its markers."""
    fmt = getattr(args, "fmt", "text")
    k = blocks.kind(p, fmt)
    if k not in blocks.PROSE or (k == "prose" and is_title(p)):
        return p, f"kept ({'title' if k == 'prose' else k})"
    if k == "list":
        pairs, done, count = [], 0, 0
        for j, (marker, item) in enumerate(blocks.items(p, fmt), 1):
            count += bool(item)
            if short_item(item):
                pairs.append((marker, item))
                continue
            text, _, fallback, lost = rewrite_unit(item, args, concepts, lang)
            note(report, f"{i}.{j}", item, text, fallback, lost, lang, fmt)
            done += text != item
            pairs.append((marker, text))
        return blocks.rebuild(pairs, fmt), f"list, {done} of {count} items rewritten"
    runs = parts(p, fmt, getattr(args, "max_words", 0))
    if len(runs) == 1:
        text, n, fallback, lost = rewrite_unit(p, args, concepts, lang, args.lead)
        if text == p and len(p.split()) > AUTO_PARTS:  # a long paragraph kept losing terms
            runs = parts(p, fmt, AUTO_PARTS_WORDS)
            if len(runs) > 1:
                print(f"  paragraph {i}: left as the original in {n} tries; "
                      f"rewriting it in {len(runs)} parts", flush=True)
    if len(runs) > 1:
        out = []
        for j, run in enumerate(runs, 1):
            text, _, fallback, lost = rewrite_unit(run, args, concepts, lang,
                                                   args.lead if j == 1 else None)
            note(report, f"{i} (part {j})", run, text, fallback, lost, lang, fmt)
            out.append(text)
        done = sum(t != r for t, r in zip(out, runs))
        return ("\n" if fmt == "latex" else " ").join(out), \
            f"one paragraph in {len(runs)} parts, {done} rewritten"
    note(report, str(i), p, text, fallback, lost, lang, fmt)
    status = ("unchanged" if text == p else f"done, {FALLBACK_STATUS[fallback]} {n} tries"
              if fallback else f"done, try {n}" if n > 1 else "done")
    return text, status


def run_paragraphs(args, frame, paragraphs, kept, only, concepts, lang):
    output, t0 = [], time.time()
    fmt = getattr(args, "fmt", "text")
    report = {"untouched": [], "copied": [], "tells": [], "numbers": [], "symbols": []}
    for i, p in enumerate(paragraphs, 1):
        if kept is not None and i not in only:
            output.append(kept[i - 1])
            continue
        if args.candidates:
            if blocks.kind(p, fmt) in blocks.PROSE and not is_title(p):
                write_candidates(args, i, p, concepts, lang)
            else:
                print(f"Paragraph {i}: no candidates for a {blocks.kind(p, fmt)} or a title")
            output.append(kept[i - 1])
            continue
        text, status = rewrite_block(i, p, args, concepts, lang, report)
        output.append(text)
        with open(args.output, "w", encoding="utf-8") as fh:  # saves after every paragraph
            fh.write(blocks.unparse(frame, output + (kept or paragraphs)[i:]))
        print(f"Paragraph {i} of {len(paragraphs)}: {status} ({time.time() - t0:.0f} s)", flush=True)

    if args.candidates:
        print(f"\nCandidates in {args.output}.candidates/ — the output was not changed. Measure them\n"
              "joined and inside the whole text, then adopt one with --take N=FILE.")
        return 0
    print(f"\nWritten: {args.output}")
    if report["untouched"]:
        print("WARNING: kept as the original, the concept they kept losing in brackets: "
              + "; ".join(report["untouched"]) + ". Check the spelling of that concept in the "
              "concepts file.")
    if report["copied"]:
        print("WARNING: every try copied long stretches of the original; the least copied one "
              "was kept: " + "; ".join(report["copied"]) + ". Redo them with --only and more "
              "--tries.")
    if report["numbers"]:
        print("WARNING: every try dropped or changed a figure; the closest was kept. Put the "
              "figure back by hand (a one-word fix): " + "; ".join(report["numbers"]) + ".")
    if report["symbols"]:
        print("WARNING: every try added markup the original does not have; the cleanest was "
              "kept. Delete the stray symbols by hand: " + "; ".join(report["symbols"]) + ".")
    if report["tells"]:
        print("WARNING: every try kept AI tells above --max-tells; the one with the fewest was "
              "kept: " + "; ".join(report["tells"]) + ".")
    strong = []
    for n, x in enumerate(output, 1):
        prose = blocks.prose_of(x, fmt)
        if (only is None or n in only) and prose and not is_title(x):
            hits = tells.find(prose, lang)
            if tells.flagged(hits):
                strong.append(f"{n} ({tells.summary(hits)})")
    if strong:
        print("AI tells left (scripts/tells.py shows them all; regenerate, don't fix by hand): "
              + "; ".join(strong))
    print("Next step: reread against the original and fix by hand what changed (HIP\n"
          "sometimes changes a detail, like «they clean» into «they wash the dishes»);\n"
          "then scripts/join.py.")
    return 0


def one_candidate(p, args, concepts, lang):
    """(text, copied share) of one acceptable version of block p, or None. A list gets
    each item rewritten; a candidate with an item left as the original is not one."""
    fmt = getattr(args, "fmt", "text")
    if blocks.kind(p, fmt) == "list":
        pairs = []
        for marker, item in blocks.items(p, fmt):
            if not short_item(item):
                text, _, fallback, _ = rewrite_unit(item, args, concepts, lang)
                if text == item or fallback:
                    return None
                item = text
            pairs.append((marker, item))
        r = blocks.rebuild(pairs, fmt)
        return r, copied_share(p, r)
    problem, share, text, _ = one_try(p, args, concepts, lang, args.lead)
    return None if problem else (text, share)


def write_candidates(args, i, p, concepts, lang="en"):
    """Up to N acceptable versions of paragraph i, each in its own file. A detector can
    score two samples of the same paragraph 0% and 100%; measuring several and keeping the
    one that passes adds no chat fingerprint, since the same base model wrote them all."""
    folder = args.output + ".candidates"
    os.makedirs(folder, exist_ok=True)
    found, tries, written = 0, 0, []
    while found < args.candidates and tries < args.candidates * args.tries:
        tries += 1
        got = one_candidate(p, args, concepts, lang)
        if got is None:
            continue
        r, share = got
        found += 1
        ext = ".tex" if getattr(args, "fmt", "text") == "latex" else ".txt"
        path = os.path.join(folder, f"p{i:02d}-{found}{ext}")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(r + "\n")
        hits = tells.find(blocks.prose_of(r, getattr(args, "fmt", "text")), lang)
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
    fmt = blocks.format_of(original)
    with open(output, encoding="utf-8-sig") as fh:
        frame, paragraphs = blocks.parse(fh.read(), fmt)
    with open(original, encoding="utf-8-sig") as fh:
        count = len(blocks.parse(fh.read(), fmt)[1])
    if count != len(paragraphs):
        print(f"ERROR: {output} has {len(paragraphs)} paragraphs and the original {count}; "
              "--take needs the same count", file=sys.stderr)
        return 2
    if not 1 <= int(n) <= len(paragraphs):
        print(f"ERROR: {output} has {len(paragraphs)} paragraphs", file=sys.stderr)
        return 2
    with open(path, encoding="utf-8-sig") as fh:
        new = fh.read().strip()
    # a list keeps its lines, and LaTeX its comments' line ends; a paragraph of text is one
    # line, as rewrite.py writes it
    keep_lines = fmt == "latex" or blocks.kind(new) == "list"
    paragraphs[int(n) - 1] = new if keep_lines else " ".join(new.split())
    # a candidate may have been edited by hand: its figures are checked against the original
    with open(original, encoding="utf-8-sig") as fh:
        source = blocks.parse(fh.read(), fmt)[1][int(n) - 1]
    plain = latex.plain if fmt == "latex" else (lambda t: t)
    lost = numbers_lost(plain(source), plain(new))
    added = numbers_added(plain(source), plain(new))
    if lost or added:
        print(f"WARNING: paragraph {n} of {path} " + "; ".join(
            x for x in (lost and "lost the figures " + ", ".join(lost),
                        added and "adds the figures " + ", ".join(added)) if x)
              + " of the original. Put them back, or take another candidate.")
    with open(output, "w", encoding="utf-8") as fh:
        fh.write(blocks.unparse(frame, paragraphs))
    print(f"Paragraph {n} of {output} now comes from {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

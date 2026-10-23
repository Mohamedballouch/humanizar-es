#!/usr/bin/env python3
"""Flags the tells of AI writing left in a text, paragraph by paragraph. No models.

rewrite.py paraphrases from the original, so the stock phrases of chat models can come
through: «plays a crucial role», «not only X but also Y», «Furthermore,», em dashes
everywhere. This script finds them, scores each paragraph and names the ones to
regenerate. It never rewrites anything: a phrase you fix by hand, or ask a chat model to
fix, brings the fingerprint back (SKILL.md). Regenerate the flagged paragraphs with
rewrite.py --only N --candidates 6 and keep the candidate with the fewest tells that
still says everything.

The patterns come from Wikipedia's «Signs of AI writing» (WikiProject AI Cleanup) and the
catalog in github.com/blader/humanizer (MIT), which ranks them by strength. Here they are
weighted: 3 for a tell that justifies regenerating on one sighting, 2 for a stock word, 1
for one that only counts with company (a single dash or triad is human too). Quotations
are skipped: a phrase the author quotes is not theirs. Not measured against detectors yet:
it targets what human readers and stylometric detectors notice, and it ranks candidates.

usage:
  python3 scripts/tells.py rewritten.txt                 # per paragraph, with what it found
  python3 scripts/tells.py original.txt rewritten.txt    # compare files paragraph by paragraph
  python3 scripts/tells.py rewritten.txt --max 2         # exit 1 if a paragraph scores above 2
"""
import argparse
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blocks  # noqa: E402
import check  # noqa: E402
import join  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # so a Windows console does not choke on «» or ñ
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")


def _words(*stems):
    """Whole words with their usual endings: «underscor» matches underscore, underscores,
    underscored, underscoring."""
    return r"\b(?:" + "|".join(stems) + r")\b"


# (label, weight, pattern). Patterns run on check.norm(text): lowercase, no accents,
# straight apostrophes.
PATTERNS = {
    "en": [
        # Leftovers from the chat: never part of the text.
        ("chat residue", 3, r"\b(?:i hope this helps|great question|you're absolutely right|"
         r"certainly!|of course!|let me know if|feel free to|would you like me to|"
         r"i'd be happy to|here is (?:an?|the) (?:overview|summary|breakdown|rewrite))"),
        ("knowledge-limit disclaimer", 3, r"\b(?:as of my (?:last|latest) (?:training|update|"
         r"knowledge)|up to my last training|while specific details (?:are|remain) (?:limited|"
         r"scarce)|based on (?:the )?available information|not (?:widely|publicly|extensively) "
         r"(?:documented|available|disclosed))"),
        # Staging instead of stating.
        ("not X but Y", 3, r"\bnot (?:just|only|merely|simply)\b[^.;:!?]{1,90}?\bbut\b|"
         r"\b(?:it|this|that)(?:'s| is) not (?:just |only |merely )?(?:about )?[^.;:!?,]{1,50}"
         r"[,;] (?:it|this|that)(?:'s| is)\b|\bisn't (?:just|only|merely)\b|"
         r"\bthis (?:does not|doesn't) mean\b[^.!?]{0,90}[.;] it means\b"),
        ("staged run-up", 3, r"\b(?:let's (?:dive|delve|explore|unpack|break (?:this|it) down|"
         r"take a (?:closer )?look)|here's (?:the thing|what you need to know)|"
         r"without further ado|the thing is,|let's be honest|real talk)|\bhonestly\?"),
        ("deep-sounding saying", 3, r"\b(?:at its core|the real question is|what really "
         r"matters|the heart of the matter|the deeper issue|let that sink in|read that again)\b"),
        ("arguing with no one", 3, r"\b(?:to be clear,|don't get me wrong|this is not to say|"
         r"i'm not (?:saying|arguing)|one might be tempted|(?:a|one) tempting approach would be|"
         r"this isn't (?:mainly |just |only )?about|it would be easy to (?:just )?assume)"),
        ("inflated significance", 3, r"\b(?:stands? as a testament|(?:a|an enduring) testament "
         r"to|(?:plays?|playing|played) an? (?:crucial|pivotal|key|vital|significant|important|"
         r"central|instrumental) role|pivotal (?:moment|role|step)|marking a (?:pivotal|"
         r"significant|major|turning)|setting the stage for|(?:ever-)?evolving landscape|"
         r"indelible mark|(?:enduring|lasting) legacy|in today's (?:fast-paced|digital|modern|"
         r"ever-changing|rapidly changing|interconnected) world|in an (?:increasingly|"
         r"ever-changing) (?:\w+ )?(?:world|landscape|era)|the future looks bright|exciting "
         r"times (?:lie )?ahead|a step in the right direction|paving the way|cannot be "
         r"overstated|fundamentally (?:reshaped|transformed|changed)|game-changer|despite these "
         r"challenges|continues to thrive)\b"),
        ("filler", 2, r"\b(?:it is (?:important|worth|crucial|essential) to (?:note|mention|"
         r"remember|recognize|consider)|it's (?:important|worth) (?:noting|mentioning|to note)|"
         r"it is worth (?:noting|mentioning)|when it comes to|in the realm of|"
         r"one-size-fits-all|a myriad of|a plethora of|a wide (?:range|array) of|"
         r"navigat(?:e|es|ing) the (?:complexities|challenges)|in conclusion,|in summary,|"
         r"to sum up,|all in all,)"),
        # Words models use far more than people.
        ("AI word", 2, _words(
            r"delv(?:e|es|ed|ing)", r"tapestr(?:y|ies)", r"testament", r"pivotal", r"crucial(?:ly)?",
            r"underscor(?:e|es|ed|ing)", r"showcas(?:e|es|ed|ing)", r"vibrant", r"intricate",
            r"intricac(?:y|ies)", r"meticulous(?:ly)?", r"garner(?:s|ed|ing)?",
            r"bolster(?:s|ed|ing)?", r"interplay", r"enduring", r"landscapes?",
            r"seamless(?:ly)?", r"multifaceted", r"holistic", r"transformative", r"paramount",
            r"realm", r"furthermore", r"moreover", r"additionally", r"notably",
            r"foster(?:s|ed|ing)?", r"leverag(?:e|es|ed|ing)", r"streamlin(?:e|es|ed|ing)",
            r"robust", r"nuanced", r"commendable", r"embark(?:s|ed|ing)?", r"unwavering",
            r"align(?:s|ed)? with", r"enhanc(?:e|es|ed|ing)", r"invaluable", r"ever-evolving",
            r"forward-thinking", r"cutting-edge", r"groundbreaking")),
        # Weak alone.
        ("-ing rider", 1, r", (?:highlighting|underscoring|emphasizing|ensuring|reflecting|"
         r"symbolizing|contributing to|cultivating|fostering|encompassing|showcasing|"
         r"demonstrating|illustrating|signaling|paving)\b"),
        ("avoids is/has", 1, r"\b(?:serves|stands|functions|acts) as an?\b|\bboasts\b"),
        ("sales language", 1, r"\b(?:nestled|in the heart of|breathtaking|must-visit|stunning|"
         r"renowned|rich (?:cultural )?heritage|diverse array|state-of-the-art|world-class)\b"),
        ("vague authority", 1, r"\b(?:experts (?:say|argue|believe|agree|note)|"
         r"(?:studies|research) (?:shows?|suggests?|indicates?)|according to (?:several|many|"
         r"some|various) (?:studies|experts|reports)|observers have (?:noted|cited))\b"),
        ("stacked hedge", 1, r"\b(?:could potentially|may potentially|might arguably|"
         r"it could be argued|it's also possible that)\b"),
        ("triad", 1, r"\b[\w-]+(?: [\w-]+){0,2}, [\w-]+(?: [\w-]+){0,2}, (?:and|or) [\w-]+"),
        ("dash", 1, r"—|(?<!\d)\s–\s|\s--\s"),
    ],
    "es": [
        ("restos del chat", 3, r"(?:espero que (?:esto|te) (?:ayude|sirva)|¡claro!|¡por supuesto!|"
         r"excelente pregunta|si quieres,? puedo|no dudes en|aqui tienes (?:un|una|el|la) "
         r"(?:resumen|version|texto))"),
        ("limite de conocimiento", 3, r"(?:hasta (?:mi|la fecha de mi) ultima actualizacion|"
         r"segun la informacion disponible|no (?:esta|estan) ampliamente documentad)"),
        ("relevancia inflada", 3, r"\b(?:(?:juega|juegan|desempena|desempenan) un papel "
         r"(?:crucial|fundamental|clave|esencial|vital|determinante|primordial)|un (?:claro )?"
         r"testimonio de|en el (?:panorama|mundo) actual|en un mundo cada vez mas|en la era "
         r"(?:digital|actual|moderna)|marc(?:a|o|ando) un (?:hito|antes y un despues)|"
         r"sienta las bases|allana el camino|no se puede subestimar)"),
        ("no solo… sino", 2, r"\bno (?:solo|solamente|unicamente)\b[^.;:!?]{1,90}?\bsino\b"),
        ("relleno", 2, r"\b(?:cabe (?:destacar|senalar|mencionar|resaltar)|es (?:importante|"
         r"fundamental|crucial) (?:destacar|senalar|mencionar|resaltar|tener en cuenta)|vale la "
         r"pena (?:destacar|mencionar|senalar)|sin lugar a dudas|en definitiva,|en conclusion,|"
         r"en resumen,|un sinfin de|una amplia gama de|una miriada de)"),
        ("palabra de IA", 2, _words(
            r"profundiz(?:ar|amos|a) en", r"adentr(?:arnos|arse)", r"sumerg(?:irnos|irse)",
            r"crucial(?:es)?", r"intrincad[oa]s?", r"meticulos(?:o|a|os|as|amente)",
            r"vibrantes?", r"multifaceticos?", r"holistic[oa]s?", r"transformador(?:a|es)?",
            r"potenci(?:ar|ando)", r"fomentar")),
        ("gerundio colgado", 1, r", (?:destacando|subrayando|resaltando|enfatizando|reflejando|"
         r"simbolizando|contribuyendo a|fomentando|garantizando|asegurando)\b"),
        ("raya", 1, r"(?<=\w)\s?—\s?(?=\w)|\s–\s"),
    ],
}
COMPILED = {lang: [(label, w, re.compile(p)) for label, w, p in pats]
            for lang, pats in PATTERNS.items()}

# Paragraphs that open with these make the model rebuild the stock sentence (SKILL.md,
# «stock openings»); rewrite.py --lead gives it another start.
STOCK_OPENINGS = {
    "en": ("additionally,", "moreover,", "furthermore,", "in addition,", "notably,",
           "importantly,", "ultimately,", "in conclusion,", "in summary,", "overall,",
           "looking ahead,", "in today's", "in an era", "when it comes to", "one of the most",
           "it is important", "it's important", "it is worth", "in the realm of"),
    "es": ("uno de los problemas", "una de las", "uno de los", "en conclusion,",
           "en resumen,", "en definitiva,", "en la actualidad,", "hoy en dia,", "cabe destacar",
           "es importante", "en el mundo actual", "en un mundo"),
}
STRONG = 3  # a paragraph at or above this score is worth regenerating
QUOTED = re.compile(r'"[^"\n]{3,}?"|“[^”\n]{3,}?”|«[^»\n]{3,}?»')


def _prepare(text):
    """Normalized text with quotations blanked out (same length, so offsets hold)."""
    t = check.norm(text).replace("’", "'").replace("‘", "'")
    return QUOTED.sub(lambda m: " " * len(m.group(0)), t)


def find(paragraph, lang="en"):
    """[(label, weight, matched text)] for one paragraph."""
    t = _prepare(paragraph)
    hits = []
    for label, weight, pat in COMPILED[lang]:
        for m in pat.finditer(t):
            hits.append((label, weight, " ".join(m.group(0).split()) or m.group(0)))
    start = t.lstrip()
    opening = next((o for o in STOCK_OPENINGS[lang] if start.startswith(o)), None)
    if opening:
        hits.append(("stock opening", 2, opening))
    # three or more sentences in a row that open with the same word («She noted… She…»)
    firsts = [m.group(1) for m in re.finditer(r"(?:^|[.!?]\s+)[¿¡«\"]?(\w+)", t)]
    run = 1
    for a, b in zip(firsts, firsts[1:]):
        run = run + 1 if a == b and a not in ARTICLES else 1
        if run == 3:
            hits.append(("repeated opening", 1, a + " ×3"))
    return hits


ARTICLES = {"the", "a", "an", "el", "la", "los", "las", "un", "una", "lo"}
EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\u2B06\u2934\u2935]")
BOLD = re.compile(r"\*\*[^*\n]+\*\*|__[^_\n]+__")


def formatting(block):
    """Markup that marks AI text as much as its words: a bold label on every item, bold
    sprinkled in prose, emojis in headings and lists, arrows, Title Case Headings. This is
    the one kind of tell to fix by hand: removing markup adds no words."""
    k = blocks.kind(block)
    hits = []
    if k == "list":
        texts = [t for _, t in blocks.items(block)]
        for t in texts:
            t = EMOJI.sub("", t).lstrip()
            if re.match(r"(?:\*\*|__)[^*_\n]{1,60}(?::\s*(?:\*\*|__)|(?:\*\*|__)\s*:)", t):
                hits.append(("bold label", 1, "**…:**"))
    elif k in ("prose", "heading"):
        texts = [block]
    else:
        return hits
    for t in texts:
        bare = EMOJI.sub("", t).lstrip()
        rest = re.sub(r"^(?:\*\*|__)[^*_\n]{1,60}(?:\*\*|__)\s*:?", "", bare) if k == "list" else t
        hits += [("bold", 1, "**…**") for _ in BOLD.finditer(rest)]
        hits += [("emoji", 1, m.group(0)) for m in EMOJI.finditer(t)]
        hits += [("arrow", 1, "→") for _ in re.finditer("→", t)]
    title = EMOJI.sub("", block.lstrip("#")).strip()
    words = re.findall(r"[^\W\d_][\w'-]*", title)
    if (k == "heading" or (k == "prose" and is_title(block))) and len(words) >= 4:
        long_words = [w for w in words[1:] if len(w) >= 4]
        if len(long_words) >= 3 and all(w[0].isupper() for w in long_words):
            hits.append(("Title Case heading", 1, title[:40]))
    return hits


def score(paragraph, lang="en"):
    return sum(w for _, w, _ in find(paragraph, lang))


def summary(hits):
    """«crucial ×2, not only … but (not X but Y), —» from a list of hits."""
    counts = collections.Counter((label, text) for label, _, text in hits)
    parts = []
    for (label, text), n in counts.most_common():
        shown = text if len(text) <= 40 else text[:37] + "…"
        tag = "" if label in ("AI word", "palabra de IA", "dash", "raya", "bold", "emoji",
                              "arrow") else f" ({label})"
        parts.append(f"{shown}{tag}" + (f" ×{n}" if n > 1 else ""))
    return ", ".join(parts)


def suggested_lead(paragraph, lang="en"):
    """Two words after a stock connector, as an opening for rewrite.py --lead; None if
    the opening is not a connector that can be left out («One of the most…» needs words
    that fit the paragraph, which only a person can choose)."""
    m = re.match(r"\s*(\w+(?: \w+)?),\s+(\S+\s+\S+)", paragraph)
    if not m or check.norm(m.group(1)) + "," not in STOCK_OPENINGS[lang]:
        return None
    lead = m.group(2).strip(",;:")
    return lead[0].upper() + lead[1:]


def paragraphs_of(text):
    return blocks.split(text)


def is_title(p):
    return len(p.split()) <= 12 and not p.rstrip().endswith((".", "!", "?", "…", ":"))


def report(paragraphs, lang):
    """[(number, score, hits)] for the paragraphs that are prose or lists and not titles;
    code, tables, headings and quotations are not the author's prose."""
    out = []
    for i, p in enumerate(paragraphs, 1):
        prose = blocks.prose_of(p)
        if not prose or is_title(p):
            continue
        hits = find(prose, lang)
        out.append((i, sum(w for _, w, _ in hits), hits))
    return out


def main():
    ap = argparse.ArgumentParser(description="Flags the tells of AI writing, paragraph by paragraph.")
    ap.add_argument("files", nargs="+", help="one text, or the original and its versions")
    ap.add_argument("--lang", "--idioma", dest="lang", choices=sorted(PATTERNS),
                    help="en or es (detected by default)")
    ap.add_argument("--max", type=int, metavar="N",
                    help="exit 1 if a paragraph of the last file scores above N")
    args = ap.parse_args()

    try:
        texts = []
        for f in args.files:
            with open(f, encoding="utf-8") as fh:
                texts.append(fh.read())
    except OSError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    last_blocks = paragraphs_of(texts[-1])
    lang = args.lang or join.detect_language(" ".join(blocks.prose_of(b) for b in last_blocks))
    reports = [report(paragraphs_of(t), lang) for t in texts]
    last, name = reports[-1], args.files[-1]

    print(f"Tells of AI writing in {name} (language: {lang}; 3 = strong, 2 = stock word, "
          "1 = weak alone)\n")
    if len(texts) > 1:
        heads = [check.short_name(f) for f in args.files]
        print(f"{'paragraph':<10} " + " ".join(f"{h:>18}" for h in heads))
        by_file = [{i: s for i, s, _ in r} for r in reports]
        for i, _, _ in last:
            print(f"{i:<10} " + " ".join(f"{str(b.get(i, '-')):>18}" for b in by_file))
        print(f"{'total':<10} " + " ".join(f"{sum(s for _, s, _ in r):>18}" for r in reports))
        print()
    for i, s, hits in last:
        if hits:
            print(f"  ¶{i:<3} {s:>3}  {summary(hits)}")
    flagged = [(i, s) for i, s, _ in last if s >= STRONG]
    total = sum(s for _, s, _ in last)
    print(f"\n{len(last)} paragraphs, total {total}; {len(flagged)} at {STRONG} or more.")
    if flagged:
        only = ",".join(str(i) for i, _ in flagged)
        print("Don't fix them by hand: regenerate them from the original and keep the candidate\n"
              "with the fewest tells that still says everything (the rewrite before join.py):\n"
              "  python3 scripts/rewrite.py 00-original.txt -o 01-rewritten.txt "
              f"--concepts concepts.txt --only {only} --candidates 6")
        for i, _ in flagged:
            lead = suggested_lead(blocks.prose_of(last_blocks[i - 1]), lang)
            if lead:
                print(f"  ¶{i} opens with a stock connector; add --lead \"{lead}\" for that one.")
    markup = [(i, formatting(b)) for i, b in enumerate(last_blocks, 1)]
    markup = [(i, h) for i, h in markup if h]
    if markup:
        print("\nFormatting tells (these you may fix by hand: removing markup adds no words):")
        for i, h in markup:
            print(f"  ¶{i:<3} {summary(h)}")
    if args.max is not None and any(s > args.max for _, s, _ in last):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

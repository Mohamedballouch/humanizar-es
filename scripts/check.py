#!/usr/bin/env python3
"""Checks that a rewrite keeps the content of the original.

Humanizing changes the surface (rhythm, syntax, vocabulary). The content -names,
figures, technical terms, negations- has to survive intact. This script checks it
in two ways:

  1. Concepts: every concept of the original must appear in every variant.
     Concepts come from a file (--concepts) or, if none is given, are extracted
     automatically from the original (proper nouns, figures, terms in
     parentheses or quotes).
  2. Negations: warns if a negative construction of the original ("no
     contradiction", "never", "without") disappears from the variant. It is the
     most dangerous error: it flips the meaning and no proofreader catches it.
  3. Figures: every number of the original (a year, an amount, a percentage, a decimal
     with its precision, a roman numeral like «siglo XX») must be in the variant as many
     times, and the variant must not add one. Both are errors: «60%» -> «sixty percent»,
     a dropped year, a «0.50» that became «0.5», an invented «35%».

Standard library only.

Usage:
  check.py original.txt variant.txt [variant2.txt ...]
  check.py original.txt variant.txt --concepts concepts.txt
  check.py original.txt --list     # show which concepts it extracts

Concepts file format (one per line, # for comments):
  Aristotle | the Stagirite       <- variants separated by |; any one is enough
  principle of non-contradiction
  antinomy                        <- whole word; accepts the plural (antinomies, policy ->
                                     policies, luz -> luces)
  subatomic*                      <- with * it matches by prefix: subatomic, subatomics...
  C#                              <- a # starts a comment only at the start or after a space
Matching ignores case and accents.

Exit code: 0 if every variant keeps 100% of the concepts and every figure, 1 if any
loses a concept or loses or adds a figure, 2 on a usage error.
"""
import argparse
import collections
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import latex  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # so a Windows console does not choke on «» or ñ
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")

# Spanish and English
NEGATIONS = (r"no|ni|nunca|jamas|tampoco|sin|nadie|nada|ningun|ninguna|ninguno|"
             r"not|never|nor|without|none|nobody|nothing|neither|cannot")

# Capitalized words that are not proper nouns even when they do not open a sentence.
NOT_PROPER = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "y", "o", "en",
    "a", "al", "por", "para", "con", "sin", "que", "se", "su", "sus", "lo", "es",
    "este", "esta", "estos", "estas", "ese", "esa", "como", "pero", "si", "no",
    "the", "an", "of", "and", "or", "in", "on", "at", "for", "to", "with", "by", "from",
    "this", "that", "these", "those", "it", "its", "but", "if", "when", "while", "as",
}


def norm(s):
    """Lowercase and without accents, to compare regardless of spelling."""
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def pattern(term):
    """Whole word (optional plural), flexible spaces. With a trailing *, matches
    by prefix. So "ser" does not match "servicio"."""
    term = norm(term).strip()
    prefix = term.endswith("*")
    parts = [re.escape(p) for p in term.rstrip("*").split()]
    if not prefix and re.search(r"[^aeiou]y$", parts[-1]):
        parts[-1] = parts[-1][:-1] + "(?:y|ie)"  # policy, policies
    elif not prefix and parts[-1].endswith("z"):
        parts[-1] = parts[-1][:-1] + "(?:z|c(?=es))"  # luz, luces
    end = "" if prefix else r"(?:e?s)?(?!\w)"
    return re.compile(r"(?<!\w)" + r"\s+".join(parts) + end)


def load_concepts(path):
    concepts = []
    with open(path, encoding="utf-8-sig") as fh:
        for line in fh:
            line = re.split(r"(?:^|\s)#", line, maxsplit=1)[0].strip()
            if not line:
                continue
            variants = [v.strip() for v in line.split("|") if v.strip()]
            concepts.append((variants[0], variants))
    return concepts


def extract_concepts(text):
    """Extracts candidates for untouchable content. It is a heuristic: review the
    list with --list and, for serious work, pass a file with --concepts."""
    found = {}

    def add(t, alternatives=()):
        t = t.strip(" .,;:«»\"'()")
        words = t.split()
        while len(words) > 1 and norm(words[0]) in NOT_PROPER:
            words = words[1:]  # "el noumeno" -> "noumeno"
        t = " ".join(words)
        if len(t) >= 3 and norm(t) not in found:
            found[norm(t)] = [t, *alternatives]

    # 1. proper nouns: capitalized words and their inner joins ("Tomas de Aquino").
    #    The word that opens a sentence is dropped because its capital may be only
    #    positional: a name that ONLY appears at the start of a sentence is not
    #    detected. That is why the automatic list is just a starting point.
    capital = r"[A-ZÁÉÍÓÚÑÜ][\wáéíóúñü]+"
    joiner = r"(?:\s+(?:de|del|la|las|los|y|of|the)\s+|\s+)"
    for m in re.finditer(rf"{capital}(?:{joiner}{capital})*", text):
        start = m.start()
        before = text[:start].rstrip()
        opens_sentence = not before or before[-1] in ".!?¿¡:\n«\"—"
        words = m.group(0).split()
        if opens_sentence:
            words = words[1:]  # the first one is capitalized by position
            while words and norm(words[0]) in NOT_PROPER:
                words = words[1:]
        if words and norm(words[0]) not in NOT_PROPER:
            # "Immanuel Kant" also counts as "Kant" in the variant
            alt = [words[-1]] if len(words) > 1 and words[-1][0].isupper() else []
            add(" ".join(words), alt)

    # 2. figures, percentages and dates
    for m in re.finditer(r"\d+(?:[.,]\d+)*\s*%?", text):
        add(m.group(0))

    # 3. short terms in parentheses or angle quotes
    for m in re.finditer(r"\(([^()]{2,40})\)|«([^«»]{2,40})»", text):
        add(m.group(1) or m.group(2))

    return [(v[0], v) for v in found.values()]


def negations(text):
    """Normalized 'negation + next word' pairs of the text, with how often each appears:
    a negation lost in one sentence is not hidden by the same pair in another. Quotes and
    parentheses are ignored ('no «contradiccion»' counts as 'no contradiccion'), and
    English contractions count as 'not' ("doesn't apply" = "does not apply")."""
    clean = re.sub(r"n['’]t(?!\w)", " not", norm(text))
    clean = re.sub(r"[«»\"“”‘’()\[\]]", " ", clean)
    return collections.Counter(
        f"{a} {b}"
        for a, b in re.findall(rf"(?<!\w)({NEGATIONS})\s+(\w+)", clean)
    )


# Figures: numbers in digits, and roman numerals of two or more letters made of I, V and
# X («siglo XX», «Phase II», «World War II»). ML, CV or DL are not numerals here.
# A minus sign is part of the figure («-0.7» and «0.7» are opposite results) when it stands
# where a sign can: after a space, «(», «[», «=», «$» or at the start, never inside «5-7»
# or «COVID-19». A «+» is not: «+2.8» is 2.8.
NUMBER = re.compile(r"(?:(?<![\w.,)\]])[-−](?=\d))?\d+(?:[.,]\d+)*"
                    r"|\b(?=[IVX]{2,}\b)X{0,3}(?:IX|IV|V?I{0,3})\b")
NUMBER_WORDS = {
    "en": "zero one two three four five six seven eight nine ten eleven twelve thirteen "
          "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split(),
    "es": "cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce "
          "quince dieciseis diecisiete dieciocho diecinueve veinte".split(),
}
TENS = {"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
        "ninety": 90, "hundred": 100, "thousand": 1000, "million": 1000000, "treinta": 30,
        "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80,
        "noventa": 90, "cien": 100, "ciento": 100, "mil": 1000, "millon": 1000000,
        "una": 1, "un": 1}


def figure_key(n):
    """The value a figure stands for, so the same figure written two ways matches and two
    different figures never do. Thousands separators go («1,990» = «1.990» = «1990», but
    only in groups of exactly three digits after a first digit that is not 0); a decimal
    comma is a decimal point («0,05» = «0.05»); «1.5» and «15» stay different, and so do
    «0.50» and «0.5», because the precision a paper reports is part of the figure."""
    n = n.replace("−", "-")
    sign = "-" if n.startswith("-") else ""
    n = n.lstrip("-")
    if not n[0].isdigit():
        return n
    return sign + _unsigned_key(n)


def _unsigned_key(n):
    if re.fullmatch(r"[1-9]\d{0,2}(?:,\d{3})+|[1-9]\d{0,2}(?:\.\d{3})+", n):
        return n.replace(",", "").replace(".", "")
    return n.replace(",", ".")


def figures(text):
    """Counter of figure values, and the first spelling of each one in the text."""
    found = NUMBER.findall(text)
    spelled = {}
    for n in found:
        spelled.setdefault(figure_key(n), n)
    return collections.Counter(figure_key(n) for n in found), spelled


def _words_for(text):
    """Values the text writes out in words («two», «sixty», «veinte»), so that turning a
    word into digits is not a new figure."""
    words = set(re.findall(r"[a-z]+", norm(text)))
    values = {str(i) for lang in NUMBER_WORDS.values() for i, w in enumerate(lang) if w in words}
    return values | {str(v) for w, v in TENS.items() if w in words}


def numbers_lost(original, variant):
    """Figures of the original that the variant has fewer times, once per missing
    occurrence: «2020» twice in the original and once in the variant is one «2020» lost.
    Only digits and numerals: «two or three days» is the concepts file's job."""
    have, _ = figures(variant)
    want, spelled = figures(original)
    return [spelled[k] for k, n in (want - have).items() for _ in range(n)]


def numbers_added(original, variant):
    """Figures the variant has more times than the original: an invented year, amount or
    percentage. A figure the original writes in words («two» -> «2») is not new."""
    have, spelled = figures(variant)
    want, _ = figures(original)
    words = _words_for(original)
    return [spelled[k] for k, n in (have - want).items() if k not in words for _ in range(n)]


SPELLING = ((r"isation", "ization"), (r"ise", "ize"), (r"ised", "ized"), (r"ises", "izes"),
            (r"ising", "izing"), (r"yse", "yze"), (r"ysed", "yzed"), (r"our", "or"),
            (r"tre", "ter"), (r"lling", "ling"), (r"lled", "led"), (r"ogue", "og"))


def spelling_changes(original, variant):
    """[(original word, new word)] where the variant spells a word of the original the
    other way («optimization» -> «optimisation»): the model writes British or American
    spelling at random, and a paper keeps one."""
    words = lambda t: set(re.findall(r"[A-Za-z]+", t.lower()))
    before, after = words(original), words(variant)
    out = []
    for w in sorted(after - before):
        for a, b in SPELLING:
            for x, y in ((a, b), (b, a)):
                if w.endswith(x) and len(w) > len(x) + 2:
                    other = w[: -len(x)] + y
                    if other in before and (other, w) not in out:
                        out.append((other, w))
    return out


def short_name(path, width=18):
    base = path.replace("\\", "/").split("/")[-1]
    return base if len(base) <= width else base[: width - 1] + "…"


def main():
    ap = argparse.ArgumentParser(
        description="Checks that a rewrite keeps the content of the original."
    )
    ap.add_argument("original")
    ap.add_argument("variants", nargs="*")
    ap.add_argument("--concepts", "--conceptos", dest="concepts",
                    help="file with one concept per line")
    ap.add_argument("--list", "--listar", dest="list", action="store_true",
                    help="show the concepts and exit")
    args = ap.parse_args()

    try:
        texts = {}
        for f in [args.original] + args.variants:
            with open(f, encoding="utf-8-sig") as fh:
                texts[f] = fh.read()
            if os.path.splitext(f)[1].lower() in (".tex", ".latex", ".ltx"):
                texts[f] = latex.plain(texts[f])  # accents as letters, 60\% as 60%
        concepts = (
            load_concepts(args.concepts)
            if args.concepts
            else extract_concepts(texts[args.original])
        )
    except OSError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    source = "file " + args.concepts if args.concepts else "automatic extraction"
    if args.list or not args.variants:
        print(f"{len(concepts)} concepts ({source}):")
        if not args.concepts:
            print("  Heuristic: it misses names that only appear at the start of a sentence")
            print("  and lowercase concepts. Copy it to a file, complete it and use --concepts.")
        for name, variants in concepts:
            extra = f"   (or: {', '.join(variants[1:])})" if len(variants) > 1 else ""
            print(f"  - {name}{extra}")
        return 0

    if not concepts:
        print("ERROR: no concepts to check. Pass --concepts.", file=sys.stderr)
        return 2

    files = list(dict.fromkeys([args.original] + args.variants))  # a file named twice counts once
    args.variants = [f for f in files if f != args.original]
    normalized = {f: norm(t) for f, t in texts.items()}
    print(f"Concepts: {len(concepts)} ({source})\n")
    print(f"{'concept':<30} " + " ".join(f"{short_name(f):>18}" for f in files))

    totals = {f: 0 for f in files}
    lost = {f: [] for f in files}
    for name, variants in concepts:
        pats = [pattern(v) for v in variants]
        row = []
        for f in files:
            hit = any(p.search(normalized[f]) for p in pats)
            totals[f] += hit
            if not hit:
                lost[f].append(name)
            row.append("ok" if hit else "LOST")
        print(f"{name[:30]:<30} " + " ".join(f"{v:>18}" for v in row))

    print("\nSUMMARY of fidelity:")
    failed = False
    for f in files:
        n = totals[f]
        pct = 100 * n / len(concepts)
        mark = "" if n == len(concepts) else "   <-- review"
        print(f"  {short_name(f, 30):<30} {n}/{len(concepts)} = {pct:.0f}%{mark}")
        if f != args.original and n < len(concepts):
            failed = True

    if totals[args.original] < len(concepts):
        failed = True
        print(
            "\nERROR: the ORIGINAL does not contain every concept. The list does not match"
            " this text (or a variant is misspelled); fix it."
        )

    neg_original = negations(texts[args.original])
    warnings = []
    for f in args.variants:
        missing = sorted(neg_original - negations(texts[f]))  # counts: one lost of two shows
        if missing:
            warnings.append((f, missing))
    if warnings:
        print("\nNEGATIONS from the original that no longer appear the same (review by hand):")
        print("  Many are legitimate rewordings. Look for the ones that change the meaning,")
        print("  like 'principle of non-contradiction' -> 'principle of contradiction'.")
        for f, missing in warnings:
            print(f"  {short_name(f, 30)}: " + ", ".join(f"«{x}»" for x in missing))

    count = {f: len([b for b in re.split(r"\n[ \t]*\n", t.strip()) if b.strip()])
             for f, t in texts.items()}
    split = [f for f in args.variants if count[f] != count[args.original]]
    if split:
        failed = True
        print(f"\nPARAGRAPHS: the original has {count[args.original]}; "
              + ", ".join(f"{short_name(f, 30)} has {count[f]}" for f in split) + ".")
        print("  A rewrite keeps the original's paragraphs: an abstract stays ONE paragraph.\n"
              "  Join them back (rewrite.py --max-words rewrites a long one in parts).")

    respelled = [(f, spelling_changes(texts[args.original], texts[f])) for f in args.variants]
    respelled = [(f, c) for f, c in respelled if c]
    if respelled:
        print("\nSPELLING switched between British and American (put the original's back; "
              "a one-word fix each):")
        for f, changes in respelled:
            print(f"  {short_name(f, 30)}: " + ", ".join(f"«{a}» -> «{b}»" for a, b in changes))

    changed = []
    for f in args.variants:
        lost = numbers_lost(texts[args.original], texts[f])
        added = numbers_added(texts[args.original], texts[f])
        if lost or added:
            changed.append((f, lost, added))
    if changed:
        failed = True
        print("\nFIGURES that changed (every number of the original must stay as it is):")
        for f, lost, added in changed:
            print(f"  {short_name(f, 30)}:"
                  + (f" lost {', '.join(lost)}" if lost else "")
                  + (";" if lost and added else "")
                  + (f" added {', '.join(added)}" if added else ""))
        print("  Put a lost figure back by hand (a one-word fix); an added one is a detail the\n"
              "  original never gave: remove it or regenerate that paragraph.")
    else:
        n = sum(figures(texts[args.original])[0].values())
        print(f"\nFIGURES: all {n} of the original are in every version, none added.")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

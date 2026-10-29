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
import blocks  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # so a Windows console does not choke on «» or ñ
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")

# Spanish and English
NEGATIONS = (r"no|ni|nunca|jamas|tampoco|sin|nadie|nada|ningun|ninguna|ninguno|"
             r"not|never|nor|without|none|nobody|nothing|neither|cannot")

# How strongly a paper states a claim. A rewrite that drops «may» or «suggests», or adds
# «significant» or «demonstrates», changes what the authors claim even when every figure and
# term survives: a real run turned «neither superiority nor equivalence is established» into
# «no significant difference», and a cleanup turned «addressing» into «solved».
HEDGES = re.compile(r"(?<!\w)(?:may|might|could|possibl[ey]|perhaps|maybe|likely|probabl[ey]|potentially|"
                    r"suggest(?:s|ed|ing)?|indicat(?:e|es|ed|ing)|appears?|appeared|seems?|seemed|"
                    r"tends?|tended|partly|partially|approximately|roughly|preliminary|"
                    r"puede[n]?|podria[n]?|posiblemente|probablemente|quiza[s]?|sugiere[n]?|"
                    r"indica[n]?|parece[n]?|tiende[n]?|aproximadamente|parcialmente)(?!\w)")
BOOSTERS = re.compile(r"(?<!\w)(?:clearly|prov(?:e|es|ed|en|ing)|demonstrat(?:e|es|ed|ing)|"
                      r"confirm(?:s|ed|ing)?|conclusive(?:ly)?|definitely|certainly|undoubtedly|"
                      r"significant(?:ly)?|strongly|always|"
                      r"claramente|demuestra[n]?|prueba[n]?|confirma[n]?|significativ[oa]s?|"
                      r"significativamente|sin duda|siempre)(?!\w)")


COMPARE = r"(?:out-?perform|beat|surpass|exceed|outstrip|outdo|overtak|outpac|outrank|dominat)\w*"
COMPARE_ACTIVE = re.compile(r"(?<!\w)" + COMPARE)
COMPARE_PASSIVE = re.compile(r"(?<!\w)(?:is|are|was|were|be|been|being|gets?|got)\s+(?:\w+\s+){0,2}?"
                             + COMPARE + r"\s+(?:[\w,-]+\s+){0,5}?by(?!\w)")
OPPOSITES = (("superior", "inferior"), ("better", "worse"), ("outperform", "underperform"),
             ("mejor", "peor"))  # word beginnings: «outperforms», «worsened»


def comparison_changes(original, variant):
    """What may have flipped a comparison: an active «outperform» that came back passive
    («controllers are out-performed by rule based scheduling», in a real try that passed
    every other check) or the other way round, and «superior» that became «inferior». The
    new words can be right; who beats whom is what to read."""
    o, v = norm(original), norm(variant)
    out = []
    po, pv = len(COMPARE_PASSIVE.findall(o)), len(COMPARE_PASSIVE.findall(v))
    ao, av = len(COMPARE_ACTIVE.findall(o)) - po, len(COMPARE_ACTIVE.findall(v)) - pv
    if pv > po and ao > 0:
        out.append("active «%s» came back passive («… by»)" % COMPARE_ACTIVE.search(o).group(0))
    elif pv < po and av > ao:
        out.append("passive «… by» came back active")
    has = lambda stem, t: re.search(r"(?<!\w)" + stem, t) is not None  # noqa: E731
    for a, b in OPPOSITES:
        for x, y in ((a, b), (b, a)):
            if has(x, o) and not has(y, o) and has(y, v):
                out.append(f"«{x}» became «{y}»")
    return out


def claim_changes(original, variant):
    """(hedges dropped, boosters added), as written, when the variant has fewer hedges or
    more boosters in all than the original: «may» -> «might» is the same claim, «may» -> «»
    a firmer one."""
    count = lambda rx, t: collections.Counter(m.group(0) for m in rx.finditer(norm(t)))  # noqa: E731
    ho, hv = count(HEDGES, original), count(HEDGES, variant)
    bo, bv = count(BOOSTERS, original), count(BOOSTERS, variant)
    hedges = sorted((ho - hv).elements()) if sum(ho.values()) > sum(hv.values()) else []
    boosters = sorted((bv - bo).elements()) if sum(bv.values()) > sum(bo.values()) else []
    return hedges, boosters


# Capitalized words that are not proper nouns even when they do not open a sentence.
NOT_PROPER = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "y", "o", "en",
    "a", "al", "por", "para", "con", "sin", "que", "se", "su", "sus", "lo", "es",
    "este", "esta", "estos", "estas", "ese", "esa", "como", "pero", "si", "no",
    "the", "an", "of", "and", "or", "in", "on", "at", "for", "to", "with", "by", "from",
    "this", "that", "these", "those", "it", "its", "but", "if", "when", "while", "as",
}


APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "‐": "-", "‑": "-"})


def norm(s):
    """Lowercase and without accents, curly apostrophes straight, to compare regardless of
    spelling."""
    s = unicodedata.normalize("NFD", s.lower().translate(APOSTROPHES))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# British and American spellings of the same word match each other in a concept:
# «realised» finds «realized», «optimiser's» finds «optimizer's», «modelling» «modeling».
FLEX = ((re.compile(r"(?<=\w)i[sz](?=(?:e|es|ed|er|ers|ing|ation|ations|able)$)"), "i[sz]"),
        (re.compile(r"(?<=\w)y[sz](?=(?:e|es|ed|er|ers|ing)$)"), "y[sz]"),
        (re.compile(r"(?<=[aeiou])ll(?=(?:ing|ed|er|ers)$)"), "ll?"))


def _word(w):
    """One word of a concept as a regex: hyphens match a hyphen, a space or nothing
    («on-site» = «on site» = «onsite»), and British and American spellings match."""
    out = []
    for piece in w.split("-"):
        stem = re.sub(r"'s$", "", piece)
        rx = re.escape(stem)
        for pat, repl in FLEX:
            m = pat.search(stem)
            if m:
                rx = re.escape(stem[:m.start()]) + repl + re.escape(stem[m.end():])
                break
        out.append(rx + (re.escape(piece[len(stem):]) if stem != piece else ""))
    return r"[\s-]?".join(out)


def pattern(term):
    """Whole word (optional plural), flexible spaces. With a trailing *, matches
    by prefix. So "ser" does not match "servicio". A term of two plain words also matches
    the orders English moves it into: «outage cost*» finds «the cost of outages», and
    «on-site microgrid» «microgrids on-site» (a real run lost 3 of 10 tries to those)."""
    raw = term.strip()
    term = norm(term).strip()
    prefix = term.endswith("*")
    parts = [_word(p) for p in term.rstrip("*").split()]
    if not prefix and re.search(r"[^aeiou]y$", parts[-1]):
        parts[-1] = parts[-1][:-1] + "(?:y|ie)"  # policy, policies
    elif not prefix and parts[-1].endswith("z"):
        parts[-1] = parts[-1][:-1] + "(?:z|c(?=es))"  # luz, luces
    end = "" if prefix else r"(?:e?s)?(?!\w)"
    body = r"[\s-]+".join(parts) + end
    words = raw.rstrip("*").split()
    if len(words) == 2 and raw == raw.lower() and all(re.fullmatch(r"[a-z][a-z-]*", w) for w in words):
        a, b = parts
        moved = [b + (r"\w*" if prefix else r"(?:e?s)?") + r"\s+of\s+(?:the\s+|an?\s+)?" + a + r"(?:e?s)?(?!\w)"]
        if "-" in words[0]:  # an adjective that also goes after the noun
            moved.append(b + (r"\w*" if prefix else r"(?:e?s)?") + r"\s+" + a + r"(?!\w)")
        body = "(?:" + "|".join([body] + moved) + ")"
    return re.compile(r"(?<!\w)" + body)


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


def numbers_lost(original, variant):
    """Figures of the original that the variant has fewer times, once per missing
    occurrence: «2020» twice in the original and once in the variant is one «2020» lost.
    Only digits and numerals: «two or three days» is the concepts file's job."""
    have, _ = figures(variant)
    want, spelled = figures(original)
    return [spelled[k] for k, n in (want - have).items() for _ in range(n)]


# Counts written in words, for what a version adds: «teams of three agents» where the
# original never said three is an invented fact. «one» is left out (a pronoun as often as a
# number), and so is «once» (Spanish eleven, English «one time»).
WORD_VALUES = {w: str(i) for lang in NUMBER_WORDS.values() for i, w in enumerate(lang)
               if i >= 2 and w != "once"}
WORD_VALUES.update({w: str(v) for w, v in TENS.items() if v > 1})


def _counts_in_words(text):
    """Counter of the values written as words, and the first spelling of each."""
    found = [w for w in re.findall(r"[a-z]+", norm(text)) if w in WORD_VALUES]
    spelled = {}
    for w in found:
        spelled.setdefault(WORD_VALUES[w], w)
    return collections.Counter(WORD_VALUES[w] for w in found), spelled


def numbers_added(original, variant):
    """Figures the variant has more times than the original: an invented year, amount,
    percentage, or a count in words («teams of three agents» where the original had only
    «all three methods»). Digits and words are counted together, so «two» -> «2» is not new.
    Only additions: a paraphrase may drop a count in words («all three» -> «each»)."""
    have, spelled = figures(variant)
    want, _ = figures(original)
    have_w, spelled_w = _counts_in_words(variant)
    want_w, _ = _counts_in_words(original)
    extra = (have + have_w) - (want + want_w)
    return [spelled.get(k) or spelled_w[k] for k, n in extra.items() for _ in range(n)]


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


SMALL_WORDS = {"of", "and", "the", "for", "to", "in", "on", "a", "an", "de", "del", "la", "el",
               "los", "las", "y", "en", "por", "para"}
ACRONYM = re.compile(r"\(([A-Z][A-Za-z0-9]*[A-Z][A-Za-z0-9]*?)s?(?=[,;)])")


def definitions(text):
    """[(long form, acronym)] the text defines, like «Markov Decision Process (MDP)» or
    «a large language model (LLM, Claude…)»: the words before the bracket whose initials
    spell the acronym. A rewrite that keeps «LLM» and drops «large language model» has lost
    the definition a paper must give at first use."""
    found = []
    for m in ACRONYM.finditer(text):
        acr = m.group(1)
        letters = [c.lower() for c in acr if c.isalpha() and (c.isupper() or c.isdigit())] or \
            [c.lower() for c in acr if c.isalpha()]
        words = re.findall(r"[\w’'-]+", text[max(0, m.start() - 160):m.start()])
        for n in range(1, min(len(words), len(letters) + 4) + 1):
            tail = words[-n:]
            initials = [p[0].lower() for w in tail if w.lower() not in SMALL_WORDS
                        for p in w.split("-") if p]
            if initials == letters and tail[0].lower() not in SMALL_WORDS:
                long_form = " ".join(tail)
                if (long_form, acr) not in found:
                    found.append((long_form, acr))
                break
    return found


YEAR = r"(?:1[89]\d{2}|20\d{2})[a-z]?"
UPPER = "A-ZÀ-ÖØ-ÞŁŚŠŹŽŻČĆŘŐŰĞŞ"  # capitals that start a surname: Álvarez, Øster, Šimić
SURNAME = r"(?:(?:van|von|de|del|der|da|di|du|le|la|dos)\s+)*[" + UPPER + r"][\w'’-]+"
AUTHORS = (SURNAME + r"(?:\s*,\s*" + SURNAME + r")*(?:\s*,?\s*(?:and|&|y|e)\s+" + SURNAME
           + r")?(?:\s+et\s+al\.?)?(?:['’]s?)?")
NARRATIVE = re.compile(r"(" + AUTHORS + r")\s+\(" + YEAR + r"(?:[,;]\s*(?:pp?\.\s*)?\d+(?:[–-]\d+)?)?\)")
NOT_NAMES = set("""however recently similarly likewise moreover furthermore additionally conversely
notably specifically thus therefore hence indeed also finally first second third later earlier
previously subsequently overall together instead meanwhile here there this these those that the
in on at as by for from of to with following according since after before during while when where
which our we et al además asimismo también recientemente igualmente posteriormente finalmente
primero según como desde para por con en el la los las un una""".split())


def cited_authors(text):
    """[(citation, surname)] of every narrative citation («Wang (2021) reports», «Lee and
    Park (2019)», «Smith et al. (2020, p. 4)»): the model sees them as words, since a lone
    placeholder in the middle of a sentence came back as «… are noisy [3]», and its year
    is a figure; a try that drops a surname loses who said it."""
    found = []
    for m in NARRATIVE.finditer(text):
        names = [n for n in re.findall(r"[%s](?:['’][%s])?[\w-]+" % (UPPER, UPPER), m.group(1))
                 if norm(n) not in NOT_NAMES]  # «O’Brien» is one name
        cite = m.group(0)[m.group(0).find(names[0]):] if names else ""  # «Recently, » left out
        for name in names:
            if (cite, name) not in found:
                found.append((cite, name))
    return found


def with_definitions(concepts, text):
    """The concepts plus every long form the text defines, and every author it cites by
    name. A concept that accepts the acronym instead («large language model | LLM») does
    not count: a paper still has to spell the long form out where it defines it, and a
    real run turned «a large language model (LLM, …)» into «an LLM»."""
    exact = {norm(variants[0]) for _, variants in concepts if len(variants) == 1}
    extra = [(f"{lf} ({acr})", [lf]) for lf, acr in definitions(text) if norm(lf) not in exact]
    names = {norm(v) for _, variants in concepts for v in variants}
    extra += [(cite, [name]) for cite, name in cited_authors(text) if norm(name) not in names]
    return list(concepts) + extra


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
    ap.add_argument("--word-limit", dest="word_limit", type=int, metavar="N",
                    help="fail if a version has more than N words (a journal's abstract limit)")
    ap.add_argument("--list", "--listar", dest="list", action="store_true",
                    help="show the concepts and exit")
    args = ap.parse_args()

    try:
        texts = {}
        for f in [args.original] + args.variants:
            # accents as letters and 60\% as 60% in LaTeX; a Word file's text, paragraph by paragraph
            texts[f] = blocks.plain(blocks.read(f), blocks.format_of(f))
        concepts = (
            load_concepts(args.concepts)
            if args.concepts
            else extract_concepts(texts[args.original])
        )
    except (OSError, ValueError, KeyError) as e:
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
    concepts = with_definitions(concepts, texts[args.original])  # «Markov Decision Process (MDP)»

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
    added_neg = [(f, sorted(negations(texts[f]) - neg_original)) for f in args.variants]
    added_neg = [(f, a) for f, a in added_neg if a]
    if added_neg:
        print("\nNEGATIONS the version added (an inversion often starts here; read each one):")
        for f, a in added_neg:
            print(f"  {short_name(f, 30)}: " + ", ".join(f"«{x}»" for x in a))
    def by_paragraph(a, b):
        """Claim changes paragraph by paragraph: a hedge added in one does not hide one
        dropped in another."""
        pa = [x for x in re.split(r"\n[ \t]*\n", a.strip()) if x.strip()]
        pb = [x for x in re.split(r"\n[ \t]*\n", b.strip()) if x.strip()]
        if len(pa) != len(pb):
            return claim_changes(a, b)
        hedges, boosters = [], []
        for x, y in zip(pa, pb):
            h, bo = claim_changes(x, y)
            hedges += h
            boosters += bo
        return sorted(hedges), sorted(boosters)
    claims = [(f, *by_paragraph(texts[args.original], texts[f])) for f in args.variants]
    claims = [(f, h, b) for f, h, b in claims if h or b]
    if claims:
        print("\nCLAIM STRENGTH changed (a paper's claim made firmer is a changed claim; read each):")
        for f, hedges, boosters in claims:
            print(f"  {short_name(f, 30)}:"
                  + (f" hedges dropped {', '.join(f'«{x}»' for x in hedges)}" if hedges else "")
                  + (";" if hedges and boosters else "")
                  + (f" added {', '.join(f'«{x}»' for x in boosters)}" if boosters else ""))
    def flips_by_paragraph(a, b):
        pa = [x for x in re.split(r"\n[ \t]*\n", a.strip()) if x.strip()]
        pb = [x for x in re.split(r"\n[ \t]*\n", b.strip()) if x.strip()]
        if len(pa) != len(pb):
            return comparison_changes(a, b)
        return [c for x, y in zip(pa, pb) for c in comparison_changes(x, y)]
    flips = [(f, flips_by_paragraph(texts[args.original], texts[f])) for f in args.variants]
    flips = [(f, c) for f, c in flips if c]
    if flips:
        print("\nCOMPARISONS that may have flipped (who outperforms whom? review.py shows where):")
        for f, changes in flips:
            print(f"  {short_name(f, 30)}: " + "; ".join(changes))
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

    words = {f: len(re.findall(r"\w+(?:[-'’]\w+)*", t)) for f, t in texts.items()}
    print("\nWORDS: " + ", ".join(
        f"{short_name(f, 30)} {words[f]}" + ("" if f == args.original else
                                             f" ({words[f] - words[args.original]:+d})")
        for f in files))
    over = [f for f in args.variants if args.word_limit and words[f] > args.word_limit]
    if over:
        failed = True
        print(f"  Over the limit of {args.word_limit}: " + ", ".join(short_name(f, 30) for f in over)
              + ". Regenerate the longest paragraph or cut a word or two by hand.")

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

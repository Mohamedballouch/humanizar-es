#!/usr/bin/env python3
"""Joins the sentences of each paragraph, the way someone writes in one go. No models.
In Spanish and English (it detects the language).

Grammarly recognizes the rhythm of AI text: sentences of even length, each with its
own period. Joining them with «and» / «y» (or with «, but» / «, pero» where it fits)
erases that rhythm without adding a single spelling or punctuation error. Applied
after scripts/rewrite.py, it took two full essays to 0% and 10% on Grammarly
(references/evidence.md). On the original text, without rewrite.py, it is not
enough (57%).

Respects proper nouns: it does not lowercase them if they are in --concepts or if
they appear capitalized mid-sentence in the text. Markdown code, tables, headings and
quotations are left as they are; list items are joined one by one. In a LaTeX file
(.tex) only the prose is joined: math, citations, references and every command are held as
placeholders (scripts/latex.py), and everything outside the paragraphs stays byte for byte.

usage:
  python3 scripts/join.py rewritten.txt -o final.txt --concepts concepts.txt
"""
import argparse
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blocks  # noqa: E402
import check  # noqa: E402
import latex  # noqa: E402
import word  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # so a Windows console does not choke on «» or ñ
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")

# Per language: words that can be capitalized mid-sentence («San Cristobal de Las
# Casas», «The Hague») but are common words when they start a sentence; the
# connectors used to join; and what is not flagged as a possible proper noun.
LANGUAGES = {
    "es": {
        "common": set("""El La Los Las Lo Un Una Unos Unas De Del Al A En Y O Con Por Para Sin
        Su Sus Mi Mis Este Esta Estos Estas Ese Esa Esos Esas Esto Eso No Si Que""".split()),
        "and": "y", "but": ("Pero",), "contrast": ("Sin embargo, ",),
        "addition": {"Además": "además", "Asimismo": "además", "También": "también"},
        "always_proper": set(),
        "no_warn": set("""Antes Mientras Cuando Aunque Quizá Quizás Hoy Ahora Así Luego
        Entonces Incluso Tampoco Nunca Siempre Todo Toda Todos Todas Cada Otro Otra Más
        Menos Muy Desde Hasta Entre Sobre Tras Ante Según Durante Como Donde""".split()),
        "hints": set("de la que el en y los las del se por un una con para es".split()),
    },
    "en": {
        "common": set("""The A An This That These Those It Its In On At For Of To With By From
        As If When While And Or But Not No Our Their His Her We They He She You What Which
        There Here Some Many Most Each Every Such""".split()),
        "and": "and", "but": ("But", "Yet"),
        "contrast": ("However, ", "Nevertheless, ", "Nonetheless, ", "Even so, "),
        "addition": {"Also": "also", "Also,": "also"},
        "always_proper": {"I", "I'm", "I've", "I'd", "I'll"},
        "no_warn": set("""Before After Today Now Then Even Still Never Always Every Each
        Other Another More Less Very Since Until Between Over During How Where Why Once
        Instead Rather Despite Although Though Because Nevertheless Ultimately Finally
        Meanwhile Similarly Consequently Therefore Thus Yet So""".split()),
        "hints": set("the and of to is that in it for with as on are this be".split()),
    },
}
COMMON = LANGUAGES["es"]["common"]  # backward compatibility

# --pauses: sentences that already open with one of these change the idea, so a period
# goes there first; inside a block they are joined with «;» keeping the connector.
OPENERS = {
    "es": ("Sin embargo,", "No obstante,", "Por lo tanto,", "Por tanto,", "Por ello,", "Por eso,",
           "Así,", "Así también,", "Así pues,", "De esta forma,", "De esta manera,", "De este modo,",
           "Es decir,", "Por ejemplo,", "Por otro lado,", "Por otra parte,", "En cambio,",
           "Entonces,", "En primer lugar,", "En segundo lugar,", "En tercer lugar,", "Primero,",
           "Segundo,", "Tercero,", "Finalmente,", "Por último,", "En conclusión,", "Además,",
           "Asimismo,", "También,", "Incluso,", "Por el contrario,", "Con todo,", "Ahora bien,"),
    "en": ("However,", "Therefore,", "Thus,", "So,", "For example,", "For instance,", "In contrast,",
           "By contrast,", "On the other hand,", "First,", "Second,", "Third,", "Firstly,",
           "Secondly,", "Thirdly,", "Finally,", "Lastly,", "In short,", "Also,", "Meanwhile,",
           "Instead,", "That is,", "As a result,", "Consequently,", "Nevertheless,",
           "Nonetheless,", "Even so,", "Still,", "Similarly,", "Likewise,", "In particular,",
           "At the same time,", "Otherwise,", "Hence,", "Accordingly,", "Ultimately,",
           "Overall,", "In conclusion,", "In the end,"),
}
# English openers that only add weight: «Moreover, the food was great» says the same as
# «the food was great» after «and». They are among the commonest tells of AI prose
# (Wikipedia, «Signs of AI writing»), so join.py leaves them out where a sentence opens
# with one. Spanish keeps «Además»: it is ordinary there and was measured that way.
FILLERS = {"es": (), "en": ("Additionally, ", "Moreover, ", "Furthermore, ", "In addition, ",
                            "Notably, ", "Importantly, ")}
ENUMERATORS = {"Primero,", "Segundo,", "Tercero,", "En primer lugar,", "En segundo lugar,",
               "En tercer lugar,", "Finalmente,", "Por último,", "First,", "Second,", "Third,",
               "Firstly,", "Secondly,", "Thirdly,", "Finally,", "Lastly,"}
# Plain joins inside a block rotate among connectors that never change the meaning.
NEUTRAL = {"es": (" y ", "; ", " y "), "en": (" and ", "; ", " and ")}


def opener(s, lang):
    return next((o for o in OPENERS[lang] if s.startswith(o)), None)


def split_blocks(sentences, pauses, rnd, lang):
    """Cut a paragraph into up to `pauses`+1 blocks of uneven length, cutting first where a
    sentence already opens with a connector. Every block keeps at least two sentences: a
    sentence left alone between two periods is read on its own, and the near-copies of the
    original hid inside a chain come out (measured: 6% in Grammarly, against 0% joined)."""
    n = len(sentences)
    allowed = range(2, n - 1)  # a cut at i leaves sentences[:i] and sentences[i:]
    natural = [i for i in allowed if opener(sentences[i], lang)]
    rnd.shuffle(natural)
    natural.sort(key=lambda i: opener(sentences[i], lang) not in ENUMERATORS)  # «Segundo,» first
    others = list(allowed)
    rnd.shuffle(others)
    cuts = []
    for i in natural + others:
        if len(cuts) == pauses:
            break
        if i not in cuts and all(abs(i - c) >= 2 for c in cuts):
            cuts.append(i)
    return [0] + sorted(cuts)


# «Dr. Smith», «Sr. García», «e.g. Slack», «John F. Kennedy», «J.R.R. Tolkien», «9 a.m.
# Everyone», «EE.UU. Allí», «cap. VI»: the period does not close the sentence.
ABBREVIATION = re.compile(r"(?:^|\s)(?:Mr|Mrs|Ms|Dr|Prof|St|Sr|Sra|Srta|Dra|Lic|Ing|vs|etc|"
                          r"approx|aprox|e\.g|i\.e|U\.S|U\.K|p\.ej|Jr|Inc|Ltd|Corp|Fig|Vol|"
                          r"al|cf|Gen|Gov|Sen|Rep|Mt|Ud|Uds|Sto|Sta|Rev|Lt|Col|Capt|Sgt|Hon|"
                          r"cap|lib|pág|págs|núm|ed|eds|op|cit|ibid)\.$", re.I)
INITIAL = re.compile(r"(?:^|[\s.(«\"“'])[A-ZÁÉÍÓÚÑ]\.$")
DOTTED = re.compile(r"(?:^|\s)(?:\w{1,3}\.){2,}$")  # a.m., D.C., EE.UU., U.S.A.
BARE_NUMBER = re.compile(r"(?:^|\s)\(?\d{1,3}[.)]$")  # «1. Open the box. 2. Remove the tray.»


def no_period_end(s):
    """True if the period that ends `s` does not end a sentence (or there is none)."""
    return (not s.endswith(".") or s.endswith("...") or bool(ABBREVIATION.search(s))
            or bool(INITIAL.search(s)) or bool(DOTTED.search(s))
            or bool(BARE_NUMBER.search(s)))


def core(word):
    """The word a name check looks at: «Microsoft's» -> «Microsoft», «I’m» -> «I»,
    «¿Juan» -> «Juan»; «O'Brien» stays whole."""
    m = re.match(r"[¿¡«\"“(]*([\w-]+(?:['’][A-ZÁÉÍÓÚÑ][\w-]*)?)", word)
    return m.group(1) if m else word


def keeps_capital(word, proper):
    """«AI», «COVID-19», «iPhone», «McDonald's» and known names keep their capitals when a
    sentence that opens with them is joined; «aI tools» would be a visible error."""
    word = core(word)
    return word in proper or any(c.isupper() for c in word[1:])


def lower_first(s):
    """«La serie» -> «la serie»; «¿Vienes?» -> «¿vienes?»: the capital is after ¿ or ¡."""
    i = len(s) - len(s.lstrip("¿¡"))
    return s[:i] + s[i:i + 1].lower() + s[i + 1:]


def drop_fillers(sentences, lang):
    out = []
    for s in sentences:
        f = next((x for x in FILLERS[lang] if s.startswith(x)), None)
        if f and len(s) > len(f):
            s = s[len(f):]
            if not keeps_capital(s.split()[0], ()):  # «Moreover, iPhone sales» -> «iPhone sales»
                s = s[0].upper() + s[1:]
        out.append(s)
    return out


# Dashes as the universal connector are a tell of AI prose in English. --no-dashes turns
# a dash between words into a comma; ranges (1990–2000, 1939 – 1945), dashes that open a
# line (dialogue, lists) and dialogue paragraphs are left alone.
DASH = re.compile(r"[ \t]*—[ \t]*|[ \t]+(?:–|--)[ \t]+")


def replace_dashes(paragraph):
    if paragraph.lstrip().startswith(("—", "–", "-")):  # dialogue
        return paragraph

    def comma(m):
        before, after = paragraph[:m.start()], paragraph[m.end():]
        if (not before.strip() or before.endswith("\n")
                or (before[-1:].isdigit() and after[:1].isdigit())):
            return m.group(0)
        return ", "

    out = DASH.sub(comma, paragraph)
    out = re.sub(r":[ \t]*,[ \t]*", ": ", out)
    out = re.sub(r",\s*,", ",", out)
    out = re.sub(r",\s*([.;:!?)\]»”\"])", r"\1", out)
    out = re.sub(r"([(\[«“])\s*,\s*", r"\1", out)
    return out


def detect_language(text):
    words = re.findall(r"[a-záéíóúñü]+", text.lower())
    counts = {lang: sum(w in c["hints"] for w in words) for lang, c in LANGUAGES.items()}
    return max(counts, key=counts.get)


def proper_nouns(text, concepts=(), lang="es"):
    common = LANGUAGES[lang]["common"]
    found = re.findall(r"(?<=[a-záéíóúñü,;:] )([A-ZÁÉÍÓÚÑ][\w'’-]+)", text)
    mid = {core(w) for w in found} - common
    mid |= LANGUAGES[lang]["always_proper"]
    for _, variants in concepts:
        for v in variants:
            for w in v.rstrip("*").split():
                if w[:1].isupper() and w not in common:
                    mid |= {w, core(w)}
    return mid


def join_paragraph(paragraph, proper, p=1.0, rnd=None, max_words=400, doubtful=None, lang="es"):
    rnd = rnd or random.Random(7)
    c = LANGUAGES[lang]
    sentences = drop_fillers(re.split(r"(?<=\.) (?=[A-ZÁÉÍÓÚÑ¿¡])", paragraph.strip()), lang)
    out = [sentences[0]]
    for s in sentences[1:]:
        prev = out[-1]
        w = s.split()[0]
        base = w.strip(",;:")
        if (no_period_end(prev) or BARE_NUMBER.match(s) or rnd.random() >= p
                or len(prev.split()) + len(s.split()) > max_words):
            out.append(s)
            continue
        body = prev[:-1]
        contrast = next((x for x in c["contrast"] if s.startswith(x)), None)
        if base in c["but"]:
            out[-1] = body + f", {base.lower()} " + s[len(w) + 1:]
        elif contrast:
            out[-1] = body + ", " + c["but"][0].lower() + " " + s[len(contrast):]
        elif w in c["addition"] or base in c["addition"]:
            out[-1] = (body + f" {c['and']} " + c["addition"].get(w, c["addition"].get(base))
                       + " " + s[len(w) + 1:])
        elif base.lower() == c["and"] and base[:1].isupper():
            out[-1] = body + f" {c['and']} " + s[len(w) + 1:]
        else:
            nxt = s if keeps_capital(base, proper) else lower_first(s)
            if doubtful is not None and not keeps_capital(base, proper):
                doubtful.append(core(base))
            out[-1] = body + f" {c['and']} " + nxt
    return " ".join(out)


def join_with_pauses(paragraph, proper, pauses, rnd, doubtful=None, lang="es"):
    """2-3 periods per paragraph instead of one: blocks of uneven length; inside each
    block, sentences that open with a connector keep it after «;», the rest rotate
    among «y» and «;»."""
    sentences = drop_fillers(re.split(r"(?<=\.) (?=[A-ZÁÉÍÓÚÑ¿¡])", paragraph.strip()), lang)
    starts = split_blocks(sentences, pauses, rnd, lang) + [len(sentences)]
    blocks = []
    for a, b in zip(starts, starts[1:]):
        out = sentences[a]
        for s in sentences[a + 1:b]:
            if no_period_end(out) or BARE_NUMBER.match(s):
                out += " " + s
                continue
            w = s.split()[0].strip(",;:")
            o = opener(s, lang)
            if w in LANGUAGES[lang]["but"]:  # «Pero Heráclito…» joins as «, pero Heráclito…»
                out = out[:-1] + ", " + w.lower() + " " + s[len(s.split()[0]) + 1:]
                continue
            if w == LANGUAGES[lang]["and"].capitalize():  # «And so…» joins as «and so…», not «and and»
                out = out[:-1] + " " + LANGUAGES[lang]["and"] + s[len(w):]
                continue
            if o:
                glue = "; "
            else:
                glue = NEUTRAL[lang][rnd.randrange(len(NEUTRAL[lang]))]
            if keeps_capital(w, proper):
                nxt = s
            else:
                nxt = lower_first(s)
                if doubtful is not None and not o:
                    doubtful.append(core(w))
            out = out[:-1] + glue + nxt
        blocks.append(out)
    return " ".join(blocks)


# A footnote or citation placeholder right after a full stop («batch.[3] Moreover») hides the
# sentence end from the joins; it moves before the stop while joining, and back after it in
# the sentences that still end there. Only the moved ones: an IEEE «[12].» stays as written.
AFTER_STOP = re.compile(r"\.((?:\[\d+\])+)(?= |$)")


def markers_before_period(text):
    moved = set(AFTER_STOP.findall(text))
    return AFTER_STOP.sub(lambda m: m.group(1) + ".", text), moved


def markers_after_period(text, moved):
    if not moved:
        return text
    return re.sub(r"((?:\[\d+\])+)\.(?= |$)",
                  lambda m: "." + m.group(1) if m.group(1) in moved else m.group(0), text)


def join_text(text, concepts=(), p=1.0, seed=7, max_words=400, doubtful=None, lang=None,
              pauses=None, no_dashes=False, fmt="text", only=None, words_per_period=None):
    """doubtful: if it is a list, it receives the words that were lowercased without
    appearing that way anywhere else in the text (possible proper nouns).
    lang: "es", "en" or None to detect it. no_dashes: dashes between words become commas.
    fmt: "text" (plain text or Markdown) or "latex". only: the paragraph numbers to join
    (a set), leaving the rest as they are; None joins them all. words_per_period: with
    pauses, a long paragraph keeps more periods, about one per that many words (a 300-word
    abstract with --pauses 2 alone came out with a 150-word sentence)."""
    frame, paragraphs = blocks.parse(text, fmt)
    lang = lang or detect_language(" ".join(blocks.prose_of(x, fmt) for x in paragraphs))
    c = LANGUAGES[lang]
    rnd = random.Random(seed)
    source = blocks.plain(text, fmt)
    proper = proper_nouns(source, concepts, lang)
    lowered = []

    def prose(x):
        x = replace_dashes(x) if no_dashes else x
        x, moved = markers_before_period(x)
        if pauses:
            n = pauses
            if words_per_period:
                n = max(pauses, round(len(x.split()) / words_per_period) - 1)
            return markers_after_period(join_with_pauses(x, proper, n, rnd, lowered, lang), moved)
        return markers_after_period(join_paragraph(x, proper, p, rnd, max_words, lowered, lang), moved)

    def one(x):
        if fmt not in ("latex", "docx"):
            return prose(x)
        codec = latex if fmt == "latex" else word  # placeholders in, the same pieces back
        visible, pieces = codec.protect(x)
        joined = prose(visible)
        return x if joined == visible else (codec.restore(joined, pieces) or x)

    out = []
    for n, x in enumerate(paragraphs, 1):
        if only is not None and n not in only:
            out.append(x)
            continue
        k = blocks.kind(x, fmt)
        if k == "list":
            out.append(blocks.rebuild([(m, one(t) if t else t) for m, t in blocks.items(x, fmt)],
                                      fmt))
        else:
            out.append(one(x) if k == "prose" else x)
    output = blocks.unparse(frame, out)
    if doubtful is not None:
        words = set(re.findall(r"\w+", source))
        doubtful.extend(sorted({w for w in lowered if w.lower() not in words
                                and w not in c["common"] | c["no_warn"]}))
    return output


def main():
    ap = argparse.ArgumentParser(description="Joins the sentences of each paragraph with «and».")
    ap.add_argument("input")
    ap.add_argument("-o", "--output", "--salida", dest="output", required=True)
    ap.add_argument("--concepts", "--conceptos", dest="concepts",
                    help="concepts file (its proper nouns are respected)")
    ap.add_argument("--ratio", "--proporcion", dest="ratio", type=float, default=1.0,
                    help="fraction of joins to make (1.0, the measured one; 0.6 gave 66%% on Grammarly)")
    ap.add_argument("--max-words", "--maximo", dest="max_words", type=int, default=400,
                    help="maximum words per joined sentence")
    ap.add_argument("--lang", "--idioma", dest="lang", choices=sorted(LANGUAGES),
                    help="es or en (detected by default)")
    ap.add_argument("--pauses", "--pausas", dest="pauses", type=int,
                    help="leave this many periods per paragraph (2 or 3) in blocks of uneven "
                    "length, instead of joining everything; reads better")
    ap.add_argument("--words-per-period", dest="words_per_period", type=int, metavar="N",
                    help="with --pauses: a long paragraph keeps about one period per N words "
                         "(try 55 for an abstract); not measured against detectors yet")
    ap.add_argument("--only", help="join only these paragraphs (e.g. 4,7), the numbers rewrite.py "
                    "--only uses; the rest stay as they are")
    ap.add_argument("--no-dashes", "--sin-rayas", dest="no_dashes", action="store_true",
                    help="turn dashes between words (—, – and --) into commas; for English text "
                    "whose author does not use them")
    args = ap.parse_args()

    text = blocks.read(args.input)
    concepts = check.load_concepts(args.concepts) if args.concepts else []
    doubtful = []
    fmt = blocks.format_of(args.input)
    lang = args.lang or detect_language(" ".join(blocks.prose_of(x, fmt)
                                                 for x in blocks.parse(text, fmt)[1]))
    try:
        only = {int(n) for n in args.only.split(",") if n.strip()} if args.only else None
    except ValueError:
        print(f"ERROR: --only takes paragraph numbers like 4,7; got {args.only}", file=sys.stderr)
        return 2
    joined = join_text(text, concepts, args.ratio, max_words=args.max_words, doubtful=doubtful,
                       lang=lang, pauses=args.pauses, no_dashes=args.no_dashes, fmt=fmt,
                       only=only, words_per_period=args.words_per_period)
    blocks.write(args.output, joined, args.input)
    count = lambda t: len(re.findall(r"[.!?](?:\s|$)", blocks.plain(t, fmt)))  # noqa: E731
    print(f"Written: {args.output} ({count(text)} sentences -> {count(joined)}, language: {lang})")
    if doubtful:
        print("REVIEW: these were lowercased and do not appear that way in the text; if they "
              f"are proper nouns, add them to --concepts: {', '.join(doubtful)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""LaTeX papers: rewrite the prose, keep everything else byte for byte.

  parse(text)        -> (frame, paragraphs), with unparse(frame, paragraphs) == text
  protect(paragraph) -> (visible, pieces): inline LaTeX as placeholders [1], [2]…
  restore(r, pieces) -> the paragraph in LaTeX again, or None if r broke a placeholder

The frame is everything that is not a paragraph of prose: the preamble, \\section lines,
equations, figures, tables, algorithms, code, theorems and proofs, comments, blank lines,
the bibliography, and what follows \\end{document}. It is never touched. A paragraph is
body text, the abstract, or a list (itemize, enumerate, description), and only its prose
reaches the model: math ($x$, \\(…\\)), citations, references, labels, footnotes, \\emph{…}
and every other command become placeholders, and a try that loses, repeats or adds one is
not used. So math, citations and cross-references cannot change.

Accent macros (\\'e, \\~n, {\\'\\i}) are read as the letters they stand for: a rewritten
paragraph writes «é» and «ñ», which LaTeX reads as UTF-8 (the default since 2018).
Standard library only.
"""
import re

KEEP_ENVS = set("""
equation equation* align align* alignat alignat* gather gather* multline multline* flalign
flalign* eqnarray eqnarray* displaymath math split cases subequations dmath dmath*
figure figure* table table* tabular tabular* tabularx longtable wrapfigure wraptable
subfigure subtable sidewaysfigure sidewaystable algorithm algorithm* algorithm2e algorithmic
lstlisting verbatim Verbatim verbatim* minted tikzpicture pgfpicture forest thebibliography
comment center flushleft flushright minipage theorem lemma proposition corollary definition
proof remark example claim conjecture assumption hypothesis axiom notation titlepage
appendices filecontents filecontents* frame tcolorbox mdframed quote quotation verse
""".split())
LIST_ENVS = {"itemize", "enumerate", "description"}
PROSE_ENVS = {"abstract", "acknowledgments", "acknowledgements", "acks", "document"}

BEGIN = re.compile(r"\\begin\s*\{([^}]+)\}")
END = r"\\end\s*\{%s\}"
COMMENT_LINE = re.compile(r"^\s*%")
COMMAND = re.compile(r"\\([A-Za-z@]+)\*?")
PLACEHOLDER = re.compile(r"\[(\d+)\]")


def _group(text, i, open_, close):
    """Index just after the balanced group that starts at text[i] == open_, or -1."""
    depth = 0
    j = i
    while j < len(text):
        c = text[j]
        if c == "\\":
            j += 2
            continue
        if c == open_:
            depth += 1
        elif c == close:
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return -1


def command_end(text, i):
    """End of the command at text[i] == '\\' with its [optional] and {mandatory} arguments."""
    m = COMMAND.match(text, i)
    if not m:
        return min(i + 2, len(text))  # \%, \\, \, and the like
    j = m.end()
    while j < len(text) and text[j] in "[{":
        k = _group(text, j, text[j], "]" if text[j] == "[" else "}")
        if k < 0:
            break
        j = k
    return j


def _only_commands(line):
    """True for a line made only of commands with their arguments, and maybe a comment:
    «\\section{Results}\\label{sec:res}», «\\vspace{1em}», «\\maketitle»."""
    s = line.strip()
    if not s.startswith("\\"):
        return False
    i = 0
    while i < len(s):
        if s[i] == "%":
            return True
        if s[i].isspace():
            i += 1
            continue
        if s[i] != "\\":
            return False
        i = command_end(s, i)
    return True


def _env_end(lines, start, name):
    """Index of the line that closes environment `name` opened at lines[start]."""
    end = re.compile(END % re.escape(name))
    begin = re.compile(r"\\begin\s*\{%s\}" % re.escape(name))
    depth = 0
    for k in range(start, len(lines)):
        depth += len(begin.findall(lines[k])) - len(end.findall(lines[k]))
        if depth <= 0:
            return k
    return len(lines) - 1


def parse(text):
    """(frame, paragraphs) with len(frame) == len(paragraphs) + 1."""
    lines = text.splitlines(keepends=True)
    chunks = []  # ("frame" | "para", text)
    para = []

    def flush():
        if para:
            chunks.append(("para", "".join(para)))
            para.clear()

    def frame(s):
        flush()
        chunks.append(("frame", s))

    has_body = any(re.match(r"\s*\\begin\s*\{document\}", ln) for ln in lines)
    i, in_body = 0, not has_body
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not in_body:
            frame(line)
            in_body = bool(re.match(r"\s*\\begin\s*\{document\}", line))
            i += 1
            continue
        if re.match(r"\s*\\end\s*\{document\}", line):
            frame("".join(lines[i:]))
            break
        if not stripped or COMMENT_LINE.match(line):
            frame(line)
            i += 1
            continue
        if stripped.startswith("\\iffalse"):
            k = next((k for k in range(i, len(lines)) if lines[k].strip().startswith("\\fi")),
                     len(lines) - 1)
            frame("".join(lines[i:k + 1]))
            i = k + 1
            continue
        if stripped.startswith(("\\[", "$$")):
            close = "\\]" if stripped.startswith("\\[") else "$$"
            rest = stripped[2:]
            k = i if close in rest else next(
                (k for k in range(i + 1, len(lines)) if close in lines[k]), len(lines) - 1)
            frame("".join(lines[i:k + 1]))
            i = k + 1
            continue
        m = BEGIN.search(line)
        if m:
            name = m.group(1).strip()
            if name in PROSE_ENVS and _only_commands(line):
                frame(line)
                i += 1
                continue
            k = _env_end(lines, i, name)
            body = "".join(lines[i:k + 1])
            nested = BEGIN.findall(body)[1:]
            if (name in LIST_ENVS and stripped.startswith("\\begin") and not nested
                    and re.search(END % re.escape(name) + r"\s*$", body)):
                flush()
                lead = body[:len(body) - len(body.lstrip())]
                trail = body[len(body.rstrip()):]
                if lead:
                    chunks.append(("frame", lead))
                chunks.append(("para", body.strip()))
                chunks.append(("frame", trail))
            elif name in PROSE_ENVS:  # \begin{abstract} Text… on one line: prose
                para.append(line)
                i += 1
                continue
            else:
                frame(body)
            i = k + 1
            continue
        if _only_commands(line):
            frame(line)
            i += 1
            continue
        para.append(line)
        i += 1
    flush()

    # A paragraph's own leading and trailing whitespace belongs to the frame.
    frame_out, paras = [""], []
    for kind, s in chunks:
        if kind == "frame":
            frame_out[-1] += s
            continue
        core = s.strip()
        lead = s[:len(s) - len(s.lstrip())]
        trail = s[len(s.rstrip()):]
        if not core:
            frame_out[-1] += s
            continue
        frame_out[-1] += lead
        paras.append(core)
        frame_out.append(trail)
    return frame_out, paras


def unparse(frame, paragraphs):
    out = [frame[0]]
    for p, f in zip(paragraphs, frame[1:]):
        out += [p, f]
    return "".join(out)


def is_list(p):
    m = BEGIN.match(p)
    return bool(m) and m.group(1).strip() in LIST_ENVS


ITEM = re.compile(r"\\item\b")


def items(p):
    """(prefix, text) pairs of a list paragraph: prefix is the LaTeX before the item's
    text («\\begin{itemize}\\n  \\item »), the last pair holds «\\end{itemize}» with no text.
    "".join(prefix + text) gives the list back."""
    starts = [m.start() for m in ITEM.finditer(p)]
    end = re.search(r"\\end\s*\{[^}]+\}\s*$", p)
    stop = end.start() if end else len(p)
    pairs, cursor = [], 0
    for n, s in enumerate(starts):
        j = s + len("\\item")
        if j < len(p) and p[j] == "[":
            k = _group(p, j, "[", "]")
            j = k if k > 0 else j
        while j < len(p) and p[j] in " \t\n":
            j += 1
        nxt = starts[n + 1] if n + 1 < len(starts) else stop
        body = p[j:nxt]
        text = body.rstrip()
        pairs.append((p[cursor:j], text))
        cursor = j + len(text)
    pairs.append((p[cursor:], ""))
    return pairs


def rebuild(pairs):
    return "".join(prefix + text for prefix, text in pairs)


ACCENTS = {"'": "\u0301", "`": "\u0300", "^": "\u0302", '"': "\u0308", "~": "\u0303",
           "c": "\u0327", "=": "\u0304", ".": "\u0307", "u": "\u0306", "v": "\u030c"}
ACCENT = re.compile(r"\{?\\([`'^\"~=.]|[cuv](?=[{ ]))\s*\{?\\?([A-Za-z])\}?\}?")
ESCAPES = {"\\%": "%", "\\&": "&", "\\#": "#", "\\_": "_", "\\$": "$"}


def unaccent(text):
    """«Mart\\'{\\i}nez» -> «Martínez», «Espa\\~na» -> «España»."""
    import unicodedata

    def letter(m):
        base = "i" if m.group(2) == "i" and "\\i" in m.group(0) else m.group(2)
        return unicodedata.normalize("NFC", base + ACCENTS[m.group(1)])
    return ACCENT.sub(letter, text)


def protect(p):
    """(visible, pieces): the prose of paragraph p for the model, with each inline LaTeX
    piece replaced by «[n]», and the pieces to put back. A piece that starts with «~»
    («Fig.~\\ref{f}», «al.~\\cite{x}») is shown after a space and takes that space back."""
    text = unaccent(p)
    taken = {int(n) for n in PLACEHOLDER.findall(text)}  # «see [1]» typed by the author
    n = max(taken, default=0)
    out, pieces, i = [], {}, 0

    def piece(s):
        nonlocal n
        n += 1
        pieces[n] = s
        return f"[{n}]"

    while i < len(text):
        c = text[i]
        two = text[i:i + 2]
        if c == "%":  # a comment runs to the end of its line, newline included
            j = text.find("\n", i)
            j = len(text) if j < 0 else j + 1
            out.append(piece(text[i:j]) + " ")
            i = j
        elif two in ("$$", "\\[", "\\("):
            close = {"$$": "$$", "\\[": "\\]", "\\(": "\\)"}[two]
            j = text.find(close, i + 2)
            j = len(text) if j < 0 else j + 2
            out.append(piece(text[i:j]))
            i = j
        elif c == "$":
            j = i + 1
            while j < len(text) and text[j] != "$":
                j += 2 if text[j] == "\\" else 1
            j = min(j + 1, len(text))
            out.append(piece(text[i:j]))
            i = j
        elif two in ESCAPES:
            out.append(ESCAPES[two])
            i += 2
        elif c == "~" and text[i + 1:i + 2] == "\\":
            j = command_end(text, i + 1)
            out.append(" " + piece(text[i:j]))
            i = j
        elif c == "~":
            out.append(" ")
            i += 1
        elif c == "\\":
            j = command_end(text, i)
            out.append(piece(text[i:j]))
            i = j
        elif c == "{":
            j = _group(text, i, "{", "}")
            j = len(text) if j < 0 else j
            out.append(piece(text[i:j]))
            i = j
        elif text.startswith("---", i):  # the em dash, as --no-dashes and tells.py see it
            out.append("—")
            i += 3
        elif text.startswith("``", i):
            out.append("“")
            i += 2
        elif text.startswith("''", i):
            out.append("”")
            i += 2
        elif c == "\n":
            out.append(" ")
            i += 1
        else:
            out.append(c)
            i += 1
    visible = re.sub(r"[ \t]+", " ", "".join(out)).strip()
    return visible, pieces


def strip_placeholders(visible):
    """The visible text without its placeholders, for the checks that read words and
    figures (a placeholder's number is not a figure of the text)."""
    return re.sub(r" ?\[\d+\]", "", visible)


def problem(visible, rewritten, pieces):
    """«(LaTeX changed)» if the try lost, repeated or invented a placeholder, or wrote
    LaTeX of its own (a backslash or a brace); None if it can be restored."""
    if re.search(r"[\\{}]", rewritten):
        return "(LaTeX changed)"
    for k in pieces:
        if len(re.findall(r"\[%d\]" % k, rewritten)) != 1:
            return "(LaTeX changed)"
    known = {int(x) for x in PLACEHOLDER.findall(visible)}
    if any(int(x) not in known for x in PLACEHOLDER.findall(rewritten)):
        return "(LaTeX changed)"
    return None


def _escape(text):
    text = text.replace("—", "---").replace("–", "--")
    text = re.sub(r"(?<!\\)([%&#_$])", r"\\\1", text)
    text = text.replace("“", "``").replace("”", "''").replace("‘", "`")
    text = re.sub(r'(^|[\s(\[])"', r"\1``", text)
    return text.replace('"', "''")


def restore(rewritten, pieces):
    """The rewritten visible text back in LaTeX: special characters escaped, each
    placeholder replaced by its piece. None if a placeholder is missing or doubled, or
    the text holds LaTeX of its own."""
    if re.search(r"[\\{}]", rewritten) or any(
            len(re.findall(r"\[%d\]" % k, rewritten)) != 1 for k in pieces):
        return None
    text = _escape(rewritten)
    for k, s in pieces.items():
        pat = r" ?\[%d\]" % k if s.startswith("~") else r"\[%d\]" % k
        text = re.sub(pat, lambda m, s=s: s, text, count=1)
    return sentence_lines(re.sub(r"\n ", "\n", text))


SHORT = {"al", "fig", "figs", "eq", "eqs", "e.g", "i.e", "vs", "dr", "mr", "mrs", "ms", "prof",
         "sec", "tab", "ref", "cf", "etc", "approx", "no", "vol", "pp", "ch", "cap", "pág"}


def sentence_lines(text):
    """One sentence per line, for a paragraph rewritten or joined here: LaTeX reads a line
    end as a space, and a diff of the paper then shows what changed sentence by sentence.
    Never breaks inside a comment, math, braces or after an abbreviation («et al.»)."""
    out, depth, math, comment, i = [], 0, False, False, 0
    while i < len(text):
        c = text[i]
        if comment:
            comment = c != "\n"
        elif c == "\\":
            out.append(text[i:i + 2])
            i += 2
            continue
        elif c == "%":
            comment = True
        elif c == "$":
            math = not math
        elif c == "{":
            depth += 1
        elif c == "}":
            depth = max(0, depth - 1)
        elif (c == " " and not math and depth == 0 and out and out[-1][-1:] in ".!?"
              and re.match(r"[A-Z¿¡\\]", text[i + 1:i + 2])):
            word = re.search(r"(\S+)[.!?]$", "".join(out[-12:]))
            if not word or (word.group(1).lower() not in SHORT and len(word.group(1)) > 1):
                out.append("\n")
                i += 1
                continue
        out.append(c)
        i += 1
    return "".join(out)


def plain(text):
    """Text to compare a paper with its rewrite: accents as letters, escapes as the
    characters they print («60\\%» -> «60%»), «~» as a space. Everything else stays, so
    the figures inside equations and tables count on both sides."""
    text = unaccent(text)
    for k, v in ESCAPES.items():
        text = text.replace(k, v)
    return text.replace("~", " ").replace("``", "“").replace("''", "”")

#!/usr/bin/env python3
"""PDF in, PDF out: the conversions around the pipeline. The kind of conversion comes from
the file extensions:

  convert.py paper.pdf -o 00-original.md    PDF -> text the pipeline can read (Markdown)
  convert.py 02-final.md -o 02-final.pdf    text or Markdown -> PDF, through LaTeX
  convert.py 02-final.tex -o 02-final.pdf   your LaTeX paper -> PDF (figures, .bib and all)

A paper's LaTeX source is always the better input: rewrite.py and join.py read .tex
directly and keep the equations, tables, citations and layout byte for byte. A PDF only
holds positioned text, so from a PDF this script recovers the prose: it joins the lines of
each paragraph, undoes end-of-line hyphenation, drops page numbers and running headers,
marks headings, and puts what is not prose (equations, table cells, the references) in
fenced blocks, which the pipeline keeps as they are. The PDF made back from that text is a
clean single-column document with the same words; it does not reproduce the original's
layout, figures or typeset equations.

Reading a PDF needs pdftotext (poppler: `brew install poppler`, `apt install
poppler-utils`, or on Windows `winget install oschwartz10612.Poppler`) or the pypdf package.
Making a PDF needs a LaTeX engine: tectonic, latexmk, pdflatex, xelatex or lualatex (TeX
Live, MacTeX or MiKTeX). Without one the .tex is still written: upload it to Overleaf.
"""
import argparse
import collections
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blocks  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # so a Windows console does not choke on «» or ñ
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")


# ---------------------------------------------------------------- PDF -> text

def pdf_pages(path):
    """The text of each page, from pdftotext or, without it, pypdf."""
    tool = shutil.which("pdftotext")
    if tool:
        r = subprocess.run([tool, "-enc", "UTF-8", path, "-"], capture_output=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.decode("utf-8", "replace").strip() or "pdftotext failed")
        return r.stdout.decode("utf-8", "replace").split("\f")
    try:
        import pypdf
    except ImportError:
        raise RuntimeError("reading a PDF needs pdftotext (poppler) or the pypdf package: "
                           "brew install poppler, apt install poppler-utils, or "
                           "python3 -m pip install pypdf")
    return [page.extract_text() or "" for page in pypdf.PdfReader(path).pages]


HEADING = re.compile(r"^(?:(?:\d+(?:\.\d+)*\.?|[IVX]+\.|[A-Z]\.)\s+)?"
                     r"(?:Abstract|Resumen|Introduction|Introducción|Related [Ww]ork|Background|"
                     r"Methods?|Methodology|Metodología|Materials and [Mm]ethods|Results|"
                     r"Resultados|Discussion|Discusión|Conclusions?|Conclusiones|"
                     r"Acknowledg(?:e)?ments?|Agradecimientos|References|Referencias|"
                     r"Bibliography|Bibliografía|Appendix|Apéndice|Anexo)\b.{0,60}$")
NUMBERED = re.compile(r"^(?:\d+(?:\.\d+)*\.?|[IVX]+\.)\s+[A-ZÁÉÍÓÚÑ][^.!?]{0,80}$")
END_OF_TEXT = re.compile(r"^(?:\d+(?:\.\d+)*\.?\s+)?(?:References|Referencias|Bibliography|"
                         r"Bibliografía)\s*$", re.I)
CAPTION = re.compile(r"^(?:Figure|Fig\.|Table|Tabla|Figura|Algorithm|Algoritmo)\s*\d+[.:]")


def _repeated_lines(pages):
    """Running headers and footers: the same line (digits aside) near the top or the bottom
    of most pages."""
    if len(pages) < 3:
        return set()
    seen = collections.Counter()
    for page in pages:
        lines = [ln.strip() for ln in page.splitlines() if ln.strip()]
        for ln in set(lines[:3] + lines[-3:]):
            if not re.fullmatch(r"[\d\s.,()]+", ln):  # a bare number is a figure or a page
                seen[re.sub(r"\d+", "#", ln)] += 1    # number, never a running header
    return {ln for ln, n in seen.items() if n >= max(3, len(pages) // 2)}


def _prose_ratio(text):
    """Share of the characters that are letters: about 0.8 in prose, far less in an
    equation or a row of table cells."""
    chars = [c for c in text if not c.isspace()]
    return sum(c.isalpha() for c in chars) / max(1, len(chars))


LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
# a bullet, as fonts leave it: a real one, a control or private-use character (LaTeX's
# itemize bullet comes out as U+0088), or a dash or asterisk
BULLET = re.compile("^(?:[•◦▪▫‣∙·●○■□\u0080-\u009f\ue000-\uf8ff]|[-–*])\\s+")
MATHY = re.compile(r"[=≤≥≈≠±×∑∫√∈∀∃→←↔∞∂∇]")


def normalize(text):
    """Ligatures as letters («ﬁ» -> «fi»), a dotless ı with an accent as «í», composed
    accents (NFC): what a PDF's fonts leave in the extracted text."""
    import unicodedata
    for k, v in LIGATURES.items():
        text = text.replace(k, v)
    text = text.replace("ı́", "í").replace("ı́", "í").replace("­", "")
    return unicodedata.normalize("NFC", text)


def _kind(s, median):
    """What one extracted line looks like: blank, heading, item, caption, math, short
    (a table cell, a label, a title line) or text."""
    if not s:
        return "blank"
    words = s.split()
    if len(words) <= 12 and (HEADING.match(s) or NUMBERED.match(s)):
        return "heading"
    if BULLET.match(s):
        return "item"
    if CAPTION.match(s):
        return "caption"
    if (_prose_ratio(s) < 0.6 or re.fullmatch(r"\(\d+(?:\.\d+)?\)", s)
            or (MATHY.search(s) and len(words) < 15 and not s.endswith("."))):
        return "math"
    if len(s) < 0.5 * median and not re.search(r"[.!?:;,]$", s):
        return "short"
    return "text"


def _page_numbers(pages):
    """{(page index, line index)} of the page numbers: the first or last non-empty line of a
    page holding a number that counts up with the pages. A lone number anywhere else, like
    a table cell («38») or a section number, is a figure and stays."""
    found = {}
    for i, page in enumerate(pages):
        lines = page.splitlines()
        full = [k for k, ln in enumerate(lines) if ln.strip()]
        for k in ({full[0], full[-1]} if full else ()):
            s = " ".join(lines[k].split())
            m = re.fullmatch(r"(?:page\s+)?(\d{1,4})(?:\s*(?:/|of|de)\s*\d{1,4})?", s, re.I)
            if m:
                found.setdefault(int(m.group(1)) - i, set()).add((i, k))
    if not found:
        return set()
    offset, hits = max(found.items(), key=lambda kv: len(kv[1]))
    return hits if len(hits) >= max(2, len(pages) // 2) or len(pages) == 1 else set()


def pdf_to_text(pages, removed=None):
    """Markdown from the pages of a PDF, built line by line: paragraphs on one line each,
    «## » headings, «- » list items, captions as «> » quotations, and equations, table
    cells, title lines and the references fenced, so the pipeline keeps them as they are.
    removed, if a list, receives the page numbers and running headers left out."""
    removed = [] if removed is None else removed
    noise = _repeated_lines(pages)
    numbers = _page_numbers(pages)
    lines = []
    for i, page in enumerate(pages):
        for k, ln in enumerate(normalize(page).splitlines()):
            s = " ".join(ln.split())
            if (i, k) in numbers or (s and re.sub(r"\d+", "#", s) in noise):
                removed.append(s)  # a page number or a running header
                continue
            lines.append(s)
        lines.append(None)  # a page break: it ends a paragraph only after a full stop
    # «1» on its own line above «Introduction» is the section's number: «1 Introduction»
    for k, s in enumerate(lines):
        if s and re.fullmatch(r"\d{1,2}(?:\.\d{1,2})*\.?", s):
            j = next((j for j in range(k + 1, min(k + 4, len(lines))) if lines[j]), None)
            if j is not None and HEADING.match(lines[j]) and len(lines[j].split()) <= 10:
                lines[j], lines[k] = s + " " + lines[j], ""
    long = sorted(len(s) for s in lines if s and len(s) >= 20)
    median = long[len(long) // 2] if long else 60
    all_text = " ".join(s for s in lines if s)
    hyphenated = set(re.findall(r"\w+-\w+", all_text))

    def joined(parts):
        out = parts[0]
        for s in parts[1:]:
            m = re.search(r"(\w+)-$", out)
            if m and re.match(r"[a-záéíóúñü]", s):
                word = m.group(1) + "-" + re.match(r"\w*", s).group(0)
                # «inter-national» was hyphenation; «self-reported» is written so elsewhere
                out = (out if word in hyphenated else out[:-1]) + s
            else:
                out += " " + s
        return out

    out, cur, cur_kind, fence, in_refs = [], [], None, [], False

    def close():
        nonlocal cur, cur_kind
        if cur:
            text = joined(cur)
            out.append({"item": "- ", "caption": "> "}.get(cur_kind, "") + text)
        cur, cur_kind = [], None

    def close_fence():
        nonlocal fence
        if fence:
            out.append("```text\n" + "\n".join(fence) + "\n```")
            fence = []

    for idx, s in enumerate(lines):
        if s is None:
            if cur and re.search(r"[.!?:]$", cur[-1]):
                close()
            continue
        k = _kind(s, median)
        if in_refs:
            if s:
                fence.append(s)
            continue
        if k == "heading" and END_OF_TEXT.match(s):
            close()
            close_fence()
            out.append("## " + s)
            in_refs = True  # the references are never rewritten
            continue
        if k == "blank":
            close()
            continue
        if k in ("math", "short"):
            nxt = next((x for x in lines[idx + 1:] if x), "")
            lone_title = k == "short" and not fence and _kind(nxt, median) == "text" and not cur
            if not lone_title:
                close()
                fence.append(s)
                continue
        close_fence()
        if k == "heading":
            close()
            out.append("## " + s)
        elif k in ("item", "caption"):
            close()
            cur, cur_kind = [BULLET.sub("", s) if k == "item" else s], k
        elif k == "short":
            close()
            out.append(s)
        else:
            # a short last line ending in a full stop ends its paragraph
            if cur and re.search(r"[.!?]$", cur[-1]) and len(cur[-1]) < 0.85 * median:
                close()
            cur.append(s)
            cur_kind = cur_kind or "text"
    close()
    close_fence()
    merged = []  # consecutive items make one list
    for block in out:
        if merged and block.startswith("- ") and merged[-1].split("\n")[-1].startswith("- "):
            merged[-1] += "\n" + block
        else:
            merged.append(block)
    return "\n\n".join(merged) + "\n"


# ---------------------------------------------------------------- text -> LaTeX

SPECIAL = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$", "&": r"\&",
           "#": r"\#", "^": r"\^{}", "_": r"\_", "%": r"\%", "~": r"\textasciitilde{}"}


GREEK = dict(zip("αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΦΨΩ",
                 "alpha beta gamma delta varepsilon zeta eta theta iota kappa lambda mu nu xi pi "
                 "rho sigma tau upsilon phi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma "
                 "Phi Psi Omega".split()))
SYMBOLS = {"≤": "leq", "≥": "geq", "≈": "approx", "≠": "neq", "±": "pm", "×": "times",
           "∑": "sum", "∫": "int", "√": "surd", "∈": "in", "∀": "forall", "∃": "exists",
           "→": "rightarrow", "←": "leftarrow", "↔": "leftrightarrow", "∞": "infty",
           "∂": "partial", "∇": "nabla", "·": "cdot", "−": "-"}


SUBSCRIPT = dict(zip("₀₁₂₃₄₅₆₇₈₉₊₋", "0123456789+-"))
SUPERSCRIPT = dict(zip("⁰⁴⁵⁶⁷⁸⁹⁺⁻ⁿ", "0456789+-n"))  # ¹ ² ³ are Latin-1 and print as they are


def escape(text):
    """Text for LaTeX: special characters escaped, Greek letters and math symbols as math
    (so pdflatex prints «α» and «≤» too), sub- and superscript digits as such («CO₂» keeps
    its 2), control characters left out."""
    out = []
    for c in text:
        if c in SUBSCRIPT:
            out.append("\\textsubscript{" + SUBSCRIPT[c] + "}")
        elif c in SUPERSCRIPT:
            out.append("\\textsuperscript{" + SUPERSCRIPT[c] + "}")
        elif c in SPECIAL:
            out.append(SPECIAL[c])
        elif c in GREEK:
            out.append("\\ensuremath{\\" + GREEK[c] + "}")
        elif c in SYMBOLS:
            out.append("\\ensuremath{" + ("\\" if SYMBOLS[c] != "-" else "") + SYMBOLS[c] + "}")
        elif ord(c) < 32 and c not in "\n\t" or 0x7f <= ord(c) <= 0x9f:
            continue
        else:
            out.append(c)
    return "".join(out)


def inline(text):
    """Markdown inline markup to LaTeX: **bold**, *italic*, `code`, [text](url)."""
    parts, pos = [], 0
    pattern = re.compile(r"\*\*(.+?)\*\*|(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)|`([^`]+)`|"
                         r"\[([^\]]+)\]\((\S+?)\)")
    for m in pattern.finditer(text):
        parts.append(escape(text[pos:m.start()]))
        bold, it, code, label, url = m.groups()
        if bold is not None:
            parts.append(r"\textbf{" + escape(bold) + "}")
        elif it is not None:
            parts.append(r"\emph{" + escape(it) + "}")
        elif code is not None:
            parts.append(r"\texttt{" + escape(code) + "}")
        else:
            parts.append(r"\href{" + url.replace("%", r"\%").replace("#", r"\#") + "}{"
                         + escape(label) + "}")
        pos = m.end()
    parts.append(escape(text[pos:]))
    return "".join(parts)


PREAMBLE = r"""\documentclass[11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\IfFileExists{lmodern.sty}{\usepackage{lmodern}}{}
\usepackage{textcomp}
\usepackage[margin=2.5cm]{geometry}
\usepackage[hidelinks]{hyperref}
\setlength{\parskip}{0.6em}
\setlength{\parindent}{0pt}
\begin{document}
"""


def text_to_latex(text):
    """A plain article from text or Markdown: headings, paragraphs, lists, quotations, and
    fenced or indented code (and the fenced references) as verbatim."""
    out = [PREAMBLE]
    for b in blocks.split(text):
        k = blocks.kind(b)
        if k == "heading":
            level = len(b) - len(b.lstrip("#")) if b.startswith("#") else 1
            title = b.lstrip("#").strip() if b.startswith("#") else b.split("\n")[0]
            cmd = {1: "section", 2: "section", 3: "subsection"}.get(level, "subsubsection")
            out.append(f"\\{cmd}*{{{inline(title)}}}\n")
        elif k == "list":
            pairs = blocks.items(b)
            env = "enumerate" if re.match(r"\s*\d", pairs[0][0]) else "itemize"
            body = "\n".join(f"  \\item {inline(t)}" for m, t in pairs if m.strip())
            intro = [inline(t) for m, t in pairs if not m.strip()]
            out.append("\n".join(intro + [f"\\begin{{{env}}}", body, f"\\end{{{env}}}"]) + "\n")
        elif k == "quote":
            quoted = " ".join(ln.lstrip()[1:].strip() for ln in b.split("\n"))
            out.append("\\begin{quote}\n" + inline(quoted) + "\n\\end{quote}\n")
        elif k in ("code", "table", "html"):
            lines = b.split("\n")
            if blocks.FENCE.match(lines[0]):
                lines = lines[1:-1] if len(lines) > 1 and blocks.FENCE.match(lines[-1]) else lines[1:]
            # \newline, not \\: a line that starts with «[1]» would be read as its argument
            body = " \\newline\n".join(escape(ln).replace("  ", "~ ") or "~" for ln in lines)
            out.append("\\begin{flushleft}\\small\\ttfamily\n" + body + "\n\\end{flushleft}\n")
        elif k == "rule":
            out.append("\\noindent\\rule{\\linewidth}{0.4pt}\n")
        elif _title(b):
            out.append(f"\\section*{{{inline(b)}}}\n")
        else:
            out.append(inline(" ".join(b.split())) + "\n")
    out.append("\\end{document}\n")
    return "\n".join(out)


def _title(b):
    return len(b.split()) <= 12 and not b.rstrip().endswith((".", "!", "?", "…", ":", ","))


# Characters pdflatex with T1 and textcomp can print; others (emoji, CJK) stop it, so for
# pdflatex they are left out with a warning. xelatex, lualatex and tectonic take them all.
def pdflatex_safe(text):
    ok = []
    dropped = 0
    for c in text:
        if (32 <= ord(c) < 0x7f or 0xa0 <= ord(c) < 0x250 or c in "\n\t–—‘’‚“”„†‡•…‰‹›€™"):
            ok.append(c)
        else:
            dropped += 1
    return "".join(ok), dropped


# ---------------------------------------------------------------- LaTeX -> PDF

def engine():
    """The first LaTeX engine on the PATH, as a name, or None."""
    for name in ("tectonic", "latexmk", "pdflatex", "xelatex", "lualatex"):
        if shutil.which(name):
            return name
    return None


def compile_tex(tex_path, pdf_path, name=None):
    """Compiles tex_path into pdf_path, running BibTeX when the paper has a .bib. The
    paper's own folder is the working folder, so its figures and .bib are found; the
    auxiliary files go to a temporary folder. Returns None, or the error to show."""
    name = name or engine()
    if not name:
        return ("no LaTeX engine found (tectonic, latexmk, pdflatex, xelatex or lualatex). "
                f"Install TeX Live, MacTeX or MiKTeX, or upload {tex_path} to Overleaf.")
    folder, base = os.path.split(os.path.abspath(tex_path))
    stem = os.path.splitext(base)[0]
    with tempfile.TemporaryDirectory() as out:
        def run(cmd, env=None):
            return subprocess.run(cmd, cwd=folder, capture_output=True, env=env,
                                  stdin=subprocess.DEVNULL)
        if name == "tectonic":
            r = run([name, "--outdir", out, base])
        elif name == "latexmk":
            r = run([name, "-pdf", "-interaction=nonstopmode", "-halt-on-error",
                     f"-outdir={out}", base])
        else:
            flags = [name, "-interaction=nonstopmode", "-halt-on-error", f"-output-directory={out}", base]
            r = run(flags)
            aux = os.path.join(out, stem + ".aux")
            if r.returncode == 0 and os.path.isfile(aux) and "\\bibdata" in open(
                    aux, encoding="utf-8", errors="replace").read() and shutil.which("bibtex"):
                env = dict(os.environ, BIBINPUTS=folder + os.pathsep, BSTINPUTS=folder + os.pathsep)
                subprocess.run(["bibtex", stem], cwd=out, capture_output=True, env=env)
                r = run(flags)
            if r.returncode == 0:
                r = run(flags)  # references and citations settle on the last run
        pdf = os.path.join(out, stem + ".pdf")
        if r.returncode != 0 or not os.path.isfile(pdf):
            log = os.path.join(out, stem + ".log")
            text = open(log, encoding="utf-8", errors="replace").read() if os.path.isfile(log) \
                else (r.stdout + r.stderr).decode("utf-8", "replace")
            errors = [ln for ln in text.splitlines() if ln.startswith("!")] or text.splitlines()[-15:]
            return f"{name} could not compile {tex_path}:\n  " + "\n  ".join(errors[:12])
        shutil.copyfile(pdf, pdf_path)
    return None


def figures_missing_from_pdf(text, pdf_path):
    """Figures of the text that the PDF does not print, read back from the PDF itself;
    [] when there is nothing to read it with. The PDF may add some (page numbers)."""
    import check
    try:
        printed = normalize("\n".join(pdf_pages(pdf_path)))
    except (RuntimeError, OSError):
        return []
    plain = re.sub(r"\\[a-z]+\{([^}]*)\}", r"\1", text)  # read **x** and `x` as x
    return check.numbers_lost(plain, printed)


# ---------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(description="PDF -> text, text -> PDF, LaTeX -> PDF.")
    ap.add_argument("input")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--engine", choices=("tectonic", "latexmk", "pdflatex", "xelatex", "lualatex"),
                    help="LaTeX engine for a PDF (the first one found by default)")
    args = ap.parse_args()
    src = os.path.splitext(args.input)[1].lower()
    dst = os.path.splitext(args.output)[1].lower()

    if src == ".pdf":
        if dst == ".pdf":
            print("ERROR: a PDF goes to text first (convert.py paper.pdf -o 00-original.md),\n"
                  "then through the pipeline, then back (convert.py 02-final.md -o final.pdf).",
                  file=sys.stderr)
            return 2
        try:
            pages = pdf_pages(args.input)
        except (RuntimeError, OSError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        removed = []
        text = pdf_to_text(pages, removed)
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text)
        parts = blocks.split(text)
        prose = sum(blocks.kind(b) == "prose" and not _title(b) for b in parts)
        kept = sum(blocks.kind(b) in ("code", "quote") for b in parts)
        print(f"Written: {args.output} ({len(pages)} pages, {prose} paragraphs of prose, "
              f"{kept} blocks kept as they are: equations, tables, captions, references)")
        import check
        raw = normalize("\n".join(pages))
        lost = check.numbers_lost(raw, text)
        for k in check.numbers_lost("\n".join(removed), ""):  # what the left-out lines held
            if k in lost:
                lost.remove(k)
        total = sum(check.figures(text)[0].values())
        print(f"Figures: {total} read; {len(removed)} page numbers and running headers left out.")
        if lost:
            print("WARNING: figures of the PDF that are not in the text: " + ", ".join(lost)
                  + ". Find them in the PDF and put them back before going on.")
        print("Read it before going on: text taken from a PDF can carry broken lines, "
              "table cells or\nheaders as prose. Fix the extraction here, before rewriting; "
              "the LaTeX source, if you\nhave it, is always the better input.")
        return 0

    if dst != ".pdf":
        print("ERROR: convert.py makes text from a .pdf, or a .pdf from .md, .txt or .tex",
              file=sys.stderr)
        return 2
    name = args.engine or engine()
    if src == ".tex":
        problem = compile_tex(args.input, args.output, name)
    else:
        with open(args.input, encoding="utf-8-sig") as fh:
            tex = text_to_latex(fh.read())
        if name == "pdflatex" or (name == "latexmk"):
            tex, dropped = pdflatex_safe(tex)
            if dropped:
                print(f"WARNING: {dropped} characters pdflatex cannot print (emoji and the like) "
                      "were left out; xelatex or lualatex keep them.")
        tex_path = os.path.splitext(args.output)[0] + ".tex"
        with open(tex_path, "w", encoding="utf-8") as fh:
            fh.write(tex)
        problem = compile_tex(tex_path, args.output, name)
        if problem:
            print(f"The LaTeX is in {tex_path}.", file=sys.stderr)
        else:
            with open(args.input, encoding="utf-8-sig") as fh:
                lost = figures_missing_from_pdf(fh.read(), args.output)
            if lost:
                print("WARNING: these figures of the text are not in the PDF: " + ", ".join(lost),
                      file=sys.stderr)
                return 1
    if problem:
        print(f"ERROR: {problem}", file=sys.stderr)
        return 2
    print(f"Written: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

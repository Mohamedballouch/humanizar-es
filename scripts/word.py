#!/usr/bin/env python3
"""Word files (.docx): which paragraphs are prose, and placeholders for everything else.

A .docx is a zip of XML parts, and only word/document.xml is touched: styles, images,
footnotes, comments, headers, numbering and a citation manager's data are copied byte for
byte, and so is every part of document.xml that is not a prose paragraph.

  read(path)                -> document.xml as text, with the file's paragraph styles
  write(path, xml, template)-> the template's zip with document.xml replaced
  parse(xml)                -> (frame, paragraphs), as latex.parse: unparse puts it back
  protect(p)                -> (visible, pieces): the paragraph's prose for the model
  restore(rewritten, pieces)-> the paragraph's XML again, or None if a placeholder broke
  plain(xml)                -> the document's text, for the checks that count figures

A paragraph of the body is prose unless it is a heading or a title, a caption, an entry of
a table of contents, a bibliography entry (by style, or after a «References» heading or
bold line), a quotation or code (by style), an equation, empty, inside a field that spans
paragraphs (a citation manager's bibliography, a table of contents), or holds tracked
changes or comments (accept and resolve those first: rewriting them would lose who changed
what). Tables, text boxes, section properties and Word's own document parts (a table of
contents, a bibliography or a cover page in a content control) are never touched; the
paragraphs of other content controls, where thesis templates keep an abstract, are prose.

Inside a prose paragraph, text in the paragraph's usual formatting is what the model
rewrites. Everything else becomes a placeholder «[n]» and comes back exactly as it was: a
word in italics, bold or superscript, a field (a Zotero, Mendeley or EndNote citation, a
cross-reference), an equation, a footnote reference, a hyperlink, an image. Bookmarks move
to the paragraph's edges; spelling marks are dropped.

Standard library only.
"""
import html
import os
import re
import zipfile

import latex

DOCUMENT, STYLES = "word/document.xml", "word/styles.xml"
MAIN = ("http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "http://purl.oclc.org/ooxml/wordprocessingml/main")
TAG = re.compile(r"<(/?)([A-Za-z_][\w.:-]*)((?:\s+[\w.:-]+\s*=\s*(?:\"[^\"]*\"|'[^']*'))*)\s*(/?)>")
PLACEHOLDER = latex.PLACEHOLDER
strip_placeholders = latex.strip_placeholders
unparse = latex.unparse


class Xml(str):
    """document.xml as text, with the paragraph styles of its file attached
    ({style id: (lowercase name, outline level or None)})."""
    styles = {}


def read(path):
    """document.xml of a .docx as an Xml string."""
    with zipfile.ZipFile(path) as z:
        xml = Xml(z.read(DOCUMENT).decode("utf-8"))
        names = set(z.namelist())
        xml.styles = styles_of(z.read(STYLES).decode("utf-8")) if STYLES in names else {}
    return xml


def write(path, xml, template):
    """The template's zip, entry by entry, with document.xml replaced by xml. The template
    may be the file being written: it is read whole first."""
    with zipfile.ZipFile(template) as z:
        entries = [(info, z.read(info.filename)) for info in z.infolist()]
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w") as z:
        for info, data in entries:
            z.writestr(info, xml.encode("utf-8") if info.filename == DOCUMENT else data)
    os.replace(tmp, path)


def prefix(xml):
    """«w:» for the usual Word file, «» if the main namespace is the default one."""
    m = re.search(r'xmlns(?::([\w.-]+))?="(%s)"' % "|".join(map(re.escape, MAIN)), xml)
    return (m.group(1) + ":") if m and m.group(1) else ("" if m else "w:")


def children(xml, start, end):
    """[(name, start, end)] of the elements directly inside xml[start:end]."""
    out, depth = [], 0
    for m in TAG.finditer(xml, start, end):
        closing, name, selfclosing = m.group(1), m.group(2), m.group(4)
        if closing:
            depth -= 1
            if depth == 0 and out:
                out[-1] = (out[-1][0], out[-1][1], m.end())
        elif selfclosing:
            if depth == 0:
                out.append((name, m.start(), m.end()))
        else:
            if depth == 0:
                out.append((name, m.start(), None))
            depth += 1
    return [c for c in out if c[2] is not None]


def inside(element):
    """(start, end) of what lies between an element's opening and closing tags."""
    first = TAG.match(element)
    if not first or first.group(4):
        return len(element), len(element)
    return first.end(), element.rindex("</")


def attribute(tag, name):
    m = re.search(r'%s\s*=\s*"([^"]*)"' % re.escape(name), tag)
    return m.group(1) if m else None


def styles_of(xml):
    """{paragraph style id: (lowercase name, outline level or None)}, levels inherited
    through «based on». Built-in names are English in styles.xml («heading 1», «caption»,
    «toc 1», «bibliography») whatever the language Word shows."""
    w = prefix(xml)
    raw = {}
    for m in re.finditer(r"<%sstyle\b([^>]*)>(.*?)</%sstyle>" % (w, w), xml, re.S):
        if attribute(m.group(1), w + "type") not in (None, "paragraph"):
            continue
        sid = attribute(m.group(1), w + "styleId")
        body = m.group(2)
        name = re.search(r'<%sname\s+%sval="([^"]*)"' % (w, w), body)
        based = re.search(r'<%sbasedOn\s+%sval="([^"]*)"' % (w, w), body)
        level = re.search(r'<%soutlineLvl\s+%sval="(\d+)"' % (w, w), body)
        raw[sid] = (name.group(1).lower() if name else (sid or "").lower(),
                    based.group(1) if based else None, int(level.group(1)) if level else None)
    out = {}
    for sid, (name, based, level) in raw.items():
        seen = 0
        while level is None and based in raw and seen < 10:
            level, based, seen = raw[based][2], raw[based][1], seen + 1
        out[sid] = (name, level if level is not None and level < 9 else None)
    return out


def style(p, w, styles):
    """(lowercase style name, outline level or None) of paragraph p."""
    m = re.search(r'<%spStyle\s+%sval="([^"]*)"' % (w, w), p)
    sid = m.group(1) if m else ""
    name, level = styles.get(sid, (sid.lower(), None))
    own = re.search(r'<%soutlineLvl\s+%sval="(\d+)"' % (w, w), p)
    if own and int(own.group(1)) < 9:
        level = int(own.group(1))
    if level is None and re.fullmatch(r"(?:heading|titre|berschrift|ttulo|titolo|kop)\s*(\d)", name):
        level = int(re.fullmatch(r"\D*(\d)", name).group(1)) - 1  # «Heading2» with no styles part
    return name, level


def text_of(p):
    """What a reader reads in an XML fragment: its text runs, tabs and breaks as spaces,
    deleted text and field instructions left out."""
    w = prefix_of_fragment(p)
    out = []
    # «w:t» is a text run, «m:t» the text of an equation (shown so a reader sees the formula)
    for m in re.finditer(r"<(?:%s|[\w.-]*m:)t(?:\s[^>]*)?>([^<]*)</(?:%s|[\w.-]*m:)t>|<%s(?:tab|br|cr)\b[^>]*/>"
                         % (w, w, w), p):
        out.append(html.unescape(m.group(1)) if m.group(1) is not None else " ")
    return "".join(out)


def prefix_of_fragment(p):
    m = re.match(r"\s*<([\w.-]+:)?p\b", p)
    return m.group(1) or "" if m else "w:"


def plain(xml):
    """The document's text, a blank line after each paragraph (in tables and text boxes
    too), for the checks that count figures and concepts on both sides."""
    w = prefix(xml)
    out = []
    for m in re.finditer(r"<%st(?:\s[^>]*)?>([^<]*)</%st>|</%sp>|<%s(?:tab|br|cr)\b[^>]*/>"
                         % (w, w, w, w), xml):
        if m.group(1) is not None:
            out.append(html.unescape(m.group(1)))
        elif m.group(0).startswith("</"):
            out.append("\n\n")
        else:
            out.append(" ")
    return re.sub(r"(?:[ \t]*\n){3,}", "\n\n", "".join(out)).strip() + "\n"


def why_kept(p, w, styles):
    """None for a prose paragraph, else what it is: «heading», «caption», «contents»,
    «bibliography», «quotation», «code», «equation», «empty», «tracked changes»,
    «comments»."""
    name, level = style(p, w, styles)
    if level is not None or name.startswith(("heading", "title", "subtitle")) or name in ("title", "subtitle"):
        return "heading"
    if "caption" in name or name == "table of figures":
        return "caption"
    if name.startswith(("toc", "index")):
        return "contents"
    if name.startswith("bibliograph"):
        return "bibliography"
    if "quot" in name or name == "block text":  # «Quote», «Intense Quote»; pandoc's «Block Text»
        return "quotation"
    if "code" in name or "preformatted" in name or name == "macro text":  # pandoc's «Source Code»
        return "code"
    if re.search(r"<%s(?:ins|del|moveFrom|moveTo|rPrChange|pPrChange)\b" % w, p):
        return "tracked changes"
    if re.search(r"<%s(?:commentRangeStart|commentReference)\b" % w, p):
        return "comments"
    if re.search(r"<[\w.-]*:?oMathPara\b", p):
        return "equation"
    if not text_of(p).strip():
        return "empty"
    return None


def paragraphs_of(xml, start, end, w):
    """(start, end) of the paragraphs of the body, in order, those inside a content
    control included: thesis templates put the abstract or whole chapters in one. Not
    those of a table, nor of a control that is one of Word's document parts (a table of
    contents, a bibliography, a cover page) or is locked."""
    for name, s, e in children(xml, start, end):
        if name == w + "p":
            yield s, e
        elif name == w + "sdt":
            el = xml[s:e]
            pr = re.search(r"<%ssdtPr\b.*?</%ssdtPr>" % (w, w), el, re.S)
            pr = pr.group(0) if pr else ""
            if "docPartGallery" in pr or re.search(
                    r'<%slock\s+%sval="(?:sdtContentLocked|contentLocked)"' % (w, w), pr):
                continue
            content = re.search(r"<%ssdtContent\b[^>]*>" % w, el)
            if content and not content.group(0).endswith("/>"):
                yield from paragraphs_of(xml, s + content.end(),
                                         s + el.rindex("</%ssdtContent>" % w), w)


def classify(xml):
    """[(start, end, None or why it is kept)] for every paragraph of the body, in order.
    The references zone and fields that span paragraphs are worked out here, where the
    paragraphs before are known."""
    import blocks  # the References heading words; imported here, blocks imports this module
    w = prefix(xml)
    styles = getattr(xml, "styles", {}) or {}
    body = re.search(r"<%sbody\b[^>]*>" % w, xml)
    if not body:
        return []
    end = xml.rfind("</%sbody>" % w)
    out, depth, zone = [], 0, None
    for s, e in paragraphs_of(xml, body.end(), end, w):
        p = xml[s:e]
        opened = len(re.findall(r'%sfldCharType="begin"' % w, p))
        closed = len(re.findall(r'%sfldCharType="end"' % w, p))
        spans = depth > 0 or opened > closed
        depth = max(0, depth + opened - closed)
        why = why_kept(p, w, styles)
        _, level = style(p, w, styles)
        words = re.sub(r"^[\s*_]*(?:[0-9IVX]+[.)]?\s+)?|[\s*_:.]*$", "", text_of(p).strip())
        # a short line in the body's style (a bold «References») is a heading to a reader
        line = why is None and len(words.split()) <= 4
        if why == "heading" or line:
            appendix = blocks.AFTER_REFERENCES.match(words) and (why == "heading" or not re.search(r"[,(]", words))
            if zone is not None and (appendix or (why == "heading" and (level is None or level <= zone))):
                zone = None
            if blocks.REFERENCES.fullmatch(words):
                zone = (level if level is not None else 0) if why == "heading" else 9
                why = why or "heading"
        if zone is not None and why is None:
            why = "bibliography"
        if spans and why is None:
            why = "field"
        out.append((s, e, why))
    return out


def parse(xml):
    """(frame, paragraphs): the prose paragraphs' XML, and everything else as frame."""
    frame, paras, last = [], [], 0
    for s, e, why in classify(xml):
        if why is None:
            frame.append(xml[last:s])
            paras.append(xml[s:e])
            last = e
    frame.append(xml[last:])
    return frame, paras


def kept_counts(xml):
    """{why: how many paragraphs} of the paragraphs left as they are, for the report."""
    counts = {}
    for _, _, why in classify(xml):
        if why in ("tracked changes", "comments", "field"):
            counts[why] = counts.get(why, 0) + 1
    return counts


class Pieces(dict):
    """{n: XML} of a paragraph's placeholders, with what restore needs in .meta."""
    meta = None


SIGNIFICANT_DROP = re.compile(r"<[\w.-]*:?(?:lang|noProof|rFonts|kern|szCs|bCs|iCs)\b[^>]*/>")


def signature(rpr):
    """A run's formatting, without what does not show (language, proofing marks, fonts of
    other scripts): two runs that differ only there are the same text to a reader."""
    return SIGNIFICANT_DROP.sub("", re.sub(r"\s+", " ", rpr)).replace(" ", "")


def protect(p):
    """(visible, pieces) for paragraph XML p: the text in the paragraph's usual formatting,
    with «[n]» for everything else, and the pieces to put back."""
    w = prefix_of_fragment(p)
    a, b = inside(p)
    open_tag = p[:a]
    ppr, segments, zero_start, zero_end = "", [], [], []
    field, depth = [], 0
    for name, s, e in children(p, a, b):
        el = p[s:e]
        local = name.split(":")[-1]
        if depth:                      # inside a field: everything is the field's
            field.append(el)
            depth += len(re.findall(r'fldCharType="begin"', el)) - len(re.findall(r'fldCharType="end"', el))
            if depth <= 0:
                segments.append(("piece", "".join(field)))
                field, depth = [], 0
            continue
        if local == "pPr":
            ppr = el
        elif local == "r":
            if 'fldCharType="begin"' in el:
                field = [el]
                depth = len(re.findall(r'fldCharType="begin"', el)) - len(re.findall(r'fldCharType="end"', el))
                if depth <= 0:
                    segments.append(("piece", el))
                    depth = 0
                continue
            ra, rb = inside(el)
            rpr = ""
            for cname, cs, ce in children(el, ra, rb):
                child = el[cs:ce]
                clocal = cname.split(":")[-1]
                if clocal == "rPr":
                    rpr = child
                elif clocal == "t":
                    ta, tb = inside(child)
                    segments.append(("text", html.unescape(child[ta:tb]), rpr))
                elif clocal in ("lastRenderedPageBreak", "softHyphen", "proofErr"):
                    continue
                else:
                    segments.append(("piece", "<%sr>%s%s</%sr>" % (w, rpr, child, w)))
        elif local in ("bookmarkStart", "permStart"):
            zero_start.append(el)
        elif local in ("bookmarkEnd", "permEnd"):
            zero_end.append(el)
        elif local == "proofErr":
            continue
        else:                          # hyperlink, fldSimple, oMath, sdt, smartTag, drawing…
            segments.append(("piece", el))
    if field:                          # a field still open at the end: keep it whole
        segments.append(("piece", "".join(field)))

    weight = {}
    for seg in segments:
        if seg[0] == "text":
            weight[signature(seg[2])] = weight.get(signature(seg[2]), 0) + len(seg[1].strip())
    base = max(weight, key=weight.get) if weight else ""
    base_rpr = next((seg[2] for seg in segments if seg[0] == "text" and signature(seg[2]) == base), "")

    def run_xml(text, rpr):
        return '<%sr>%s<%st xml:space="preserve">%s</%st></%sr>' % (
            w, rpr, w, html.escape(text, quote=False), w, w)

    items = []  # ("text", str) or ("piece", xml), adjacent pieces merged
    for seg in segments:
        if seg[0] == "text" and signature(seg[2]) == base:
            items.append(("text", seg[1]))
        else:
            xml = seg[1] if seg[0] == "piece" else run_xml(seg[1], seg[2])
            if items and items[-1][0] == "piece":
                items[-1] = ("piece", items[-1][1] + xml)
            elif len(items) > 1 and items[-1][0] == "text" and not items[-1][1].strip() \
                    and items[-2][0] == "piece":
                space = run_xml(items.pop()[1], base_rpr)
                items[-1] = ("piece", items[-1][1] + space + xml)
            else:
                items.append(("piece", xml))
    taken = [int(n) for n in PLACEHOLDER.findall("".join(t for k, t in items if k == "text"))]
    n = max(taken, default=0)
    pieces, out = Pieces(), []
    for kind, value in items:
        if kind == "text":
            out.append(value)
        else:
            n += 1
            pieces[n] = value
            out.append(f"[{n}]")
    visible = "".join(out)
    # a piece written against the word before it (a superscript citation, a footnote mark
    # after the period) stays against it: the model wrote «simulation [1]» for «simulation¹»
    glued = [k for k in pieces if re.search(r"\S\[%d\]" % k, visible)]
    pieces.meta = {"open": open_tag, "ppr": ppr, "rpr": base_rpr, "w": w, "glued": glued,
                   "start": "".join(zero_start), "end": "".join(zero_end)}
    return visible, pieces


def problem(visible, rewritten, pieces):
    """«(Word formatting changed)» if the try lost, repeated or invented a placeholder."""
    for k in pieces:
        if len(re.findall(r"\[%d\]" % k, rewritten)) != 1:
            return "(Word formatting changed)"
    known = {int(x) for x in PLACEHOLDER.findall(visible)}
    if any(int(x) not in known for x in PLACEHOLDER.findall(rewritten)):
        return "(Word formatting changed)"
    return None


def restore(rewritten, pieces):
    """The paragraph's XML with the rewritten text in its usual formatting and each piece
    where its placeholder is; None if a placeholder is missing or doubled."""
    if any(len(re.findall(r"\[%d\]" % k, rewritten)) != 1 for k in pieces):
        return None
    meta = pieces.meta
    for k in meta.get("glued", ()):
        rewritten = re.sub(r"\s+(?=\[%d\])" % k, "", rewritten)
    w, out = meta["w"], [meta["open"], meta["ppr"], meta["start"]]
    pos = 0
    for m in re.finditer(r"\[(\d+)\]", rewritten):
        k = int(m.group(1))
        if k not in pieces:
            continue
        out.append(_text_run(rewritten[pos:m.start()], meta))
        out.append(pieces[k])
        pos = m.end()
    out.append(_text_run(rewritten[pos:], meta))
    out += [meta["end"], "</%sp>" % w]
    return "".join(out)


def _text_run(text, meta):
    if not text:
        return ""
    w = meta["w"]
    return '<%sr>%s<%st xml:space="preserve">%s</%st></%sr>' % (
        w, meta["rpr"], w, html.escape(text, quote=False), w, w)


def prose_of(p):
    """The prose a reader reads in paragraph p, placeholders left out (for tells.py)."""
    return strip_placeholders(protect(p)[0])

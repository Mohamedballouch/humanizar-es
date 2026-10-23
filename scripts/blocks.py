#!/usr/bin/env python3
"""The blocks of a text: its paragraphs, and the Markdown pieces that are not prose.

Every script splits a text at blank lines. Three things go wrong with only that on
documentation, emails or posts: a fenced code block with a blank line inside becomes two
«paragraphs», code and tables get rewritten or joined like sentences, and a list is
rewritten into one run of prose that loses its items. Here a fenced block stays one
block, code, tables, headings, quotations, HTML and rules are kept as they are, and a
list is handled item by item with its markers.

  split(text)       -> [block, ...]   (what every script calls «paragraphs»)
  kind(block)       -> "prose" | "list" | "code" | "table" | "heading" | "quote" | "html" | "rule"
  items(block)      -> [(marker, text), ...] for a list
  rebuild(items)    -> the list again, from (marker, text) pairs

A LaTeX file (.tex) is read by scripts/latex.py instead: parse(text, "latex") gives the
paragraphs of prose and a frame with everything else, kept byte for byte, and
unparse(frame, paragraphs) puts the file back together. Every function here takes that
format as its last argument.

Standard library only.
"""
import os
import re

import latex

FENCE = re.compile(r"^\s*(```|~~~)")
MARKER = re.compile(r"^(\s*(?:[-*+•]|\d{1,3}[.)])\s+(?:\[[ xX]\]\s+)?)(.*)$")
HEADING = re.compile(r"^#{1,6}\s")
RULE = re.compile(r"^\s*(?:(?:-\s*){3,}|(?:\*\s*){3,}|(?:_\s*){3,})$")
PROSE = ("prose", "list")  # the kinds that are rewritten, joined and scanned


def format_of(path):
    """«latex» for a .tex file, «text» for anything else (plain text or Markdown)."""
    return "latex" if os.path.splitext(path)[1].lower() in (".tex", ".latex", ".ltx") else "text"


def parse(text, fmt="text"):
    """(frame, paragraphs): unparse(frame, paragraphs) writes the file back. For text, the
    frame is the blank line between paragraphs; for LaTeX, everything that is not prose."""
    if fmt == "latex":
        return latex.parse(text)
    paras = split(text)
    if not paras:
        return [text], []
    return [""] + ["\n\n"] * (len(paras) - 1) + ["\n"], paras


def unparse(frame, paragraphs):
    return latex.unparse(frame, paragraphs)


def split(text):
    """Blocks separated by blank lines; a fenced code block is one block even with blank
    lines inside. Prose blocks are stripped like before; code keeps its indentation."""
    out, current, fence = [], [], None

    def close():
        if current:
            block = "\n".join(current)
            out.append(block.strip("\n") if _is_code(block) else block.strip())
            current.clear()

    for line in text.splitlines():
        if fence:
            current.append(line)
            if line.strip().startswith(fence):  # the fence closes its own block
                fence = None
                close()
            continue
        m = FENCE.match(line)
        if m:
            close()  # a fence right under a paragraph still starts a block of its own
            fence = m.group(1)
            current.append(line)
            continue
        if not line.strip():
            close()
            continue
        current.append(line)
    close()
    return [b for b in out if b.strip()]


def _is_code(block):
    """Fenced, or two or more lines all indented. A single indented line is a paragraph:
    essays indent their first line with a tab."""
    lines = [ln for ln in block.split("\n") if ln.strip()]
    return bool(lines) and (bool(FENCE.match(lines[0])) or (
        len(lines) > 1 and all(ln.startswith(("    ", "\t")) for ln in lines)))


def kind(block, fmt="text"):
    if fmt == "latex":
        return "list" if latex.is_list(block) else "prose"
    lines = [ln for ln in block.split("\n") if ln.strip()]
    if not lines:
        return "prose"
    first = lines[0].lstrip()
    if _is_code(block):
        return "code"
    if all(ln.lstrip().startswith("|") for ln in lines):
        return "table"
    if len(lines) == 1 and HEADING.match(first):
        return "heading"
    if len(lines) == 2 and re.fullmatch(r"\s*(?:=+|-+)\s*", lines[1]):
        return "heading"  # setext: a line underlined with === or ---
    if all(ln.lstrip().startswith(">") for ln in lines):
        return "quote"
    if first.startswith("<") and lines[-1].rstrip().endswith(">"):
        return "html"
    if len(lines) == 1 and RULE.match(first):
        return "rule"
    # a list, or a line that introduces one («Three things matter:» and its items)
    start = 0 if MARKER.match(lines[0]) else 1
    if (start == 0 or (len(lines) > 2 and MARKER.match(lines[1]) and MARKER.match(lines[2]))) and \
            all(MARKER.match(ln) or ln.startswith((" ", "\t")) for ln in lines[start + 1:]):
        return "list"
    return "prose"


def items(block, fmt="text"):
    """(marker, text) for each item; a line that continues an item joins its text."""
    if fmt == "latex":
        return latex.items(block)
    out = []
    for line in block.split("\n"):
        if not line.strip():
            continue
        m = MARKER.match(line)
        if m:
            out.append([m.group(1), m.group(2).strip()])
        elif out:
            out[-1][1] = (out[-1][1] + " " + line.strip()).strip()
        else:
            out.append(["", line.strip()])
    return [(marker, text) for marker, text in out]


def rebuild(pairs, fmt="text"):
    if fmt == "latex":
        return latex.rebuild(pairs)
    return "\n".join(marker + text for marker, text in pairs)


def prose_of(block, fmt="text"):
    """The text a reader reads in a prose or list block, without the list markers (and,
    in LaTeX, without commands and math); "" for blocks that are not prose."""
    k = kind(block, fmt)
    texts = [t for _, t in items(block, fmt)] if k == "list" else [block] if k == "prose" else []
    if fmt == "latex":
        texts = [latex.strip_placeholders(latex.protect(t)[0]) for t in texts]
    return "\n".join(t for t in texts if t)

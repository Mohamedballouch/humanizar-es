#!/usr/bin/env python3
"""Step 6's hand fixes: one to three words of one paragraph, in any format.

  python3 scripts/fix.py 01-rewritten.docx 4 "the majority" "many"
  python3 scripts/fix.py 01-rewritten.docx 4 --show

A fix puts back what the model changed: a figure, a term, the original's spelling, a
dropped «not». Anything larger is refused: a paragraph that needs more is regenerated
(rewrite.py --only), because every word written by hand raises the detector score and a
sentence pasted back from the original is AI text again.

The words to replace must appear exactly once in the paragraph (add a neighbouring word to
make them unique). In a Word file they are matched in the paragraph's text as --show
prints it, where [1], [2]… stand for what a fix may not change: a word in italics or bold,
a citation, a link, an equation, a footnote. A fix keeps each of those exactly once. The
rest of the file is kept as it is, and a paragraph rewritten in parts keeps its parts
record (…parts.json), so `rewrite.py --only N --part K` still works after it.

Plain text, Markdown, LaTeX (.tex) and Word (.docx). Standard library only.
"""
import argparse
import difflib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blocks  # noqa: E402
import word  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # so a Windows console does not choke on «» or ñ
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")

MAX_WORDS = 3  # SKILL.md, step 6: a fix is one to three words


def changed_words(old, new):
    """Words replaced, removed or added between old and new («the majority» -> «many»: 2)."""
    a, b = old.split(), new.split()
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal")


def shown(p, fmt):
    """The paragraph as a fix sees it: in Word, its text with [n] for each piece."""
    return word.protect(p)[0] if fmt == "docx" else p


def legend(p):
    """What each [n] of a Word paragraph stands for, as a reader sees it."""
    pieces = word.protect(p)[1]
    return [f"[{n}] = «{' '.join(word.text_of(x).split()) or '(no text: a mark, a break or an image)'}»"
            for n, x in sorted(pieces.items())]


def apply(p, fmt, old, new):
    """(the paragraph fixed, None) or (None, why not)."""
    text = shown(p, fmt)
    count = text.count(old)
    if count != 1:
        where = " (in Word, words in italics, citations and links are [n]: see --show)" \
            if fmt == "docx" else ""
        return None, (f"«{old}» is in the paragraph {count} times; it must be there exactly once"
                      + (": add a neighbouring word" if count else where))
    fixed = text.replace(old, new, 1)
    if fmt != "docx":
        return fixed, None
    pieces = word.protect(p)[1]
    if word.problem(text, fixed, pieces):
        return None, "a fix keeps every [n] exactly once: it changes words, not formatting"
    return word.restore(fixed, pieces), None


def update_parts(path, n, old, new):
    """Keeps the parts record of paragraph n true to the fixed text; drops it if the words
    cross from one part into the next. Returns a note for the user, or None."""
    sidecar = path + ".parts.json"
    try:
        with open(sidecar, encoding="utf-8") as fh:
            saved = json.load(fh)
    except (OSError, ValueError):
        return None
    entry = saved.get(str(n))
    if not entry:
        return None
    hits = [k for k, t in enumerate(entry["text"]) if old in t]
    if len(hits) == 1 and entry["text"][hits[0]].count(old) == 1:
        entry["text"][hits[0]] = entry["text"][hits[0]].replace(old, new, 1)
        note = None
    else:
        del saved[str(n)]
        note = (f"The fix crosses two parts of paragraph {n}: its parts record is gone, so "
                f"redo it whole (--only {n}), not --part.")
    with open(sidecar, "w", encoding="utf-8") as fh:
        json.dump(saved, fh, ensure_ascii=False, indent=1)
    return note


def main():
    ap = argparse.ArgumentParser(description="One to three words of one paragraph, replaced.")
    ap.add_argument("file", help="the version to fix (01-rewritten, or 02-final for a connector)")
    ap.add_argument("paragraph", type=int, help="its number, as rewrite.py and review.py give it")
    ap.add_argument("old", nargs="?", help="the words to replace, exactly as they are")
    ap.add_argument("new", nargs="?", help="what they become")
    ap.add_argument("--show", action="store_true", help="print the paragraph as a fix sees it")
    args = ap.parse_args()

    fmt = blocks.format_of(args.file)
    try:
        text = blocks.read(args.file)
    except (OSError, ValueError, KeyError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    frame, paragraphs = blocks.parse(text, fmt)
    n = args.paragraph
    if not 1 <= n <= len(paragraphs):
        print(f"ERROR: {args.file} has paragraphs 1 to {len(paragraphs)}", file=sys.stderr)
        return 2
    p = paragraphs[n - 1]
    if args.show:
        print(shown(p, fmt))
        if fmt == "docx":
            print("\n".join(legend(p)))
        return 0
    if args.old is None or args.new is None:
        print("ERROR: give the words to replace and what they become, or --show", file=sys.stderr)
        return 2
    if not args.old.strip() or args.old == args.new:
        print("ERROR: nothing to fix", file=sys.stderr)
        return 2
    words = changed_words(args.old, args.new)
    if words > MAX_WORDS:
        print(f"NOT fixed: that changes {words} words, and a fix is one to {MAX_WORDS}. A sentence "
              f"that needs more is regenerated: rewrite.py … --only {n}", file=sys.stderr)
        return 1
    fixed, why = apply(p, fmt, args.old, args.new)
    if fixed is None:
        print(f"NOT fixed: {why}.", file=sys.stderr)
        return 1
    paragraphs[n - 1] = fixed
    blocks.write(args.file, blocks.unparse(frame, paragraphs), args.file)
    print(f"Paragraph {n}: «{args.old}» -> «{args.new}» ({words} word{'s' * (words > 1)})")
    note = update_parts(args.file, n, args.old, args.new)
    if note:
        print(note)
    return 0


if __name__ == "__main__":
    sys.exit(main())

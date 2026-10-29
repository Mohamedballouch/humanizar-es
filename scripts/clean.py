#!/usr/bin/env python3
"""Step 4a, only on request and only for English: the agent takes the AI slop out of the
original before the base model rewrites it, and this script is the gate it must pass.

  clean.py export 00-original.txt -o 00-slop.txt
      the prose, unit by unit (a paragraph, or one item of a list), in a work file. Code,
      tables, headings, quotations and titles are not in it. In LaTeX, math, citations,
      references and every command are placeholders [1], [2]… that must stay.

  clean.py import 00-original.txt 00-slop.txt -o 00-clean.txt --concepts concepts.txt
      puts the edited units back, and writes 00-clean only if every check passes against
      the original:
        - no concept lost, no figure lost or added (a minus sign included), quotations
          verbatim, no invented reference, URLs, links and `inline code` unchanged, every
          LaTeX placeholder exactly once;
        - only the slop: at most half of any unit's words changed, and at most a third of
          the whole text's. A cleanup past that is a rewrite, and the base model does the
          rewriting.
      Anything else: nothing is written, the report lists every problem and the sentences
      that changed, and the exit code is 1. Narrow the edits in the work file and import
      again. Then run rewrite.py on 00-clean, and every later check against 00-original.

The patterns to remove, and when not to: references/slop-patterns.md.
"""
import argparse
import difflib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blocks  # noqa: E402
import check  # noqa: E402
import join  # noqa: E402
import latex  # noqa: E402
import rewrite  # noqa: E402
import tells  # noqa: E402
import word  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # so a Windows console does not choke on «» or ñ
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")

HEADER = re.compile(r"^=== (\d+(?:\.\d+)?) ===\s*$")
MAX_UNIT, MAX_TOTAL = 0.5, 1 / 3  # shares of words a cleanup may change


def units(text, fmt):
    """(frame, paragraphs, [(id, visible text)]): the prose a cleanup may touch."""
    frame, paragraphs = blocks.parse(text, fmt)
    out = []
    for i, p in enumerate(paragraphs, 1):
        k = blocks.kind(p, fmt)
        if k == "prose" and not rewrite.title_block(p, fmt):
            out.append((str(i), visible(p, fmt)))
        elif k == "list":
            for j, (_, item) in enumerate(blocks.items(p, fmt), 1):
                if item and not rewrite.short_item(item):
                    out.append((f"{i}.{j}", visible(item, fmt)))
    return frame, paragraphs, out


def codec(fmt):
    """The module that turns a paragraph into prose with placeholders and back, or None."""
    return latex if fmt == "latex" else word if fmt == "docx" else None


def visible(p, fmt):
    return codec(fmt).protect(p)[0] if codec(fmt) else " ".join(p.split())


def changed_share(before, after):
    """Share of the words of `before` that a cleanup replaced, removed or added to."""
    a, b = re.findall(r"\w+", before.lower()), re.findall(r"\w+", after.lower())
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    changed = sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in sm.get_opcodes()
                  if tag != "equal")
    return min(1.0, changed / max(1, len(a)))


def changed_sentences(before, after):
    """[(original sentences, their replacement)] for what a cleanup changed, so a reader
    can check each edit against what it replaced: no check sees «addressing» -> «solved»."""
    a = rewrite.SENTENCE_END.split(" ".join(before.split()))
    b = rewrite.SENTENCE_END.split(" ".join(after.split()))
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return [(" ".join(a[i1:i2]), " ".join(b[j1:j2]))
            for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"]


def guard(original, new, fmt, concepts):
    """(problem or None, text for the document, plain before, plain after) for one unit."""
    if codec(fmt):
        c = codec(fmt)
        vis, pieces = c.protect(original)
        bad = c.problem(vis, new, pieces)
        if bad:
            return bad, original, "", ""
        before, after = c.strip_placeholders(vis), c.strip_placeholders(new)
        text = c.restore(new, pieces)
    else:
        before, after, text = " ".join(original.split()), " ".join(new.split()), new
    lost = check.numbers_lost(before, after)
    added = check.numbers_added(before, after)
    if lost or added:
        change = "; ".join(x for x in (lost and "lost " + ", ".join(lost),
                                       added and "added " + ", ".join(added)) if x)
        return f"(figures {change})", original, before, after
    missing = rewrite.concepts_in(before, concepts) - rewrite.concepts_in(after, concepts)
    if missing:
        return f"(concept lost: {', '.join(sorted(missing))})", original, before, after
    bad = rewrite.citation_problem(before, after) or rewrite.markup_problem(before, after)
    if bad:
        return bad, original, before, after
    share = changed_share(before, after)
    if share > MAX_UNIT:
        return (f"(edited {share:.0%} of it; only the slop, at most {MAX_UNIT:.0%})",
                original, before, after)
    return None, text, before, after


def read_work(path):
    """{id: text} from a work file; a unit's lines are joined with spaces."""
    got, cur = {}, None
    with open(path, encoding="utf-8-sig") as fh:
        for line in fh:
            m = HEADER.match(line.strip())
            if m:
                cur = m.group(1)
                got[cur] = []
            elif cur is not None and not line.lstrip().startswith("#"):
                got[cur].append(line.strip())
    return {k: " ".join(x for x in v if x) for k, v in got.items()}


INSTRUCTIONS = """\
# Cleanup work file ({source}). Edit only the sentences that carry an AI pattern
# (references/slop-patterns.md) and leave every other sentence exactly as it is. Keep the
# «=== n ===» lines, every figure, name, term, negation and hedge, quotations word for word,
# and the paragraphs as they are. {latex}Then:
#   python3 scripts/clean.py import {source} THIS_FILE -o 00-clean{ext} --concepts concepts.txt
"""
LATEX_NOTE = ("[1], [2]… stand for math, citations, references and other LaTeX: keep each\n"
              "# one exactly once, where it is; write no backslash and no brace. ")
WORD_NOTE = ("[1], [2]… stand for words in italics or bold, citations, equations, links and\n"
             "# footnotes of the Word file: keep each one exactly once, where it is. ")


def english_only(text, fmt):
    lang = join.detect_language(blocks.plain(text, fmt))
    if lang != "en":
        print("ERROR: the cleanup step is for English text; this one reads as Spanish. Skip it "
              "and run rewrite.py on the original.", file=sys.stderr)
        return False
    return True


def export(args):
    fmt = blocks.format_of(args.original)
    text = blocks.read(args.original)
    if not english_only(text, fmt):
        return 2
    _, _, found = units(text, fmt)
    ext = os.path.splitext(args.original)[1] or ".txt"
    head = INSTRUCTIONS.format(source=args.original, ext=ext,
                               latex=LATEX_NOTE if fmt == "latex" else WORD_NOTE if fmt == "docx" else "")
    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write(head + "\n" + "\n".join(f"=== {uid} ===\n{v}\n" for uid, v in found))
    flagged = [uid for uid, v in found if tells.find(latex.strip_placeholders(v), "en")]
    print(f"Written: {args.output} ({len(found)} units; tells.py finds patterns in "
          f"{len(flagged)}: {', '.join(flagged) or 'none'})")
    return 0


def do_import(args):
    fmt = blocks.format_of(args.original)
    text = blocks.read(args.original)
    frame, paragraphs, found = units(text, fmt)
    work = read_work(args.work)
    unknown = sorted(set(work) - {uid for uid, _ in found})
    if unknown:
        print(f"ERROR: {args.work} has units the original does not: {', '.join(unknown)}. "
              "Export again, or fix the «=== n ===» lines.", file=sys.stderr)
        return 2
    concepts = check.load_concepts(args.concepts) if args.concepts else []
    concepts = check.with_definitions(concepts, blocks.plain(text, fmt))

    problems, edited, results = [], [], {}
    words_total = changed_total = 0
    for uid, vis in found:
        original = unit_source(paragraphs, uid, fmt)
        new = work.get(uid, "").strip()
        plain_vis = latex.strip_placeholders(vis) if codec(fmt) else vis
        words = len(re.findall(r"\w+", plain_vis))
        words_total += words
        if not new or new == vis:
            results[uid] = original
            continue
        problem, result, before, after = guard(original, new, fmt, concepts)
        if problem:
            problems.append(f"{uid} {problem}")
            continue
        changed_total += changed_share(before, after) * words
        edited.append((uid, changed_sentences(before, after)))
        results[uid] = result

    total = changed_total / max(1, words_total)
    if total > MAX_TOTAL:
        problems.append(f"the whole text: {total:.0%} of its words edited; only the slop, at "
                        f"most {MAX_TOTAL:.0%}")
    if edited:
        print("Changed (read each pair: the same claim, no stronger, no weaker?):")
        for uid, pairs in edited:
            for old, new in pairs:
                print(f"  {uid}  - {old or '(nothing)'}\n  {' ' * len(uid)}  + {new or '(removed)'}")
    if problems:
        print("NOT written (narrow the edits in the work file and import again):\n  "
              + "\n  ".join(problems))
        return 1

    out = list(paragraphs)
    ids = {uid for uid, _ in found}
    for i, p in enumerate(paragraphs, 1):
        if str(i) in ids:
            out[i - 1] = results[str(i)]
        elif blocks.kind(p, fmt) == "list" and any(u.startswith(f"{i}.") for u in ids):
            out[i - 1] = blocks.rebuild([(m, results.get(f"{i}.{j}", t))
                                         for j, (m, t) in enumerate(blocks.items(p, fmt), 1)], fmt)
    blocks.write(args.output, blocks.unparse(frame, out), args.original)

    score = lambda ps: sum(tells.score(blocks.prose_of(p, fmt), "en") for p in ps)  # noqa: E731
    before, after = score(paragraphs), score(out)
    print(f"Written: {args.output} ({len(edited)} of {len(found)} units edited, {total:.0%} of "
          f"the words; tells score {before} -> {after})")
    if edited and 0 < before <= after:
        print("WARNING: the tells score did not drop: check the edits removed the patterns.")
    return 0


def unit_source(paragraphs, uid, fmt):
    """The original text of unit «3» (paragraph 3) or «3.2» (item 2 of the list in 3)."""
    if "." not in uid:
        return paragraphs[int(uid) - 1]
    i, j = (int(x) for x in uid.split("."))
    return blocks.items(paragraphs[i - 1], fmt)[j - 1][1]


def main():
    ap = argparse.ArgumentParser(description="Step 4a: the cleanup work file out, and back in "
                                             "through the gate.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="the prose of a text, unit by unit, in a work file")
    e.add_argument("original")
    e.add_argument("-o", "--output", required=True)
    i = sub.add_parser("import", help="the cleaned units back, only if every check passes")
    i.add_argument("original")
    i.add_argument("work")
    i.add_argument("-o", "--output", required=True)
    i.add_argument("--concepts", "--conceptos", dest="concepts",
                   help="file of concepts that must not be lost")
    args = ap.parse_args()
    return export(args) if args.cmd == "export" else do_import(args)


if __name__ == "__main__":
    sys.exit(main())

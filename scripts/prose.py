#!/usr/bin/env python3
"""The two ends of the Claude pipeline, where the agent itself does the rewriting.

  prose.py export 00-original.txt -o 01-prose.txt
      the prose of the text, unit by unit (a paragraph, or one item of a list), in a work
      file the agent rewrites. Code, tables, headings, quotations, titles, and in LaTeX the
      preamble, equations, figures, tables and bibliography are not in it: they stay as
      they are. In LaTeX, math, citations, references and every command are placeholders
      [1], [2]… that the rewrite must keep.

  prose.py import 00-original.txt 01-prose.txt -o 02-final.txt --concepts concepts.txt
      puts the rewritten units back into the text, each one through the same guards as
      the base-model pipeline: no lost concept, no lost or added figure (a «0.50» that
      became «0.5» is one), quotations verbatim, no invented reference, URLs, links and
      `inline code` unchanged, every LaTeX placeholder once, not truncated or doubled.
      A unit that fails stays as the original, the report says why, and the exit code is
      1 until every unit passes: fix those units in the work file and import again.

The work file is plain text: a «=== 3 ===» line before each unit (3.2 is item 2 of the
list in paragraph 3, the numbers rewrite.py --only and tells.py use), lines starting with
«#» ignored. Rewrite the text under each line; keep the lines.
"""
import argparse
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

if hasattr(sys.stdout, "reconfigure"):  # so a Windows console does not choke on «» or ñ
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")

HEADER = re.compile(r"^=== (\d+(?:\.\d+)?) ===\s*$")
HARD_COPY = 0.8  # a «rewrite» that keeps 80% of the original in long runs is not one


def units(text, fmt):
    """[(id, visible text)] of the prose to rewrite, and what import needs to rebuild it."""
    frame, paragraphs = blocks.parse(text, fmt)
    out = []
    for i, p in enumerate(paragraphs, 1):
        k = blocks.kind(p, fmt)
        if k == "prose" and not rewrite.is_title(p):
            out.append((str(i), visible(p, fmt)))
        elif k == "list":
            for j, (_, item) in enumerate(blocks.items(p, fmt), 1):
                if item and not rewrite.short_item(item):
                    out.append((f"{i}.{j}", visible(item, fmt)))
    return frame, paragraphs, out


def visible(p, fmt):
    return latex.protect(p)[0] if fmt == "latex" else " ".join(p.split())


INSTRUCTIONS = """\
# Work file of the Claude pipeline ({source}).
# Rewrite the text under each «=== n ===» line and keep the lines themselves. Say exactly
# what the original says: every figure, name, term and negation; quotations word for word;
# no new fact, example or reference. {latex}Then: python3 scripts/prose.py import {source} THIS_FILE -o 02-final{ext}
"""
LATEX_NOTE = ("[1], [2]… stand for math, citations, references and other LaTeX: keep each "
              "one exactly once,\n# where it belongs; write no backslash and no brace. ")


def export(args):
    fmt = blocks.format_of(args.original)
    with open(args.original, encoding="utf-8-sig") as fh:
        text = fh.read()
    _, _, found = units(text, fmt)
    ext = os.path.splitext(args.original)[1] or ".txt"
    head = INSTRUCTIONS.format(source=args.original, ext=ext,
                               latex=LATEX_NOTE if fmt == "latex" else "")
    body = "\n".join(f"=== {uid} ===\n{v}\n" for uid, v in found)
    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write(head + "\n" + body)
    words = sum(len(latex.strip_placeholders(v).split()) for _, v in found)
    print(f"Written: {args.output} ({len(found)} units, {words} words to rewrite)")
    return 0


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


def guard(original, new, fmt, concepts, lang):
    """(problem or None, warning or None, text to put in the document) for one unit."""
    if fmt == "latex":
        vis, pieces = latex.protect(original)
        bad = latex.problem(vis, new, pieces)
        if bad:
            return bad, None, original
        plain_o, plain_n = latex.strip_placeholders(vis), latex.strip_placeholders(new)
    else:
        vis, plain_o, plain_n = visible(original, fmt), " ".join(original.split()), new
    if new == vis:
        return None, "unchanged", original
    problem, share = rewrite.acceptable(plain_o, plain_n, rewrite.concepts_in(plain_o, concepts),
                                        concepts, HARD_COPY)
    lost, added = check.numbers_lost(plain_o, plain_n), check.numbers_added(plain_o, plain_n)
    if lost or added:  # in this pipeline a figure is never left to put back later
        change = "; ".join(x for x in (lost and "lost " + ", ".join(lost),
                                       added and "added " + ", ".join(added)) if x)
        return f"(figures {change})", None, original
    if problem == "(copied)":
        return f"(copied, {share:.0%} in long runs of the original)", None, original
    if problem:
        return problem, None, original
    warning = f"{share:.0%} in long runs of the original" if share > 0.45 else None
    text = latex.restore(rewrite.restore_percent_signs(vis, new), pieces) if fmt == "latex" else new
    return None, warning, text


def do_import(args):
    fmt = blocks.format_of(args.original)
    with open(args.original, encoding="utf-8-sig") as fh:
        text = fh.read()
    frame, paragraphs, found = units(text, fmt)
    work = read_work(args.work)
    unknown = sorted(set(work) - {uid for uid, _ in found})
    if unknown:
        print(f"ERROR: {args.work} has units the original does not: {', '.join(unknown)}. "
              "Export again, or fix the «=== n ===» lines.", file=sys.stderr)
        return 2
    concepts = check.load_concepts(args.concepts) if args.concepts else []
    lang = join.detect_language(" ".join(blocks.prose_of(p, fmt) for p in paragraphs))

    failed, warned, missing, done = [], [], [], 0
    out = list(paragraphs)

    def one(uid, original):
        nonlocal done
        new = work.get(uid)
        if new is None or not new.strip():
            missing.append(uid)
            return original
        problem, warning, result = guard(original, new, fmt, concepts, lang)
        if problem:
            failed.append(f"{uid} {problem}")
        elif warning:
            warned.append(f"{uid} ({warning})")
        done += result != original
        return result

    ids = {uid for uid, _ in found}
    for i, p in enumerate(paragraphs, 1):
        if str(i) in ids:
            out[i - 1] = one(str(i), p)
        elif blocks.kind(p, fmt) == "list" and any(u.startswith(f"{i}.") for u in ids):
            pairs = [(m, one(f"{i}.{j}", t) if f"{i}.{j}" in ids else t)
                     for j, (m, t) in enumerate(blocks.items(p, fmt), 1)]
            out[i - 1] = blocks.rebuild(pairs, fmt)  # a list with nothing to rewrite stays as is
    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write(blocks.unparse(frame, out))

    print(f"Written: {args.output} ({done} of {len(found)} units rewritten)")
    if failed:
        print("FAILED, kept as the original (fix them in the work file and import again):\n  "
              + "\n  ".join(failed))
    if missing:
        print("Not in the work file, kept as the original: " + ", ".join(missing))
    if warned:
        print("Check: " + "; ".join(warned))
    flagged = []
    for i, p in enumerate(out, 1):
        prose = blocks.prose_of(p, fmt)
        if prose and not rewrite.is_title(p):
            hits = tells.find(prose, lang)
            if tells.flagged(hits):
                flagged.append(f"{i} ({tells.summary(hits)})")
    if flagged:
        print("AI tells left (rewrite those sentences in the work file): " + "; ".join(flagged))
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(description="Prose out to a work file and back, guarded.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="the prose of a text, unit by unit, in a work file")
    e.add_argument("original")
    e.add_argument("-o", "--output", required=True)
    i = sub.add_parser("import", help="the rewritten units back into the text, guarded")
    i.add_argument("original")
    i.add_argument("work")
    i.add_argument("-o", "--output", required=True)
    i.add_argument("--concepts", "--conceptos", dest="concepts",
                   help="file of concepts that must not be lost")
    args = ap.parse_args()
    return export(args) if args.cmd == "export" else do_import(args)


if __name__ == "__main__":
    sys.exit(main())

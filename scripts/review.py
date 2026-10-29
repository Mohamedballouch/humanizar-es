#!/usr/bin/env python3
"""Step 6's review sheet: every sentence of the original beside what the rewrite made of it.

  python3 scripts/review.py 00-original.txt 01-rewritten.txt --concepts concepts.txt -o 01-review.md

In every real run so far the checks passed and reading still found an error: an inversion
(«made after» -> «generated without having seen»; «controllers outperform rule-based
schedules» -> «controllers are out-performed by rule based scheduling»), an invented count
(«teams of three agents»), a mechanism turned into a measurement, a claim made firmer («no
significant difference»), a garbled sentence. This sheet makes that reading complete. For each prose
paragraph it aligns the two versions sentence by sentence (one to one, two merged into one,
one split in two, one dropped, one added) and flags each pair:

  FIGURES    a figure of the original lost, or one added, in this pair
  NEGATION   a negation added or lost («without», «no», «not»…)
  CLAIM      a hedge dropped («may», «suggests») or a booster added («significant»)
  COMPARISON an «outperform» turned passive («outperformed by»), «superior» into
             «inferior»: who beats whom may have flipped
  CONCEPT    a concept of concepts.txt missing from the rewritten paragraph
  DROPPED    an original sentence, or most of one, with no counterpart
  ADDED      a new sentence, or most of one, the original does not support
  DIFFERENT  little in common: garbled, or saying something else
  COPIED     nearly word for word: detectors read it as the AI original

Flags point at where meaning most often changes; they prove nothing either way. Read every
pair, flagged first. When the rewrite was made in parts (rewrite.py saves them in
`…parts.json`), each pair names its part and the command that redoes only that part.

Plain text, Markdown, LaTeX (.tex) and Word (.docx). Standard library only.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blocks  # noqa: E402
import check  # noqa: E402
import join  # noqa: E402
import rewrite  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # so a Windows console does not choke on «» or ñ
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")

STOP = set("""a an the of and or to in on at by for with from as is are was were be been it its this
that these those which who whom than then there their they we our us he she his her not no
de la el los las un una y o en por para con del al que se su sus es son fue lo como""".split())
MOVES = ((1, 1), (2, 1), (1, 2), (3, 1), (1, 3), (2, 2), (1, 0), (0, 1))
SKIP, RESHAPE = 0.2, 0.05  # what a dropped or added sentence, and a merge or split, cost
DIFFERENT, COVERED, COPIED = 0.12, 0.3, 0.8


def sentences(text):
    """The sentences of a paragraph; «et al.», «Fig.» and initials do not end one."""
    out = []
    for s in rewrite.SENTENCE_END.split(" ".join(text.split())):
        if out and join.no_period_end(out[-1]):
            out[-1] += " " + s
        elif s.strip():
            out.append(s)
    return out


def stems(text):
    """Content words cut to five letters (so «optimisers» meets «optimisation»), and
    numbers whole: what two sentences about the same thing share."""
    words = re.findall(r"[a-z0-9]+(?:[.,][0-9]+)?", check.norm(text))
    return {w if w[0].isdigit() else w[:5] for w in words
            if w not in STOP and (len(w) > 1 or w.isdigit())}


def similarity(a, b):
    sa, sb = stems(a), stems(b)
    return len(sa & sb) / max(1, len(sa | sb))


def coverage(part, whole):
    """Share of the content words of `part` that `whole` also has."""
    sp = stems(part)
    return len(sp & stems(whole)) / max(1, len(sp))


def align(a, b):
    """[(original sentences, rewritten sentences)], in order, from a dynamic programme that
    rewards shared content and charges for dropped, added, merged or split sentences."""
    n, m = len(a), len(b)
    best = [[None] * (m + 1) for _ in range(n + 1)]
    best[0][0] = (0.0, None)
    for i in range(n + 1):
        for j in range(m + 1):
            if best[i][j] is None:
                continue
            score = best[i][j][0]
            for di, dj in MOVES:
                ii, jj = i + di, j + dj
                if ii > n or jj > m:
                    continue
                if di == 0 or dj == 0:
                    gain = -SKIP
                else:
                    gain = similarity(" ".join(a[i:ii]), " ".join(b[j:jj]))
                    gain -= 0 if (di, dj) == (1, 1) else RESHAPE
                if best[ii][jj] is None or score + gain > best[ii][jj][0]:
                    best[ii][jj] = (score + gain, (i, j))
    pairs, i, j = [], n, m
    while (i, j) != (0, 0):
        pi, pj = best[i][j][1]
        old, new = a[pi:i], b[pj:j]
        if len(old) == len(new) == 1 and not stems(old[0]) & stems(new[0]):
            pairs += [([], new), (old, [])]  # nothing in common: one dropped, one added
        else:
            pairs.append((old, new))
        i, j = pi, pj
    return pairs[::-1]


def readable(block, fmt):
    """The paragraph as a reader reads it; in LaTeX, with its commands still visible."""
    if fmt == "latex":
        return " ".join(blocks.latex.plain(block).split())
    if fmt == "docx":
        return " ".join(blocks.word.text_of(block).split())
    return " ".join(blocks.prose_of(block, fmt).replace("\n", " ").split())


def flags_for(old, new, para):
    """The flags of one pair. `para` holds what the whole paragraph lost or gained, so a
    figure that only moved to the next sentence is not flagged here."""
    a, b = " ".join(old), " ".join(new)
    out = []
    value = lambda x: check.WORD_VALUES.get(check.norm(x), check.figure_key(x))  # noqa: E731
    lost = [x for x in check.numbers_lost(a, b) if value(x) in {value(y) for y in para["lost"]}]
    added = [x for x in check.numbers_added(a, b) if value(x) in {value(y) for y in para["added"]}]
    if lost or added:
        out.append("FIGURES " + "; ".join(x for x in (lost and "lost " + ", ".join(lost),
                                                      added and "added " + ", ".join(added)) if x))
    neg_add = [x for x in para["neg_added"] if x in check.norm(b)]
    neg_lost = [x for x in para["neg_lost"] if x in check.norm(a)]
    if neg_add or neg_lost:
        out.append("NEGATION " + "; ".join(x for x in (
            neg_add and "added " + ", ".join(f"«{x}»" for x in neg_add),
            neg_lost and "lost " + ", ".join(f"«{x}»" for x in neg_lost)) if x))
    hedges, boosters = check.claim_changes(a, b)  # in this pair: a swap elsewhere does not hide it
    if hedges or boosters:
        out.append("CLAIM " + "; ".join(x for x in (
            hedges and "hedge dropped " + ", ".join(f"«{x}»" for x in hedges),
            boosters and "added " + ", ".join(f"«{x}»" for x in boosters)) if x))
    flips = check.comparison_changes(a, b)
    if flips:
        out.append("COMPARISON " + "; ".join(flips))
    missing = [c for c in para["concepts"]
               if any(check.pattern(v).search(check.norm(a)) for v in para["variants"][c])]
    if missing:
        out.append("CONCEPT missing from the paragraph: " + ", ".join(missing))
    if old and not new:
        out.append("DROPPED")
    elif new and not old:
        out.append("ADDED")
    else:
        gone = [s for s in old if len(stems(s)) > 2 and coverage(s, b) < COVERED] if len(old) > 1 else []
        new_ = [s for s in new if len(stems(s)) > 2 and coverage(s, a) < COVERED] if len(new) > 1 else []
        if gone:
            out.append("DROPPED inside a merge: «" + " ".join(gone[0].split()[:8]) + "…»")
        if new_:
            out.append("ADDED inside a split: «" + " ".join(new_[0].split()[:8]) + "…»")
        if similarity(a, b) < DIFFERENT and not gone and not new_:
            out.append("DIFFERENT")
        if len(a.split()) >= 8 and rewrite.copied_share(a, b) > COPIED:
            out.append("COPIED")
    return out


def part_of(text, entry):
    """Number of the part of a parts record that holds this rewritten sentence, or None."""
    if not entry or not text:
        return None
    probe = " ".join(text.split()[:6])
    for k, t in enumerate(entry.get("text", []), 1):
        if probe and probe in " ".join(t.split()):
            return k
    return None


def main():
    ap = argparse.ArgumentParser(description="Each sentence of the original beside the rewrite's, flagged.")
    ap.add_argument("original")
    ap.add_argument("rewritten")
    ap.add_argument("--concepts", "--conceptos", dest="concepts")
    ap.add_argument("-o", "--output", help="the sheet, in Markdown (default: print it)")
    args = ap.parse_args()

    fmt = blocks.format_of(args.original)
    try:
        frame_a, paras_a = blocks.parse(blocks.read(args.original), fmt)
        frame_b, paras_b = blocks.parse(blocks.read(args.rewritten), fmt)
    except (OSError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    if len(paras_a) != len(paras_b):
        print(f"ERROR: {args.original} has {len(paras_a)} paragraphs and {args.rewritten} "
              f"{len(paras_b)}: the rewrite must keep them (check.py says where).", file=sys.stderr)
        return 2
    concepts = check.load_concepts(args.concepts) if args.concepts else []
    concepts = check.with_definitions(concepts, " ".join(readable(p, fmt) for p in paras_a))
    variants = {name: vs for name, vs in concepts}
    try:
        with open(args.rewritten + ".parts.json", encoding="utf-8") as fh:
            parts = json.load(fh)
    except (OSError, ValueError):
        parts = {}

    lines = [f"# Review: {os.path.basename(args.original)} -> {os.path.basename(args.rewritten)}", ""]
    total, flagged, counts = 0, 0, {}
    for i, (pa, pb) in enumerate(zip(paras_a, paras_b), 1):
        if blocks.kind(pa, fmt) not in blocks.PROSE or rewrite.is_title(readable(pa, fmt)):
            continue
        ta, tb = readable(pa, fmt), readable(pb, fmt)
        if not ta:
            continue
        para = {"lost": check.numbers_lost(ta, tb), "added": check.numbers_added(ta, tb),
                "neg_added": sorted(set(check.negations(tb) - check.negations(ta))),
                "neg_lost": sorted(set(check.negations(ta) - check.negations(tb))),
                "concepts": sorted(rewrite.concepts_in(ta, concepts) - rewrite.concepts_in(tb, concepts)),
                "variants": variants}
        lines += [f"## Paragraph {i}", ""]
        if ta == tb:
            lines += ["Unchanged: the original as it was (rewrite it, or it reads as AI).", ""]
        for k, (old, new) in enumerate(align(sentences(ta), sentences(tb)), 1):
            total += 1
            fl = flags_for(old, new, para)
            flagged += bool(fl)
            for f in fl:
                counts[f.split()[0]] = counts.get(f.split()[0], 0) + 1
            head = f"### {i}.{k}" + (" FLAG: " + " | ".join(fl) if fl else "")
            lines += [head, "",
                      "- **original:** " + (" ".join(old) or "(nothing)"),
                      "- **rewrite:** " + (" ".join(new) or "(nothing)")]
            part = part_of(" ".join(new), parts.get(str(i)))
            if part and fl:
                lines.append(f"- part {part}: redo it with `rewrite.py … --only {i} --part {part}`")
            lines.append("")
    summary = (f"{total} pairs, {flagged} flagged" + (": " + ", ".join(
        f"{n} {f}" for f, n in sorted(counts.items(), key=lambda x: -x[1])) if counts else "")
        + ". Read every pair: flags show where meaning most often changes, not whether it did.")
    lines.insert(2, summary)
    lines.insert(3, "")
    sheet = "\n".join(lines).rstrip() + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(sheet)
        print(f"Written: {args.output} ({summary})")
    else:
        sys.stdout.write(sheet)
    return 0


if __name__ == "__main__":
    sys.exit(main())

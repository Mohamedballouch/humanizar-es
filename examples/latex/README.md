# Example: a LaTeX paper

`paper.tex` is a short AI-written paper with what a real one carries: an abstract, inline
and display math, citations and cross-references, a comment, a figure, a table, a list and
a bibliography. `paper.pdf` is the same paper compiled, to try the PDF path.

Only the prose reaches the model. Everything else stays byte for byte, and inside a
paragraph the inline LaTeX becomes placeholders the model has to keep:

```text
The rapid expansion of remote work over the past several years has changed the way
organizations plan collaboration [1]. As shown in Fig. [2], adoption grew from 12% in
2019 to 41% in 2022. [3] Prior work by Martínez et al. [4] measured output with a simple
model [5], where [6] captures the effect of distance.
```

`[1]` is `~\cite{smith2020,lee2021}`, `[3]` the comment `% TODO: update`, `[5]` the math
`$y = \alpha + \beta x$`. A try that drops, repeats or invents a placeholder is not used.

Try the steps that need no model:

```bash
python3 scripts/tells.py examples/latex/paper.tex                     # stock AI phrases, per paragraph
python3 scripts/join.py examples/latex/paper.tex -o /tmp/joined.tex --pauses 2
python3 scripts/check.py examples/latex/paper.tex /tmp/joined.tex     # "FIGURES: all 45 … none added"
python3 scripts/convert.py /tmp/joined.tex -o /tmp/joined.pdf         # needs a LaTeX engine
python3 scripts/convert.py examples/latex/paper.pdf -o /tmp/paper.md  # the PDF path: needs pdftotext
```

With the model, the full run is the one in `SKILL.md`, with `.tex` names:
`rewrite.py 00-original.tex -o 01-rewritten.tex`, then `join.py`, `check.py` and
`convert.py 02-final.tex -o 02-final.pdf`.

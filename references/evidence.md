# Evidence

Every measurement of the recipe (`rewrite.py` → hand fixes → `join.py`), taken by hand in
[Grammarly's AI detector](https://www.grammarly.com/ai-detector) in October 2026, one scan
per version, with the box cleared before pasting. The Spanish test essays belong to a user
and are not published; their numbers are. The English examples are in `examples/en/`.

## 1. The full recipe

| Essay | Original rewritten by `rewrite.py` | `rewrite.py` + fixes + **`join.py`** |
|---|---|---|
| 🇪🇸 Aristotle: act and potency, 1,990 words, 11 paragraphs | 45% (the original, first half) | **0% and 0%** (two halves, `--pauses 2`) |
| 🇪🇸 Tourism and AI in Chiapas, 1,150 words, 9 paragraphs | 77% | **0%** |
| 🇪🇸 Dragon Ball and its generation, 910 words, 7 paragraphs | 84% | **10%** |
| 🇪🇸 An AI classification model, 690 words, 5 paragraphs | not measured | **0%** |

Hand fixes: 21 in Chiapas and 16 in Dragon Ball. Concepts kept: 37 of 38 in Chiapas
("itinerarios" became "rutas") and 24 of 24 in Dragon Ball.

The third Spanish essay was the first run of the published skill (v2.0.0), done by an
agent following `SKILL.md` step by step: 9 hand fixes (one restored a negation the model
had inverted), 18 of 18 concepts, about 4 minutes on CPU.

The fourth essay (October 7) ran the 3.0.0 pipeline: copy guard, `--only` regeneration
of five paragraphs, 7 + 3 hand fixes of one to three words, `--pauses 2` and 12 logical
connectors; 24 of 24 concepts. Grammarly reads about 1,400 words, so it was measured in
halves (1,081 and 937 words, with headings).

## 2. What Grammarly punishes: one change at a time

Base: the `rewrite.py` output of the Dragon Ball essay, **without fixes**. Each version
applies a single change.

| Version (same base) | Grammarly |
|---|---|
| Base, unchanged | 84% |
| Random double spaces | 84% |
| Remove ~35% of commas | 60% |
| Splice ~50% of sentences with commas | 54% |
| Join ~60% of sentences with "y" | 40% |
| **Join every sentence of each paragraph with "y"** | **8%** |
| Same, in 4 paragraphs instead of 7 | 8% |
| The original **without** `rewrite.py`, join ~60% | 66% |
| The original **without** `rewrite.py`, join all | 57% |

What it shows:

1. **Grammarly looks at sentence rhythm**, not typography: double spaces moved nothing,
   and the more sentences are joined, the lower the score.
2. **Joining sentences beats any punctuation error**, and adds none.
3. **Both steps are needed.** Joining without rewriting first stopped at 57%; rewriting
   without joining, at 84%.
4. **The number of paragraphs doesn't matter** (8% with 7 and with 4).

## 2b. Hand fixes and pauses: one change at a time (fourth essay)

Same essay, same base-model rewrite; second half unless noted.

| Version | First half | Second half |
|---|---|---|
| All joined; 23 hand fixes, three of them sentence-sized (one pasted back from the original) | 0% | 3% |
| The sentence-sized fixes regenerated with `--only`; bibliography removed | not measured | 3% |
| The two paragraphs still carrying 4–5-word fixes regenerated too | not measured | **0%** |
| `--pauses 2` + 12 connectors, a block could be a single sentence | 6% | **0%** |
| `--pauses 2` + 12 connectors, every block two or more sentences | **0%** | **0%** (same text) |

What it shows:

1. **Hand fixes of four or more words are measurable.** The 3% survived removing the
   bibliography and went away only when the paragraphs with bigger fixes were regenerated.
2. **Pauses are compatible with the rhythm step**, as long as no sentence is left alone.
   The 6% came from near-copies of the original standing between two periods; the same
   sentences inside longer blocks scored 0%.
3. **Logical connectors** («sin embargo», «por eso», «es decir»…), one or two words per
   swap, did not raise the score.

## 2c. ZeroGPT: what it measures, and how selection got it to 0% (fourth essay)

ZeroGPT was measured through the same service its web page uses, which returns the score
and the list of flagged sentences. **It is deterministic**: the same text gave the same
score every time (100% and 100%, 52.4% and 52.4%). Controls in every session: Unamuno's
prologue (1,685 words) and the author's chat messages, both 0%.

**One change at a time, same essay:**

| Version | ZeroGPT |
|---|---|
| The AI original (whole) | 34.3% |
| Rewritten by the base model, sentences unjoined | 33.9% |
| … every sentence of each paragraph joined | 44.0% |
| … `--pauses 2` (the version at 0% in Grammarly) | 52.4% |
| … the same, with headings, as handed in | 45.3% |
| Unamuno, joined with `join.py` (full and with pauses) | 0% and 0% |

What it shows:

1. **ZeroGPT scores sentence by sentence and weighs by words** (`aiWords / textWords`).
   Joining does not make human text look like AI, but a long sentence that contains one
   textbook clause is flagged whole, so joining amplifies what is left of the original.
2. **The base-model rewrite alone does not move ZeroGPT** (34.3% → 33.9%). It flags
   fluent, definitional sentences («La potencia activa es la facultad de…»).
3. **The same paragraph sampled several times gives very different scores.** Paragraph
   «potencia activa y pasiva», 8 samples, unjoined: 29% to 96%; joined: 100% in all.
   «Conclusión», 8 samples, joined: 0% in three, 58–100% in the rest.
4. **The stock opening comes from our own prompt.** `rewrite.py` starts each paragraph with
   the original's first two words. With «Aristóteles distingue…», 22 candidates of that
   paragraph scored 100% joined; starting with «La potencia» instead, the chosen candidate
   scored 0% with three different pause layouts. The introduction, starting with «Uno de»,
   was flagged in context with every candidate; with «Desde la», 0%.
5. **Context changes the score.** A paragraph at 0% alone was flagged inside the document,
   and the other way round; adding the bibliography moved one version from 0% to 10.2%. So
   candidates were measured inside the whole document, with and without bibliography.
6. **It is brittle.** Replacing «actus» with «acto» four times took a paragraph from 0% to
   43%; a three-word grammar fix, from 0% to 62%. Every fix was measured again; when one
   broke a paragraph, another candidate or a smaller fix was used.
7. **Selection needs a person.** One candidate passed but dropped a whole sentence about
   the contradiction between Parmenides and Heraclitus; another changed the quotation of
   Aristotle and added «(De Anima, libro i, cap. vi)», a reference that does not exist.
   Both were discarded; `rewrite.py` now rejects changed quotes and invented references.

**Result:** 7 of 11 paragraphs replaced by selected candidates (two with another opening),
24 of 24 concepts, both quotations of Aristotle verbatim. Measured by the author on the
public sites: **ZeroGPT 0%** (whole text), **Grammarly 0% and 0%** (halves), **GPTZero 0% AI ·
2% mixed · 98% human** (whole text, and the second half alone). 92 candidates were
generated and more than 200 versions scored to get there.

## 2d. English (October 7): ZeroGPT at 0%, and what GPTZero's English model sees

Two AI-generated English essays: the repo's example on remote work (601 words) and one on
electric vehicles (673 words). Same pipeline: base-model rewrite, ≤3-word fixes,
`--pauses 2`, and for the second essay, selection of candidates for three paragraphs.

**Controls.** Hacker News comments from March 2016 (human, pre-LLM, 363–766 words): ZeroGPT
1.5%, GPTZero 100% human. **Emerson's *Self-Reliance* (1841) scored 64.5% AI in ZeroGPT**:
famous classic texts are false positives, so they make bad controls. The two AI originals:
100% in ZeroGPT, 100% AI in GPTZero.

| | ZeroGPT | GPTZero (model 4.1o) |
|---|---|---|
| Remote work · original | 100% | 100% AI |
| Remote work · rewritten, `--pauses 2` | **0%** | 100% AI |
| Electric vehicles · original | 100% | — |
| Electric vehicles · after selection (3 paragraphs) | **0%** | — |

**GPTZero's newer English model reads base-model paraphrases: the next milestone.** Spanish is scored by GPTZero's
model 4.1m, which reads our output as human; English is scored by model 4.1o, which does
not. Every variant below scored 100% AI on the whole remote-work essay, with a valid
control in the same session:

| Variant (whole document) | GPTZero 4.1o |
|---|---|
| Qwen3-4B + HIP, one pass, unjoined and joined | 100% AI |
| … two passes (faithful: 13/13 concepts, 0–32% copied) | 100% AI |
| … temperature 1.3 | 100% AI |
| … paragraphs mixed from the three versions above | 100% AI |
| Llama 3.1 8B **base**, few-shot paraphrase | 100% AI |
| Mistral 7B **base**, two temperatures | 100% AI |
| Three middle paragraphs only (285 words) | 100% AI |
| **One paragraph alone (~100 words)** | 76–99% human |

A single paragraph passes only because it is short: from ~250 words on, GPTZero's English
model recognizes text written by a language model, base or chat, from three model families.
A different method is needed for it (for example, a base model fine-tuned on human English
prose). Contributions welcome. Note: GPTZero's percentages are the model's confidence in its
classification of the whole text, not a share of the words.

## 2e. A journal abstract with the real model (October 26): fidelity, not detectors

One English abstract, 294 words in one paragraph, 41 concepts, 19 figures (a «−0.7», en-dash
ranges, British spelling). Qwen3-4B-Base Q8_0 + HIP on 4 CPU cores. **No detector was run:
these rows are about what the pipeline keeps and loses.**

| Run | Whole tries passed | Parts | Time | After the guards |
|---|---|---|---|---|
| 1 (5.4.1) | 0 of 6 | 4, 1 kept as the original | 15 min | Every check passed; reading found «supervised» for «controlled», «generated without having seen» for «made after» (an inversion), a garbled sentence, and «6.7%\%» |
| 2 (5.5.0) | 0 of 6 | 4, all rewritten | 13 min | Every check passed; reading found «teams of three agents» (six), «as measured by throughput» (a mechanism made a measurement), a garbled sentence. Parts 2 and 3 redone with `--part`: 6 tries kept the original, 15 tries passed, one with stray `$` |
| 3, `--protect-terms` | 0 of 6 | 4, 1 kept as the original | 18 min | Every check passed; the model put a locked term in the wrong place («the optimiser's curse directives») and lost the parentheses of a list |
| 4, LaTeX (5.7.0) | 0 of 2, then split | 4, 1 kept as the original, 1 copied 59% | 16 min | The abstract with 5 `\cite` and 6 inline formulas: every citation and formula kept in place, the rest of the file identical, the PDF compiled. Reading found «no significant difference in superiority or equivalence» for «neither superiority nor equivalence is established» (the added-negation report named it), «starts» lost, the off-window sentence garbled again, «at» lost |
| 5 (5.8.0, llama-server) | 0 of 2, then split | 4: part 2 kept as the original, part 3 lost «B = 3»; then candidates for parts 2, 4 and 1 | 8 min + 14 min of candidates | Reading found «the optimistic predictions … were confirmed by the optimiser's curse» (the CLAIM flag named it), «supervised by a simulator» for «through», «maximum estimate» for «point estimate». Candidates: part 2 gave 1 of 18 tries, then 3 of 8 («teams … trained to work on … four test days», «without changing the energy cost»), part 4 one inversion («expected gains … lower than the realised gains») and «validated by the optimiser's curse», part 1 a supervisor that «starts or ends an event». Final: one candidate per part, 9 fixes of 1–3 words (15 words), every check passed, 4 sentences of 51–96 words |

Run 5 also found three faults in the workflow, fixed in 5.8.0: a part candidate is saved as
the whole paragraph, so adopting part 4's after part 2's put the old part 2 back; a candidates
run wrote back the parts record it had read at its start; and candidates were ranked by tells
alone, so the one that wrote «without changing the energy cost» looked as good as the rest.
Candidates now carry the review sheet's flags and are ranked by them.

What it changed: concepts now match across hyphens, apostrophes and spelling; `\%` and `$…$`
are repaired; added counts in words («three») are added figures; added negations are
reported; a long paragraph is split after 2 whole tries; parts can be redone and get
candidates one by one; `--words-per-period` keeps a long paragraph's sentences readable.
`--protect-terms` did not help on this abstract and stays off. The LaTeX placeholders for
`\cite` and math, which sit after a word or in brackets, held in every try; the ones for
terms inside a noun phrase did not. Reading every paragraph
against the original (step 6) caught what no check did, in all three runs.

## 2f. Citations in a manuscript paragraph, and a Word file, with the real model (October 29)

Same model and machine as 2e. **No detector was run.** A 74-word Markdown paragraph with every
kind of citation a manuscript carries: «(Smith et al., 2020; Lee & Park, 2019)», «[12],
[14]–[16]», «Wang (2021) reports», «Kim (2020, p. 4)», and two inline formulas.

| Code | Usable tries | What the usable ones did |
|---|---|---|
| 5.7.0, citations as plain words | 1 of 24 | «[12], [14]–[16]» became «(12), (14) - (16)», and every check passed |
| first placeholders: the year of a narrative citation locked | 2 of 24 | one dropped the authors («… are noisy (2021)», «the formulation of (2020, p. 4)»), one wrote «[14]--[16]» |
| narrative citations as words, a numbered cluster as one piece (12 tries, logged) | 2 of 12 | faithful |
| the same 12 outputs through 5.8.0's checks (replayed) | 6 of 12 | one inverted the finding («controllers are out-performed by rule based scheduling»: the new COMPARISON flag names it), one overstated it («gains shrink» -> «advantages disappear»), two faithful |

Why the 12 logged tries were refused: a concept 5 times (three times «on-site microgrid»:
twice «microgrids on-site», once «on-site» really dropped; «the cost of outages»; «price
predictions»), a placeholder 4 times (repeated at a sentence end twice, all four written as
«(1)»… «(4)» once, renumbered once), copied once. Two tries wrote «Wang [2021]» and «Kim
[2020, p.4]», which would have passed every check. 5.8.0 repairs both bracket habits and
matches a two-word term in the orders English moves it into; a dropped «on-site» and «price
predictions» are still refused.

A thesis-like Word file (four prose paragraphs; a Zotero citation field, a superscript
citation, a hyperlink, an italic species name, a tracked change and a citation manager's
bibliography field): three paragraphs rewritten in 47 seconds, the fourth kept as a title,
the tracked-change paragraph and the bibliography untouched. Every piece came back in place,
all 22 figures and 5 concepts held, and the review sheet flagged nothing. Reading found
«minimize» for «reduce» and «as shown in public dataset» (its article lost): two one-word
fixes, now made with `fix.py`. It also found «simulation ¹», a space before the superscript
citation; a piece written against the word before it now stays against it.

## 2g. Loading the model once (October 29)

The cost of a try that writes one token, on 4 CPU cores, the same 74-word paragraph:
`llama-completion` 12.9 s cold, then 6.3 and 6.8 s (a new process loads the model every time);
llama-server 4.1 s to load once, then 3.3 s for a new prompt and 0.1 s for the same prompt
again. Six whole tries took 28.2 s each with `llama-completion` and 25.4 s through the server
(22.0 s without one try slowed by other work on the machine). Not measured on a GPU.

The Word file of 2f through the whole pipeline in this mode: the model loaded once (12 s), the
three paragraphs were rewritten in 35 s in all, and the server was gone at the end; join,
check (22 of 22 figures) and the PDF followed. The review sheet flagged one pair, a negation
added: «noisy price forecasts shrink their gains» had become «they perform no better than the
rule-based controller when price forecasts are noisy», a claim the paper never made, so that
paragraph is one to regenerate. Reading found two more: «in manufacturing other lines»
(the bold «manufacturing» is a placeholder; `fix.py … "in [2] other lines" "in other [2]
lines"` put it back, its bold kept) and «as the reward» dropped after the formula, which no
check sees.

## 3. Why a base model

Xu et al. (2026), *Base Models Look Human To AI Detectors*
([arXiv:2605.19516](https://arxiv.org/abs/2605.19516)): on GPTZero and Pangram, text from
Llama3-8B **base** scored 96.7% and 98.8% human; text from its chat version, 30.3% and
17.1%. Detectors mostly recognize the fingerprint of chat training. Their method, HIP,
fine-tunes a base model to paraphrase; this repo uses their adapter for Qwen3-4B-Base.

Our measurements point the same way: rewriting with chat models never went below 64%, and
every fix made by a chat model raised the score.

| Fixes | Grammarly |
|---|---|
| Dragon Ball, `rewrite.py` + join, no fixes | 8% |
| Same with 16 fixes before joining | 10% |
| Two passes of `rewrite.py` + 19 fixes, no joining | 91% |

That's why the recipe fixes only the culprit word, by hand, and before joining.

## 4. What was tried and didn't work

So nobody repeats it. All with full essays, in Grammarly:

| Attempt | Grammarly |
|---|---|
| Rewrite with a chat model following style rules | 75% |
| Full rewrite with a chat model, without typical AI phrases | 100% |
| Rewrite sentence by sentence with a chat model, guided by a local detector | 67% |
| Reorganize the essay structure with a chat model | 92% |
| One pass of `rewrite.py`, no joining | 77% and 84% |

Adding typos and dropping accents also lowered the score (4% at best), but it leaves
visible errors, and joining sentences gets there without them.

## 5. Other detectors

Fourth essay, the `--pauses 2` version, before selection (section 2c has the final one).
Every detector was checked in the same session with two controls: human texts (a 1914
prologue by Miguel de Unamuno, and the author's own chat messages, typos included) and the
AI original.

| Detector | Human controls | AI original | **Final** | Valid? |
|---|---|---|---|---|
| **GPTZero** (free account, first 10,000 characters) | — | 37% AI · 32% mixed · 31% human | **0% AI · 1% mixed · 99% human** | yes |
| **ZeroGPT** | 0% and 0% | 44.9% | **49.8%** | yes; 0% after selection (section 2c) |
| QuillBot | 0% | 0% | 0% | no: it does not flag the AI original |
| GPTZero, from a browser after ~6 scans | 100% AI (Unamuno and the author's messages) | 100% | 100% | no: throttled, it flags everything |

The last row is why every session needs controls: without them, a throttled detector
reads as "the new version is worse".

- **CleverHumanizer** disagrees with Grammarly: rank correlation of 0.47 across 16 texts
  measured on both. It gave 5% AI to a joined essay Grammarly scored at 69%, and tends to
  extremes (~5% or ~78%).
- **Grammarly's in-editor detector**, on a free account, shows 20% for any text: it's a
  sample number, not a measurement.

## 6. Limits

- Four essays in Spanish and two in English (section 2d). We don't yet know how well it
  carries over to emails, marketing or technical writing, and GPTZero's English model
  is not passed.
- `tells.py` (3.2.0) and the English joining changes of 3.2.0 and 3.3.0 are not measured
  against any detector yet. Section 4 is why they find and never fix: a chat-model
  rewrite without the typical AI phrases still scored 100% in Grammarly.
- ZeroGPT passes only with selection (section 2c), which costs model runs and a person's reading.
- One scan per version. Differences of a few points may be noise.
- Detectors change; this is a snapshot of October 2026.

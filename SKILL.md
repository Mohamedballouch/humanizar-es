---
name: humanize-research
description: Rewrites AI-generated text and research papers (English or Spanish) so AI detectors read it as human, saying exactly the same thing: every figure, citation and quotation kept. A local base model without chat training (Qwen3-4B-Base + HIP, llama.cpp) rewrites each paragraph; scripts guard fidelity (concepts, figures, quotes, references, links, LaTeX placeholders), rebuild the rhythm (join.py --pauses 2), flag AI tells (tells.py) and select candidates for what a detector still flags. Measured at 0% in Grammarly, 0% in ZeroGPT and 0% AI in GPTZero on a test essay. Takes text, Markdown, LaTeX papers and PDF (convert.py). Use when asked to "humanize" text or a paper, "make it not detectable as AI", "pass Grammarly/GPTZero/Turnitin", "remove AI tells", or in Spanish "humaniza este texto", "que no lo detecte el detector de IA".
metadata:
  version: "5.0.0"
  languages: en, es
  evidence: references/evidence.md
---

# Humanize AI text and research papers

You receive a text written with AI and give it back **saying exactly the same thing**, but
without AI detectors (Grammarly, GPTZero, ZeroGPT, Originality.ai, Turnitin) recognizing it
as AI. A local **base** model (Qwen3-4B-Base with the HIP adapter, run by llama.cpp) does the
rewriting; you prepare the text, review with fixes of one to three words, have the user
measure, and select among candidates. The rewriting runs on the computer (you still read the
text, as you read everything in this session). The first time, check the installation
(step 4). Talk to the user in their language.

In the commands, `<skill>` is the folder containing this `SKILL.md`. Texts go in the
user's working folder, not inside the skill. Use the original's extension in every name
(`00-original.md`, `02-final.tex`). **On Windows** type `python` (or `py`) where it says
`python3`; everything else is the same. No key or account is needed.

## Before rewriting

### 1. Save the original untouched

If the text came through chat, write it to `00-original.txt`, with paragraphs separated by
a blank line. Leave out a chat model's wrapper around the text («Certainly! Here is…», "I
hope this helps", "Let me know if…"): it is not part of the text. Never overwrite the
original. Markdown is fine: code, tables, headings and quotations are kept as they are, and
a list is rewritten item by item with its markers (short items stay as they are).

**A paper in LaTeX** (journal or conference): copy the main `.tex` to `00-original.tex` in
the paper's folder (where its figures and `.bib` live) and use `.tex` names in every step
(`01-rewritten.tex`, `02-final.tex`). Only the prose is rewritten: the preamble, sections,
equations, figures, tables, algorithms, theorems, captions, comments and bibliography stay
byte for byte, and inside a paragraph math, `\cite`, `\ref`, footnotes and every other command
become placeholders `[1]`, `[2]`… that the rewrite must keep. Papers split into several
files (`\input{intro}`) are done one file at a time.

**A PDF**, only when there is no source (ask for the `.tex` or the Word file first: it is
always the better input):

```bash
python3 <skill>/scripts/convert.py paper.pdf -o 00-original.md
```

It joins each paragraph's lines, undoes hyphenation, drops page numbers and running
headers, and fences equations, table cells and references so they are kept. It prints how
many figures it read; if it warns that a figure of the PDF is not in the text, fix that
first. **Read `00-original.md` with the user before going on**: an extracted text can carry
broken lines or table cells as prose. The PDF made back at the end has the same words in a
plain layout, not the original's.

### 2. Ask what it's for

If it's graded academic work, or work where AI use must be disclosed, say so before going
on (see *Responsible use*). For a paper going to a journal or a conference, ask whether the
venue's policy allows AI-assisted writing and what it asks authors to disclose: most allow
it with disclosure, some forbid it, and rewriting does not change what has to be disclosed.

### 3. List what must not be lost

Build `concepts.txt` with the user: **full** proper names, titles, terms, figures, dates
and the negations an idea rests on. One per line, variants with `|`, `*` for prefixes:

```text
Microsoft Teams | Teams
two or three days | 2 or 3 days
commut*
```

To start: `python3 <skill>/scripts/check.py 00-original.txt --list`

## Rewrite with the base model

### Why it works (read this so you don't sabotage it)

1. **Detectors recognize the fingerprint of chat training.** Everything a chat model
   writes carries it, **including you**. So never rewrite the text yourself
   or "improve" sentences: every sentence you write puts the fingerprint back. `rewrite.py` does the
   rewriting with a **base** model (no chat training).
2. **Grammarly recognizes rhythm**: sentences of even length, each with its own period.
   `join.py` rebuilds it in blocks of uneven length, the way people write.
3. **Both steps are needed.** Measured: `rewrite.py` alone 84%; joining alone 57%; both 8%.
4. **Copied stretches of the original are AI text.** Never paste a sentence of the
   original back, and never fix more than three words by hand: regenerate instead
   (`--only`). Measured: 3% with bigger hand fixes, 0% after regenerating.
5. **ZeroGPT scores sentence by sentence and weighs by words.** One textbook clause inside
   a long joined sentence flags the whole sentence, so rhythm alone can make ZeroGPT worse
   (34% → 52% on a test essay). What fixes it is **selection**: the base model gives a
   different version each run, so regenerate the flagged paragraphs as candidates and keep
   the one that passes, measured in the whole document (step 9). That essay ended at 0% in
   ZeroGPT, Grammarly and GPTZero at once.
6. **Stock openings come from the original.** The model starts each paragraph with the
   original's first two words; if they are «Uno de los problemas…» or «Aristóteles
   distingue…», it rebuilds the stock sentence. `--lead "Desde la"` gives it another start.
   In English, a paragraph that opens with a filler ("Moreover,", "Additionally,") leads
   with the words after it automatically.
7. **Stock phrases come through from the original too.** The base model paraphrases what
   it reads, so «plays a crucial role», "not only… but also", "Furthermore," or a dash in
   every sentence can survive. `tells.py` finds them with the catalog of Wikipedia's
   *Signs of AI writing* (as ranked by github.com/blader/humanizer) and names the
   paragraphs to regenerate. It finds; it never fixes: fixing them yourself puts the
   fingerprint back (rule 1). Not measured against detectors yet: it targets what readers
   notice and it ranks candidates.

### 4. Check the installation (once)

Run `python3 <skill>/scripts/install_model.py`: if everything is there it verifies it, says
"Ready" and rewrites one test sentence (10–60 s), so a llama.cpp that cannot run the model
fails here with its error; if something is missing, it says so.

1. **llama.cpp**: if missing, macOS and Linux `brew install llama.cpp`; Windows
   `winget install llama.cpp`. On Windows `rewrite.py` also looks in winget's folder, so no
   new terminal is needed; if it lives elsewhere, `HUMANIZE_LLAMA` holds the path to the
   `.exe`.
2. **The model** (`Qwen3-4B-Base.Q8_0.gguf` and `hip-qwen3-4b-base.gguf`): if missing,
   **ask permission** (~4.6 GB) and let `install_model.py` download it. If the user already
   has Qwen3-4B-Base as a `.gguf` (any quantization), set `HUMANIZE_BASE_MODEL` to that file
   instead: only the 280 MB adapter is downloaded, and the installer refuses a file that is
   not Qwen3-4B and warns if it is the chat model. A Hugging Face folder (`.safetensors`)
   is converted first with llama.cpp's `convert_hf_to_gguf.py`. A bigger base model
   (Qwen3-8B-Base) needs its own adapter too: `HUMANIZE_BASE_MODEL` and `HUMANIZE_ADAPTER`
   (README, «A bigger model»); it is not measured, and the paper finds little gain over 4B. It needs network
   access; if your environment blocks it, ask for approval or have the user run it in a
   terminal. If the download is cut, run it again: it resumes.

Python 3.9+ is enough: the scripts need no packages.

### 5. Rewrite with the local model

Tell the user: about 30 seconds per paragraph on an M4 Mac, 1 to 3 minutes on an older PC;
on the CPU, free. With a GPU, `HUMANIZE_GPU=1` (set before the session starts) runs it
there, much faster; `install_model.py` says whether llama.cpp sees the GPU. If your
environment cuts long commands, run it in the background and read its output: `rewrite.py`
saves the file after every paragraph and prints its progress.

```bash
python3 <skill>/scripts/rewrite.py 00-original.txt -o 01-rewritten.txt --concepts concepts.txt
```

At the end it reports which paragraphs it left as the original and the concept they kept
losing (check its spelling in `concepts.txt`), and which ones copied long stretches of the
original in every try. Rerun only those paragraphs, with more `--tries`. A try that drops a
figure (a year, an amount, a percentage) is retried; if every try does, the closest is kept
and the report names the figure to put back: that is a one-word fix. A try that changes a
URL, a link or `inline code` is never used. List items are reported as `3.2` (paragraph 3,
item 2); `--only` takes the paragraph number.

### 6. Review and fix, BEFORE joining (blocking)

```bash
python3 <skill>/scripts/check.py 00-original.txt 01-rewritten.txt --concepts concepts.txt
```

Besides concepts and negations, it lists the figures of the original missing from the
rewrite: put each one back (a one-word fix) unless it was written out on purpose.

Then scan it for tells of AI writing:

```bash
python3 <skill>/scripts/tells.py 00-original.txt 01-rewritten.txt
```

It scores every paragraph (3 = strong tell, 2 = stock word, 1 = weak alone) and prints the
`--only` command for those worth regenerating (one strong tell, two stock words, or 6
points), with a `--lead` when the paragraph opens with a stock connector. One stock word, a
dash or a list of three alone is ordinary human prose: leave it. Regenerate them as candidates (step 9) rather than fixing them: a tell
is never one of your one-to-three-word fixes. In English, do this before delivering; in
Spanish, when the user wants the text to read less like AI, not only to pass a detector.
It also lists **formatting tells** (a bold label on every list item, bold sprinkled in
prose, emojis in headings and lists, arrows, Title Case Headings): those you may fix by
hand, with the user's agreement, because removing markup adds no words.

Then **compare every paragraph of `01-rewritten.txt` with the original** and list what
really changed. Typical slips:

- a changed detail ("many" → "the majority"; "physical office" → "fixed schedule");
- an inverted or overstated idea ("were forced to work from home" where it said "split
  their time"; «renunciar al pragmatismo» for «resignarse al pragmatismo»);
- wrong gender, number or date («siglo X»);
- a lost `%` written in words ("sixty percent" → "60"), a typo or a dropped accent;
- a sentence that doesn't make sense.

Show the list to the user and fix **only the minimal culprit word or phrase**, with exact
replacements in `01-rewritten.txt`. Don't rewrite whole sentences or polish style: every
word you add raises the detector score (in testing, 16 fixes moved an essay from 8% to
10%). If it's just different but says the same thing, leave it.

**A fix is one to three words.** If a paragraph needs more — a garbled or inverted
sentence, an invented quote, a lost sentence — **don't write it and don't paste the
original's sentence back** (that is AI text again): redo that paragraph from the original
with the model and review it again:

```bash
python3 <skill>/scripts/rewrite.py 00-original.txt -o 01-rewritten.txt --concepts concepts.txt --only 6,11
```

`--only` keeps the other paragraphs and their fixes. Measured on a 1,990-word essay in
Grammarly: its last half scored 3% twice while it carried hand fixes of four or more words
(a few of them the original's own words put back); after redoing those paragraphs with
`--only` and fixing only 1-2 words, 0%. The bibliography was not the cause.

### 7. Rebuild the rhythm

```bash
python3 <skill>/scripts/join.py 01-rewritten.txt -o 02-final.txt --concepts concepts.txt --pauses 2
```

It detects English or Spanish (force it with `--lang en|es`). If it warns about words it
lowercased, check which are proper names; add them to `concepts.txt` and run it again.
`--pauses 2` leaves two or three periods per paragraph, in blocks of
uneven length, cutting first where a sentence already opens with «Sin embargo», «Por
ejemplo», «Segundo»… and joining the rest with «y» or «;». Then you may swap the «y» or «;»
of a join for a logical connector («sin embargo», «por eso», «así», «es decir», «en
cambio») **only where the relation is plain**, one or two words per swap. Measured on a
1,990-word essay: **0% and 0% in Grammarly** with 12 such swaps. Every block keeps at least
two sentences: when a near-copy of the original was left alone between two periods, that
half went up to 6%. Without `--pauses`, every sentence of a paragraph is joined into one
(also measured at 0%, but it reads badly); use it only if the user asks for it.

**In English** `join.py` also leaves out the filler openers "Moreover,", "Furthermore,",
"Additionally,", "In addition,", "Notably," and "Importantly," (they add nothing after
"and"), keeps acronyms like AI or COVID-19 and initials like "John F. Kennedy" intact, and
with `--no-dashes` turns dashes between words (—, –, --) into commas. Use `--no-dashes`
when the user's own writing doesn't use dashes; ask if you don't know. None of this is
measured against detectors yet; it removes what readers notice.

**Don't touch `02-final.txt` afterwards** except for those connector swaps: any fix goes into `01-rewritten.txt` and you
join again.

### 8. Verify and deliver

```bash
python3 <skill>/scripts/check.py 00-original.txt 02-final.txt --concepts concepts.txt
```

**Every figure must survive.** `check.py` counts each number of the original (years,
amounts, percentages, decimals with their precision, «siglo XX») and exits with 1 if a
version lost one or added one; the run is not done until it prints "FIGURES: all … of the
original are in every version, none added". Put a lost figure back by hand (a one-word
fix); an added one is a detail the original never gave: remove it or regenerate.

Deliver `02-final.txt`, the fidelity table and the list of fixes, **in the format the
user will hand in** (headings, bibliography): the context changes ZeroGPT's score. For a
paper, deliver `02-final.tex` and its PDF:

```bash
python3 <skill>/scripts/convert.py 02-final.tex -o 02-final.pdf     # LaTeX: compiles it, BibTeX too
python3 <skill>/scripts/convert.py 02-final.md -o 02-final.pdf      # text from a PDF: a plain PDF
```

It needs a LaTeX engine (TeX Live, MacTeX, MiKTeX or tectonic); without one, it says so and
the `.tex` can be compiled on Overleaf. From text it reads the new PDF back and warns if a
figure did not make it in. Warn
that sentences stay longer than in a polished essay. If the text is over ~1,400 words, tell
the user to measure it in Grammarly in two halves; GPTZero's free scan reads 10,000
characters. Ask them to measure in their detector **together with a text of their own
written without AI**, and to tell you what is still flagged.

### 9. Select, for what a detector still flags

ZeroGPT and Grammarly highlight the sentences they flag. For each flagged paragraph:

```bash
python3 <skill>/scripts/rewrite.py 00-original.txt -o 01-rewritten.txt --concepts concepts.txt \
        --only 4 --candidates 6 --temperature 1.1
```

If the paragraph starts with a stock opening, add `--lead` with two other words that fit
the paragraph («Desde la», «La potencia», «Para Aristóteles»; `tells.py` suggests one after a
stock connector). Candidates land in `01-rewritten.txt.candidates/`; tries that lose a
concept, change a quote, invent a reference or copy the original are already discarded.
Each candidate is printed with its tells score, and the list ends fewest tells first.
`--max-tells 2` also discards tries above that score (it costs more tries).

1. **Read each candidate against the original** and drop any that loses an idea, even if
   no concept is missing (one dropped a whole sentence about the contradiction between two
   authors). Among the faithful ones, start with the fewest tells.
2. **Have the user measure the survivors joined, inside the whole text**, not alone: a
   paragraph that scores 0% alone can be flagged in context, and the other way round.
3. Adopt the one that passes and join again:

```bash
python3 <skill>/scripts/rewrite.py 00-original.txt -o 01-rewritten.txt --take 4=01-rewritten.txt.candidates/p04-2.txt
python3 <skill>/scripts/join.py 01-rewritten.txt -o 02-final.txt --concepts concepts.txt --pauses 2
```

4. **Any fix to an adopted paragraph gets measured again.** ZeroGPT is deterministic but
   brittle: a one-word fix took a paragraph from 0% to 62%. If a fix breaks it, try the
   next candidate instead of forcing the fix.

## Don't

- **Rewrite it yourself, "humanize" it in your own words, or ask another chat model.**
  That adds the fingerprint this recipe removes.
- **Add typos, remove commas or add double spaces.** Not needed: double spaces moved
  nothing (84% → 84%), and joining sentences lowered the score more than any error.
- **Feed `rewrite.py` its own output.** A second pass drifts from the meaning (in testing
  it ended at 91%). Candidates are different: each is a fresh first pass from the original.
- **Accept a candidate that changes a quotation or adds a source.** The guard catches the
  usual cases; read for the rest.
- **Turn on the GPU yourself.** `rewrite.py` runs on the CPU unless the user has set
  `HUMANIZE_GPU`; it is their machine's setting.

## Limits (read before promising anything)

1. **It is measured on Grammarly, GPTZero and ZeroGPT**, Spanish essays: Grammarly 0% on three of
   four (10% on an older run); one essay at 0% in all three at once, ZeroGPT only after
   selection (step 9). **English:** ZeroGPT 0% on two essays; **GPTZero in English is not
   passed yet** - its model 4.1o recognizes base-model text (Qwen, Llama and Mistral tested)
   from ~250 words on. If the text is English and the user needs GPTZero, say so **before
   starting**. Never promise a number.
2. **Detectors flag human text too** and change without notice. Hence the human control.
3. **Only English and Spanish** have joining rules and tells. Other languages: the rewrite
   may work, joining and `tells.py` won't.
4. **`tells.py` is a reader's check, not a detector.** A low score does not mean a detector
   passes, and human text can score too (a dash, a list of three). Only strong tells
   justify regenerating on one sighting.
5. **Turnitin and iThenticate cannot be measured from here.** They are sold only to
   institutions and publishers, and since August 2025 Turnitin counts English text from
   "AI bypassers" (humanizers) as AI. The public detectors are a proxy, not a guarantee.

## Responsible use

For text the user or their client signs and answers for: brand content, outreach,
documentation, emails, drafts written with AI help. **Don't use it to pass off graded work
as one's own where AI is banned or must be disclosed.** If that's the destination, flag the
risk before proceeding.

## Files

- `scripts/install_model.py` — downloads and verifies the model (once)
- `scripts/rewrite.py` — steps 5, 6 and 9: rewrite with the local base model, guard
  fidelity, `--only`, `--candidates`, `--lead`, `--take`
- `scripts/join.py` — step 7: rebuild the rhythm of each paragraph (`--only`)
- `scripts/check.py` — concepts, negations and figures (counted), original against version
- `scripts/latex.py` — LaTeX papers: what is prose, placeholders for math and commands
- `scripts/convert.py` — PDF to text, text to PDF, LaTeX to PDF
- `scripts/blocks.py` — paragraphs and Markdown blocks (code, tables, lists), shared by all
- `scripts/tells.py` — steps 6 and 9: tells of AI writing per paragraph, what to regenerate
- `references/evidence.md` — every measurement
- `references/detectors.md` — how to measure in Grammarly, GPTZero, ZeroGPT and Originality.ai, with controls
- `examples/` — worked examples in English and Spanish, and a LaTeX paper with its PDF

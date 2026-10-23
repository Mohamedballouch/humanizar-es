# humanize-research · Local AI text humanizer for research papers and prose, in English and Spanish

[![tests](https://github.com/ervin-mo/humanizar-es/actions/workflows/tests.yml/badge.svg)](https://github.com/ervin-mo/humanizar-es/actions/workflows/tests.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![macOS · Linux · Windows](https://img.shields.io/badge/macOS%20·%20Linux%20·%20Windows-yes-success.svg)](#install)
[![Español · English](https://img.shields.io/badge/Español%20·%20English-yes-success.svg)](#languages)

**English** · [Español](README.es.md)

![humanize-research: make AI text read as human, on your own computer, for free](assets/vista-previa.png)

**humanize-research** (called *humanizar-es* until 3.4; the repository keeps that name)
takes a text written with ChatGPT, Claude, Gemini or DeepSeek and gives
it back **saying the same thing**, in prose that the three detectors we measured read as
human: **0% in Grammarly, 0% in ZeroGPT and 0% AI / 98% human in GPTZero**, on the same
1,990-word essay that started at 45%. Use it as a *skill* for your coding agent (Claude
Code, Codex, OpenCode, Antigravity), or by hand.

## Two pipelines

| | **Claude pipeline** (the skill's default) | **Base-model pipeline** |
|---|---|---|
| Who writes | Your agent, paragraph by paragraph | A local base model without chat training (Qwen3-4B-Base + HIP) |
| What guards it | `prose.py import`: every figure, concept, quotation, reference, link and LaTeX placeholder, or the paragraph is refused | The same checks, inside `rewrite.py` |
| Needs | Nothing to install | A one-time 4.6 GB download; 30 s to 3 min per paragraph on CPU |
| Measured | **Not yet.** Rewrites by other chat models scored 64–100% in Grammarly | The results below |
| Your text | Read by your agent's provider, like anything your agent reads | Rewritten on your computer; by hand, it never leaves it |

The skill runs the Claude pipeline unless you ask for the base model, and offers the base
model for the paragraphs a detector still flags. Run by hand, without an agent, it is the
base-model pipeline. Every number below is the base-model pipeline's.

It is not a synonym spinner or a typo generator. The base-model pipeline has four stages,
and every one exists because a controlled experiment showed what a detector actually
measures: one variable at a time, the same text in every condition, and a human-written
control and the AI original in every session.

---

## Results

| AI-generated essay | Grammarly | ZeroGPT | GPTZero |
|---|---|---|---|
| **Aristotle: act and potency** · 1,990 words · before | 45% | 45.3% | 37% AI |
| **Aristotle: act and potency** · **after** | **0% and 0%** | **0%** | **0% AI · 98% human** |
| Tourism and AI in Chiapas · 1,150 words | 77% → **0%** | — | — |
| An AI classification model · 690 words | → **0%** | — | — |
| Dragon Ball and its generation · 910 words | 84% → **10%** | — | — |
| 🇬🇧 Remote work (English) · 601 words | — | 100% → **0%** | — |
| 🇬🇧 Electric vehicles (English) · 673 words | — | 100% → **0%** | — |

*October 2026. The first essay keeps 24 of 24 key names, terms and figures, and its two
quotations of Aristotle word for word. Grammarly reads ~1,400 words, so it was measured in
halves. The Dragon Ball essay ran on an earlier version of the pipeline.*

---

## The method (base-model pipeline)

```
 original ─► 1. rewrite ──► 2. fidelity ──► 3. rhythm ──► 4. selection ──► final
             base model     concepts,       blocks of      candidates,
             without chat   quotes, copy,   uneven         measured in the
             training       ≤3-word fixes   length         whole document
```

### What the detectors measure

Three detectors, three different signals. The pipeline exists because each one was
taken apart with experiments:

| Detector | What it reacts to | What does **not** move it |
|---|---|---|
| **GPTZero** | the fingerprint of chat training; its newer English model (4.1o) also reads base-model text, our next milestone | — |
| **Grammarly** | rhythm: sentences of even length, each closed by its own period | double spaces (typos do move it, but leave visible errors) |
| **ZeroGPT** | individual sentences that read like a textbook; it scores **sentence by sentence and weighs by words** | joining sentences of a human text (Unamuno joined: 0%) |

### 1. Remove the chat-training fingerprint

Xu et al. (2026), [*Base Models Look Human To AI Detectors*](https://arxiv.org/abs/2605.19516),
showed that text from a **base** model scores 97–99% human on GPTZero and Pangram, and the
same model after chat training 17–30%. Our tests agree: every rewrite we tried with a chat
model stayed between 64% and 100% in Grammarly. `rewrite.py` paraphrases with
Qwen3-4B-Base plus the paper's HIP adapter, through llama.cpp, on your CPU.

### 2. Keep it faithful, without putting the fingerprint back

Each paragraph gets one pass, and a try is rejected and retried when it:

- loses a concept you listed (names, terms, figures, key negations);
- **changes a quotation** of the original or **adds a reference** the original never had
  (on a test essay the model wrote «(De Anima, libro i, cap. vi)», which does not exist);
- **copies the original**: more than 60% of its words in runs of 8+ identical words;
- **drops a figure** of the original (a year, an amount): retried, and if every try does,
  the closest is kept and the figure to put back is named;
- **changes a URL, a link or `inline code`**;
- comes out truncated or runs away.

Markdown is respected: code, tables, headings and quotations are kept as they are, and a
list is rewritten item by item with its markers.

`check.py` then compares concepts, negations and figures, and a person fixes **one to three words**
at most. Anything bigger is regenerated by the model (`--only`), never written by hand and
never pasted back from the original: hand fixes of four or more words kept half an essay
at 3% in Grammarly; regenerating those paragraphs brought it to 0%.

The base model paraphrases what it reads, so the stock phrases of chat models can come
through: "plays a crucial role", "not only… but also", "Furthermore,", a dash in every
sentence. `tells.py` scores each paragraph against the catalog of Wikipedia's
[*Signs of AI writing*](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing), as
ranked by [blader/humanizer](https://github.com/blader/humanizer), and names the paragraphs
to regenerate. It never fixes them: every hand fix puts the chat fingerprint back. It also
lists formatting tells (bold labels, emojis, Title Case Headings), the one kind you may fix
by hand, since removing markup adds no words. On the
English example, the original scores 29 and the rewrite 17.

### 3. Rebuild the rhythm

People write in bursts, some sentences long, some short. `join.py --pauses 2` leaves two or
three periods per paragraph, in **blocks of uneven length** of at least two sentences,
cutting first where a sentence already opens with a discourse marker («Sin embargo»,
"For example", «Segundo»). Inside a block it links with "and" or ";". No content word is
touched. In English it also leaves out the filler openers "Moreover,", "Furthermore,",
"Additionally,"…, keeps acronyms (AI, COVID-19) and initials (John F. Kennedy) intact, and
with `--no-dashes` turns dashes between words into commas.

### 4. Select by measurement

The base model is a sampler: the same paragraph comes out differently every time, and a
detector can score two samples 0% and 100%. So the paragraphs a detector still flags are
regenerated several times (`--candidates`), each candidate is joined and **measured inside
the whole document** (context changes the score), and the one that passes is adopted
(`--take`). All candidates come from the same base model, so selection adds no chat
fingerprint. Two findings made this work:

- **The opening words matter.** To keep writing in Spanish, the model starts each paragraph
  with the original's first two words. When those are a stock opening («Uno de los
  problemas más importantes…», «Aristóteles distingue…»), the model rebuilds the stock
  sentence and ZeroGPT flags it. Starting with other words (`--lead "Desde la"`) fixed it:
  22 candidates of one paragraph with the original opening scored 100%; with another
  opening, 0%.
- **Every edit is measured again.** ZeroGPT is deterministic but brittle: a one-word fix
  took a paragraph from 0% to 62%.

### The experiments behind each stage

Same essay, one change at a time.

| Grammarly | |
|---|---|
| Rewritten by the base model only | 84% |
| … plus random double spaces | 84% |
| … removing ~35% of the commas | 60% |
| … joining ~60% of the sentences | 40% |
| … joining every sentence of each paragraph | **8%** |
| The original, without the base model, joining every sentence | 57% |
| Rewriting with a chat model (four different recipes) | 64–100% |
| Pauses, with a sentence left alone between two periods | 6% |
| **Pauses, blocks of two or more sentences** | **0% and 0%** |

| ZeroGPT (deterministic: the same text always gives the same score) | |
|---|---|
| The AI original | 34.3% |
| Rewritten by the base model, sentences unjoined | 33.9% |
| … all sentences joined | 44.0% |
| … with pauses | 52.4% |
| A human text (Unamuno, 1914), joined the same way | 0% |
| **After selection: candidates measured in the whole document** | **0%** |

The tension is real: Grammarly wants long sentences, ZeroGPT punishes a long sentence that
contains one textbook clause. Rhythm alone cannot satisfy both; rhythm plus selection does.
Every measurement: [`references/evidence.md`](references/evidence.md).

### How we measure

- **Two controls in every session**: a human text must come out human, and the AI original
  must come out as AI. A detector that fails either one does not count: QuillBot scored
  the AI original 100% human, and GPTZero, after many scans from one browser, scored a
  1914 text 100% AI.
- **The reference is re-measured in the same session**, never compared with a number from
  hours before.
- **The final format is the one measured**: with headings and bibliography, ZeroGPT can
  give a different score than for the bare text.

---

## Install

### With your agent (easiest)

```bash
git clone https://github.com/ervin-mo/humanizar-es.git
cd humanizar-es             # the repository's name; the skill installs as humanize-research
python3 install.py          # on Windows: python install.py
```

Open a new session and ask: **"humanize this text"** (or «humaniza este texto»). The skill
walks the agent through every stage: install what's missing (it asks before downloading the
model), list with you what must not be lost, rewrite, show you every change, rebuild the
rhythm, and select candidates for whatever your detector still flags.

| Agent | Skills folder | Covered by `install.py`? |
|---|---|---|
| Claude Code | `~/.claude/skills` | yes |
| Codex | `~/.agents/skills` | yes |
| OpenCode | `~/.agents/skills`, `~/.claude/skills` | yes |
| Antigravity (`agy`) | `~/.agents/skills` | yes |
| DeepSeek Harness (`dsh`) | `~/.agents/skills` | yes |
| Gemini CLI | `~/.gemini/skills` | with `--agent gemini` |

### The model (once, ~4.6 GB)

Only for the base-model pipeline: the Claude pipeline needs nothing installed.

You need Python 3.9+ (no extra packages) and [llama.cpp](https://github.com/ggml-org/llama.cpp):

| | macOS and Linux | Windows |
|---|---|---|
| llama.cpp | `brew install llama.cpp` | `winget install llama.cpp` |
| The model | `python3 scripts/install_model.py` | `python scripts\install_model.py` |

The installer checks every file against its sha256 and resumes if the download is cut.

**Already have Qwen3-4B-Base?** Point the skill at it and only the 280 MB adapter is
downloaded. Any `.gguf` of Qwen3-4B-Base works (Q8_0, Q4_K_M, F16…); the installer reads its
header and refuses another model, and warns if it is Qwen3-4B, the chat model:

```bash
echo 'export HUMANIZE_BASE_MODEL=/path/to/Qwen3-4B-Base.gguf' >> ~/.bashrc && source ~/.bashrc
python3 scripts/install_model.py
```

In Hugging Face format (a folder of `.safetensors`), convert it first with llama.cpp:
`python3 ~/llama.cpp/convert_hf_to_gguf.py /path/to/Qwen3-4B-Base --outtype q8_0 --outfile
Qwen3-4B-Base.Q8_0.gguf` (after `pip install -r ~/llama.cpp/requirements/requirements-convert_hf_to_gguf.txt`).

It runs on CPU: 8 GB of free RAM is enough, no GPU. On an M4 Mac it takes about 30–60
seconds per paragraph; on a few-years-old PC, 1 to 3 minutes.

**Have a GPU?** `export HUMANIZE_GPU=1` runs the model on it, which is much faster. It needs
about 5 GB of free GPU memory (`HUMANIZE_GPU=20` puts only 20 of the model's 36 layers
there) and a llama.cpp built for the GPU: `-DGGML_VULKAN=ON` for most GPUs, NVIDIA
included (on Ubuntu, `sudo apt install libvulkan-dev glslc spirv-headers` first), or
`-DGGML_CUDA=ON` for NVIDIA with the CUDA toolkit (an RTX 50 needs CUDA 12.8 or later, newer
than some distributions' own package), added to llama.cpp's `cmake -S . -B build`; brew's
llama.cpp on a Mac uses Metal already. `install_model.py` then says whether
llama.cpp sees the GPU. It is off by default because on a Mac the GPU froze the screen
while the model ran. If the laptop lists its integrated graphics too, `export
HUMANIZE_GPU_DEVICE=Vulkan1` (a name from `llama-completion --list-devices`) pins the run to
the discrete one. It is the same model either way; the measurements were made on CPU.

---

## Use it by hand

By hand, without an agent, you run the base-model pipeline. On Windows, type `python`
where it says `python3`.

**1. List what must not be lost** in `concepts.txt`: full proper names, figures, terms.
One per line, variants with `|`, `*` for prefixes.

```text
Aristotle
act and potency | act and potentiality
self-regulat*
```

**2. Rewrite** with the base model:

```bash
python3 scripts/rewrite.py my-text.txt -o rewritten.txt --concepts concepts.txt
```

**3. Check, and fix one to three words at most.** For anything bigger, regenerate that
paragraph:

```bash
python3 scripts/check.py my-text.txt rewritten.txt --concepts concepts.txt
python3 scripts/tells.py my-text.txt rewritten.txt       # stock AI phrases left, per paragraph
python3 scripts/rewrite.py my-text.txt -o rewritten.txt --concepts concepts.txt --only 6,11
```

Don't ask ChatGPT to fix it: it puts back the fingerprint the base model removed.

**4. Rebuild the rhythm** (the language is detected automatically):

```bash
python3 scripts/join.py rewritten.txt -o final.txt --concepts concepts.txt --pauses 2
# English, if you don't write with dashes:
python3 scripts/join.py rewritten.txt -o final.txt --concepts concepts.txt --pauses 2 --no-dashes
```

**5. Measure** the final text in your detector, in the format you will hand in, with a
human text as control ([`references/detectors.md`](references/detectors.md)).

**6. Select, for what is still flagged.** Generate candidates of those paragraphs, with
other opening words if the paragraph starts with a stock phrase:

```bash
python3 scripts/rewrite.py my-text.txt -o rewritten.txt --concepts concepts.txt \
        --only 4 --candidates 6 --lead "Desde la" --temperature 1.1
```

Each candidate is printed with its `tells.py` score, fewest first; `--max-tells 2` also
discards tries above that score. Join each candidate into the full text, measure, adopt
the one that passes, and join again:

```bash
python3 scripts/rewrite.py my-text.txt -o rewritten.txt --take 4=rewritten.txt.candidates/p04-3.txt
python3 scripts/join.py rewritten.txt -o final.txt --concepts concepts.txt --pauses 2
```

Reread the adopted paragraph against the original: passing a detector is worth nothing if
it dropped an idea.

Worked examples, with every hand fix listed, are in [`examples/`](examples/).

### Papers: LaTeX in, LaTeX out; PDF in, PDF out

Give the scripts a `.tex` and they work on the prose only. The preamble, sections,
equations, figures, tables, algorithms, theorems, captions, comments and bibliography stay
byte for byte; inside a paragraph, math, `\cite`, `\ref`, footnotes and every other command
reach the model as placeholders (`[1]`, `[2]`…), and a try that drops, repeats or invents
one is not used. Rewritten paragraphs come back one sentence per line, so `git diff` shows
the paper's changes sentence by sentence.

```bash
python3 scripts/rewrite.py paper.tex -o 01-rewritten.tex --concepts concepts.txt
python3 scripts/join.py 01-rewritten.tex -o 02-final.tex --pauses 2
python3 scripts/check.py paper.tex 02-final.tex --concepts concepts.txt
python3 scripts/convert.py 02-final.tex -o 02-final.pdf      # compiles it, BibTeX included
```

With only a PDF, `convert.py` turns it into text first (it joins lines, undoes hyphenation,
drops page numbers and running headers, and fences equations, table cells and references
so they are kept), and turns the result back into a PDF at the end. That PDF has the same
words in a plain layout, not the original's: when you have the source, use it.

```bash
python3 scripts/convert.py paper.pdf -o 00-original.md       # needs pdftotext or pypdf
python3 scripts/convert.py 02-final.md -o 02-final.pdf       # needs a LaTeX engine
```

**Figures never change silently.** Every number of the original (years, amounts,
percentages, decimals with their precision, «siglo XX») is counted: a try that adds or
changes one is never used, a try that drops one is retried, `check.py` exits with 1 if a
version lost or added any, `convert.py` reports the figures it read from a PDF and reads
the PDF it makes back to confirm they are all there. See [`examples/latex/`](examples/latex/).

---

## Languages

| | Rewrite | Rhythm | Check | Measured |
|---|---|---|---|---|
| **Español** | ✅ | ✅ «y», «;», «pero»… | ✅ | ✅ four essays, three detectors |
| **English** | ✅ (the HIP adapter was trained in English) | ✅ "and", ";", "but"…, fillers left out, `--no-dashes` | ✅ + `tells.py` | ✅ ZeroGPT, two essays · GPTZero: next milestone |

Other languages: the rewrite may work (the base model is multilingual), but `join.py`
only knows Spanish and English connectors. Adding one is a small dictionary in
`scripts/join.py`; pull requests welcome.

## Detectors

| Detector | Status |
|---|---|
| **Grammarly** | ✅ 0% on three of four essays (10% on one run with an older version) |
| **GPTZero** | ✅ 0% AI · 98% human (Spanish) · English: next milestone ([what we tried](references/evidence.md)) |
| **ZeroGPT** | ✅ 0% in Spanish and English, with stage 4 (selection) where needed |
| **Originality.ai** | not measured yet; it claims to catch humanizers, so treat it as the strictest ([how to measure](references/detectors.md)) |
| **Turnitin / iThenticate** | cannot be measured: sold only to institutions and publishers, and it has counted English "humanizer" text as AI since August 2025 |
| QuillBot | not usable in Spanish: it scored the AI original 100% human |

Each detector runs its own model, so a version that passes one may not pass another; the
first essay passes all three at once. Measurements on more detectors and more kinds of
text are the contribution we need most.

---

## FAQ

**Is it free? Do I need an OpenAI key or any account?**
Free and keyless. The model downloads once and runs on your computer.

**Does it change what my text says?**
It is built not to: tries that lose a concept, change a quote or invent a reference are
rejected, `check.py` compares concepts and negations, and you reread every paragraph.

**Does it add typos on purpose, like other "humanizers"?**
No. It changes who wrote the sentences and their rhythm, not the spelling.

**Are the results consistent?**
Three of four essays reached 0% in Grammarly, and the latest one passes Grammarly, GPTZero
and ZeroGPT at once. The pieces that can be deterministic are (the joining is seeded;
ZeroGPT gives the same score for the same text), output that copies the original is
refused, and 123 tests run on every change on Ubuntu, macOS and Windows. Detectors drift
over time, which is why every session carries controls.

**Does the selection step send my text anywhere?**
The tool never does. Measuring is your step, in your detector, as with any text you check.

**Do I need a GPU?**
No. It runs on CPU, at low priority, so your computer stays usable. If you have one,
`HUMANIZE_GPU=1` uses it (see *The model*).

---

## Limits

1. **GPTZero in English is the next milestone.** Its newer English model (4.1o) reads
   base-model text from ~250 words on; three model families were tested
   ([evidence](references/evidence.md)). Emails, marketing and technical writing are not
   measured yet.
2. **Rereading is not optional.** The base model sometimes changes a detail or flips an
   idea. The pipeline catches lost concepts, changed quotes and invented references; a
   person catches the rest.
3. **Selection costs time.** Each candidate is a model run (30–60 s per paragraph on an M4).
4. **Detectors change.** This is a snapshot of October 2026.

## Responsible use

Made for text you sign and answer for: brand content, outreach, documentation, emails,
drafts written with AI help. **Don't use it to hand in graded work as your own where AI is
banned or must be disclosed.** That problem isn't technical; it's academic honesty. For a
paper, read the journal's or conference's policy on AI-assisted writing first: most allow
it with a disclosure, some forbid it, and rewriting the text does not change what you have
to disclose.

---

## Project layout

```
humanizar-es/
├── SKILL.md                 the skill for agents
├── install.py               installs the skill (install.sh: shortcut for macOS/Linux)
├── scripts/
│   ├── install_model.py     downloads the model (once)
│   ├── prose.py             Claude pipeline: the prose out to a work file and back, guarded
│   ├── rewrite.py           stages 1, 2 and 4: rewrite, guard fidelity, candidates
│   ├── check.py             stage 2: concepts and negations, original vs rewrite
│   ├── tells.py             stages 2 and 4: stock AI phrases per paragraph, what to regenerate
│   ├── blocks.py            paragraphs and Markdown blocks (code, tables, lists), shared
│   ├── latex.py             LaTeX papers: the prose, and placeholders for math and commands
│   ├── convert.py           PDF to text, text to PDF, LaTeX to PDF
│   └── join.py              stage 3: rebuild the rhythm of each paragraph
├── examples/                worked examples in Spanish and English
├── references/              every measurement, and how to measure
└── tests/                   123 tests on Ubuntu, macOS and Windows (no network, no model)
```

The old script names (`hip.py`, `unir.py`, `verificar_fidelidad.py`, `instalar_hip.py`)
still work.

## Contributing

What's missing most is **evidence**: the pipeline measured on more texts, more languages
and more detectors, always with a human control and the AI original. Open an issue or a
PR with the numbers in [`references/evidence.md`](references/evidence.md).

```bash
python3 -m unittest discover -s tests -v
```

## Credits and license

Code and docs: [MIT](LICENSE), © ervin-mo. The HIP method and adapter are by Xu et al.
(2026); the base model is Alibaba's Qwen3-4B-Base. Both are Apache-2.0 and downloaded
separately: see [`THIRD_PARTY.md`](THIRD_PARTY.md). The patterns in `tells.py` come from
Wikipedia's *Signs of AI writing* and [blader/humanizer](https://github.com/blader/humanizer)
(MIT). If you use this in your work, cite the
repo ([`CITATION.cff`](CITATION.cff)) and the HIP paper.

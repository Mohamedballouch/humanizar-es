# Changelog

## 5.8.0 — October 29, 2026

**Theses and reports in Word, and what 12 logged real-model tries showed.**

- **Word files (`.docx`) in every script**, with the standard library: only
  `word/document.xml` changes; styles, images, footnotes, comments, headers and a citation
  manager's data are copied byte for byte. Only the prose of the body is rewritten.
  Headings (by style or outline level, a thesis template's own style based on Heading 1
  included), captions, contents, the bibliography (by style, after a «References» heading or
  bold line, or a citation manager's field), quotations and code (by style), equations,
  tables, text boxes and Word's own document parts stay; paragraphs with tracked changes or
  comments are left as they are and counted. The paragraphs of other content controls,
  where templates keep an abstract, are prose. Inside a paragraph, italics, bold,
  superscript, citation fields (Zotero, Mendeley, EndNote), cross-references, links,
  equations and footnote marks reach the model as placeholders; a piece written against
  the word before it stays against it (a real run wrote «simulation ¹»). Long paragraphs are
  rewritten in parts, `--part` included. Tested on files from pandoc and LibreOffice and a
  thesis with a Zotero field, a tracked change and a bibliography field: the result opens in
  python-docx and LibreOffice, and the real model kept every piece in place.
- **`fix.py`**: step 6's fixes, one to three words of one paragraph, in any format; more is
  refused («regenerate it»). In Word it keeps every placeholder exactly once and the parts
  record, so `--part` still works after a fix. `--show` prints what each `[n]` stands for.
- **`convert.py 02-final.docx -o 02-final.pdf`**, with LibreOffice; it reads the PDF back for
  the figures.
- **Citations in text, Markdown and Word are placeholders**: «(Smith et al., 2020; Lee,
  2019)», a numbered cluster «[12], [14]–[16]» as one piece (alone, its dash came back as
  «--»), footnote marks and inline math. A narrative citation («Wang (2021) reports») stays
  words: locked as a piece it came back as «… are noisy [3]», and with only «(2021)» locked
  the model dropped «Wang». Its authors are concepts now, and its year a figure. Placeholders
  are put back in one pass: «[2] … [1]» could come back swapped.
- **Two bracket habits of the model are repaired before any check**: «(1)»… «(4)» written for
  the placeholders, and «Wang [2021]» for «Wang (2021)» (that try passed every check).
- **A concept of two plain words matches the orders English moves it into**: «outage cost*»
  finds «the cost of outages», «on-site microgrid» finds «microgrids on-site».
- **`HUMANIZE_SERVER=1`** loads the model once per run in llama.cpp's own server (on
  127.0.0.1 only) instead of once per try; with no `llama-server`, or if it stops, the tries
  run `llama-completion` as before. On 4 CPU cores a try's overhead fell from 6.5 s to 0.1–3 s
  (a retry of the same paragraph reuses its prompt), about a fifth of each try; more is
  expected with a GPU, where writing is fast (not measured). `install_model.py` says whether
  `llama-server` is there.
- **Words the model will not see are reported in Word**: a size or colour set by hand on
  part of a pasted paragraph keeps those words out of the rewrite, and `rewrite.py` names
  the paragraphs where that is a quarter or more of the words. Fixed on the way: a run
  whose only formatting was a language mark, which Word writes all the time, counted as
  formatted and its words were locked; language marks, ligatures and black set by hand are
  plain text now.
- **Every candidate is printed with the review sheet's flags** (a negation added or lost, a
  claim made firmer, a comparison flipped) and ranked by them, then by tells. A real part
  candidate wrote «without changing the energy cost» for «rather than lower energy cost»:
  its added «without» now heads the line.
- **A candidates run leaves the parts record alone**; it wrote back the copy it read at
  its start, undoing a `--take` or a `fix.py` made while it ran.
- **Part candidates of two parts add up.** A part candidate is saved as the whole paragraph,
  so taking part 4's after part 2's put the old part 2 back (found on the journal abstract).
  `--take` of a part candidate now replaces only its part.
- **COMPARISON** in `check.py` and `review.py`: an active «outperform» that came back passive
  («… outperformed by …»), or «superior» that became «inferior». A try accepted by the new
  checks read «controllers are out-performed by rule based scheduling» for «controllers
  outperform rule-based schedules»; the flag points straight at it.

Replayed through the new checks, the 12 logged tries of a paragraph with five citations and
two formulas went from 2 usable to 6 (references/evidence.md §2f).

## 5.7.0 — October 26, 2026

**For journal articles, theses and reports.**

- **A references section is never rewritten in text and Markdown either** (LaTeX's
  bibliography always was). Found by test: a Markdown manuscript's «## References» entries
  were prose and list blocks, so the base model would have rewritten authors, titles and
  years. From a References / Bibliography / Works Cited / Referencias / Bibliografía heading
  (Markdown, underlined, or a plain title line, numbered or bold) to the next heading of its
  level, an appendix or a new chapter, everything is copied byte for byte.
- **Acronym definitions are concepts.** «a large language model (LLM, …)» came back as «an
  LLM» in a real run; `check.py`, `rewrite.py` and `clean.py` now find each long form the
  original defines (its initials spell the acronym) and require it.
- **`check.py` prints word counts**, and `--word-limit N` fails a version over a journal's
  abstract limit (the real abstract went from 294 to 302 words).
- **`rewrite.py --resume`** continues an interrupted run (a thesis takes hours on a CPU):
  paragraphs already rewritten in the output stay, the rest are redone.

## 5.6.0 — October 26, 2026

From the second real-model run on the 294-word journal abstract:

- **Counts in words are figures when added.** «30 independently trained teams of three
  agents» (the teams have six) passed every check; digits and number words are now counted
  together, so an extra «three» is an added figure and the try is not used. Dropping a count
  in words («all three» -> «each») is still allowed.
- **`$…$` the original never had is removed** from a try, like `\%`: all 15 tries of one part
  wrote «$B=3$» and «$p$».
- **`--protect-terms`** (option, off): the multi-word, hyphenated and numbered concepts reach
  the model as fixed placeholders it writes around. Tried on the abstract: whole tries still
  0 of 6, and the model put a locked term in the wrong place («the optimiser's curse
  directives»). It stays off; references/evidence.md §2e has the three runs.
- **`join.py --words-per-period N`**: a long paragraph keeps about one period per N words
  (`--pauses 2` alone gave the abstract a 150-word sentence; with 55, four sentences of
  53–91 words). Not measured against detectors.
- **A paragraph over 150 words gets 2 whole tries, not 6, before it is split in parts**: the
  abstract failed 6 of 6 whole tries, 10 of its 13 minutes.
- **`--only N --part K --candidates M`**: several versions of one part, each saved as the
  whole paragraph; `--take` adopts one and keeps the parts record right.

## 5.5.0 — October 26, 2026

**From the first run with the real model in a test session** (Qwen3-4B-Base + HIP on CPU,
a 294-word journal abstract, 15 minutes). Every whole-paragraph try lost a term, the
automatic split rewrote it in 4 parts and kept one paragraph, and all figures and concepts
passed; reading it showed what the guards missed.

- **Concepts match across hyphens, apostrophes and spelling.** «on-site» = «on site» =
  «onsite», a curly apostrophe = a straight one, «realised» = «realized», «modelling» =
  «modeling». A concept typed with a straight apostrophe used to fail against the user's own
  original with a curly one, and part 4 was kept as the original over «realised-profit».
- **HIP's «\%» in plain text** is turned into «%». It used to be kept as a stray symbol, and
  the percent repair then wrote «6.7%\%».
- **`check.py` reports negations the version added.** The run turned «made after only the
  incumbent has been scored» into «generated without having seen the incumbent score»; the
  added «without» is where to look first.
- **`rewrite.py --only N --part K`** regenerates one part of a paragraph rewritten in parts
  and keeps the others and their hand fixes (the parts are saved in `….parts.json`, and the
  run prints each part's first words).

## 5.4.1 — October 26, 2026

From cleaning two real AI texts by hand through the gate (the English example essay: 20% of
its words edited, tells 29 -> 5, passed; the microgrid abstract: 10%, passed):

- `clean.py import` prints each changed sentence beside the one it replaced. The test cleanup
  turned «played a crucial role in addressing» into «solved» and dropped an «often»: both
  pass every check, and only reading the pair shows them. SKILL.md asks for that reading.
- The «tells score did not drop» warning no longer fires when the original scored 0: the
  abstract's slop («makes important contributions to the continuing debates», «specifically
  utilizing») is the kind `tells.py` does not count.

## 5.4.0 — October 26, 2026

**Optional step 4a: clean the slop before the base model (English, on request).**

- `scripts/clean.py export` puts the prose in a work file (LaTeX as placeholders); the agent
  edits only the sentences that carry an AI pattern; `clean.py import` is the gate. It writes
  `00-clean` only if no figure (sign included), concept, quotation, reference, link or LaTeX
  placeholder changed, and at most half of any paragraph's words and a third of the whole
  text's were edited; otherwise it writes nothing and lists the problems and the changed
  sentences. It reports the tells score before and after.
- `references/slop-patterns.md`: the 26 patterns of blader/humanizer (MIT) in our own words,
  with this step's rules on top: only the slop, the paragraphs kept, papers keep their passive
  voice and hedges.
- Step 5 then rewrites `00-clean`; steps 6 and 8 still check against `00-original`.
- `references/detectors.md`: the A/B test (with and without the cleanup, on the same text and
  day, with both controls) that decides whether the step becomes the default. Until then the
  default is the measured pipeline.
- `rewrite.py`'s warning for a paragraph kept as the original no longer blames a concept's
  spelling when no concept was lost.

## 5.3.0 — October 24, 2026

Found by running the whole pipeline (rewrite, check, join, check, PDF) on two abstracts and
a LaTeX paper with a stand-in model that makes the real one's mistakes: it drops a term on
long sources, wraps a figure in `$…$`, drops a minus sign and writes British spelling.

- `--candidates` on a long paragraph (over 150 words, or `--max-words`) built none: every
  whole-paragraph try lost a term. Each candidate is now built part by part and stays one
  paragraph.
- A paragraph or part the model gave back word for word was reported with empty brackets;
  the report now says so.
- `install_model.py` names only the GPU in `HUMANIZE_GPU_DEVICE`, and warns when that name
  is not one llama.cpp lists.

## 5.2.0 — October 23, 2026

**Sturdier guards, from what went wrong on a real abstract.**

- A figure keeps its minus sign: «-0.7» that became «0.7» was passing every guard; now it is
  a lost figure and an added one, so the try is not used and `check.py` fails. «+2.8» is 2.8,
  and «5-7» or «COVID-19» carry no negative number. «−» (U+2212) is a minus too.
- A try that adds markup the original does not have (a stray `$`, `\`, `{`, `*`, `_`, `#`…)
  is used only when every try does; the report names the symbols to delete.
- A paragraph over 150 words that fails every try is redone automatically in runs of whole
  sentences (`--max-words 100`) and stays one paragraph.
- `check.py` lists words switched between British and American spelling, and counts a file
  named twice once (it used to double its concepts).

## 5.1.0 — October 23, 2026

**An abstract stays one paragraph.** On a 250-word abstract the model kept dropping terms,
and the agent split it into four paragraphs to rewrite it, then delivered four.

- `rewrite.py --max-words N` rewrites a paragraph longer than N words in runs of whole
  sentences (never inside «et al.», math or braces), each with its own guards, and puts it
  back as one paragraph.
- `check.py` fails when a version has a different number of paragraphs than the original.
- SKILL.md: never split or merge paragraphs; a long one that keeps losing terms is redone
  with `--max-words 100`.

## 5.0.0 — October 23, 2026

**One pipeline again: the base model.** The Claude pipeline (4.1.0–4.4.1), where the agent
rewrote the prose itself, is removed: it was never measured, and chat-model rewrites scored
64–100% in Grammarly. The skill always rewrites with the local base model now.

- `scripts/prose.py` and its tests are gone; SKILL.md has one pipeline, its steps numbered
  1 to 9 (4 is the installation check), and the README has no two-pipelines table.
- `install.py` says the model and llama.cpp are needed, and how to get llama.cpp on Linux.

## 4.4.1 — October 23, 2026

- README: a bigger model is not claimed to be better. The paper (arXiv:2605.19516, §4.2)
  finds that from 4B up the meaning-versus-detector trade-off shifts only modestly, not
  necessarily for the better, and that HIP needs only a model large enough to paraphrase well.
  Qwen3-4B-Base stays the default; use a Base adapter, never an Instruct one.

## 4.4.0 — October 23, 2026

**A bigger base model.**

- `HUMANIZE_ADAPTER` points the base-model pipeline at a HIP adapter in GGUF other than the
  4B one, for a bigger base model set in `HUMANIZE_BASE_MODEL` (Qwen3-8B-Base, 14B-Base,
  Llama-3-8B). The authors' adapters are on Hugging Face; the README gives the
  `convert_lora_to_gguf.py` steps and the memory each size needs.
- `install_model.py` checks the adapter is a LoRA in GGUF, that the base model has its
  architecture, and, as before, that it is a base model and not the chat one (Qwen3 or
  «instruct»/«chat» in the name). Nothing is downloaded when both are yours.
- Not measured: every result in this repo is Qwen3-4B-Base.

## 4.3.2 — October 23, 2026

- `HUMANIZE_GPU_DEVICE=Vulkan1` pins the GPU run to one device of `llama-completion
  --list-devices`, for a laptop whose integrated graphics are listed beside the discrete GPU.

## 4.3.1 — October 23, 2026

- The GPU instructions lead with Vulkan (`-DGGML_VULKAN=ON`), which needs no CUDA toolkit
  and runs on NVIDIA too. An RTX 50 (Blackwell) needs CUDA 12.8 or later, and a
  distribution's own `nvidia-cuda-toolkit` can be older (12.4 on Ubuntu 26.04), so the
  CUDA build fails there with «Unsupported gpu architecture 'compute_120a'».

## 4.3.0 — October 23, 2026

**The GPU, on request.**

- `HUMANIZE_GPU=1` runs the base model on the GPU (`-ngl 99`), much faster than the CPU;
  a number from 2 up puts only that many of its 36 layers there, for a GPU with less than
  ~5 GB free. The CPU stays the default: on a Mac the GPU froze the screen.
- `install_model.py` says where the model runs and, with `HUMANIZE_GPU`, asks llama.cpp
  which GPUs it sees (`--list-devices`), warning when it was built for the CPU alone.

## 4.2.0 — October 23, 2026

**Bring your own Qwen3-4B-Base.**

- `HUMANIZE_BASE_MODEL` points the base-model pipeline at a `.gguf` of Qwen3-4B-Base you
  already have, in any quantization (the HIP adapter fits them all). `install_model.py` then
  downloads only the 280 MB adapter, reads the file's GGUF header without loading it, and
  refuses a model that is not Qwen3-4B (architecture qwen3, width 2560); it warns when the
  file calls itself Qwen3-4B without «Base», the chat model the method avoids.
- `install_model.py` no longer deletes a model file that does not match its checksum: it
  sets it aside as `….mismatch` and says how to use it as your own base model.

## 4.1.0 — October 23, 2026

**Two pipelines, the user chooses.** The skill's default is now the **Claude pipeline**:
the agent rewrites the prose itself and the repo's guards check every paragraph. The
**base-model pipeline** (the measured one) runs on request, and the skill offers it for the
paragraphs a detector still flags.

- `scripts/prose.py`: `export` writes the prose of a text or a paper, unit by unit
  (paragraphs and list items; in LaTeX with placeholders for math, citations and commands),
  to a work file the agent rewrites; `import` puts it back and refuses any unit that loses
  or adds a figure, loses a concept, changes a quotation, invents a reference, changes a
  link or code, breaks a LaTeX placeholder, comes out truncated or copies the original. A
  refused unit stays as the original and the exit code is 1 until all pass. An unchanged
  work file gives the paper back byte for byte.
- `join.py --only`: joins only the listed paragraphs, so the base-model paragraphs of a
  Claude-pipeline text get their rhythm and the rest is left alone.
- SKILL.md: one part shared by both pipelines (the original, what it is for, the concepts),
  then the Claude pipeline (C1–C6, with writing rules drawn from what the detectors were
  measured to react to) and the base-model pipeline (B1–B6, unchanged).
- **The Claude pipeline is not measured against detectors.** Rewrites by other chat models
  scored 64–100% in Grammarly; the docs say so wherever the default is described.
- Detectors guide: **Originality.ai** (models, free checker, cost, data kept) and
  **Turnitin / iThenticate** (not measurable from here; humanizer detection in English
  since August 2025).
- README: the two pipelines side by side. The old line "your text never leaves your
  machine" now says what is true: by hand, it does not; through an agent, the agent's
  provider reads it.

## 4.0.0 — October 23, 2026

**New name: humanize-research.** The skill now rewrites research papers (LaTeX and PDF) as
well as prose, in English and Spanish, and «humanizar-es» said neither. Agents find it as
`humanize-research`, and `install.py` installs it under that name.

- `install.py` removes an install under the old name (`humanizar-es`, and `humanize-local`)
  from the same skills folders, but leaves a git clone kept there under the old name.
- Unchanged, so nothing breaks or downloads again: the model folder
  (`~/.cache/humanizar-es/hip`), the environment variables, every script and flag, and the
  repository's own name and URLs.

## 3.4.0 — October 23, 2026

**Papers: LaTeX in and out, PDF in and out, and figures that cannot change.**

- `scripts/latex.py`: a `.tex` file is read as prose plus a frame kept byte for byte (the
  preamble, sections, equations, figures, tables, algorithms, theorems, captions, comments,
  `\iffalse`, the bibliography). Inside a paragraph, math, `\cite`, `\ref`, `\label`,
  footnotes, `\emph` and every other command become placeholders the model must keep; a try
  that loses, repeats or invents one, or writes LaTeX of its own, is not used. The
  abstract and `itemize`/`enumerate` lists are rewritten (item by item). Accent macros are
  read as letters; rewritten paragraphs come back one sentence per line. `rewrite.py`,
  `join.py`, `tells.py` and `check.py` take `.tex` files directly; `--only`, `--candidates`
  and `--take` work on them.
- `scripts/convert.py`: PDF to Markdown (pdftotext or pypdf; lines joined, hyphenation
  undone, page numbers and running headers dropped, ligatures and accents repaired,
  headings, bullets and captions recognized, equations, table cells and references fenced
  so they are kept); Markdown or text to PDF through a generated LaTeX article (Greek
  letters, math symbols and sub/superscript digits printed by pdflatex too); a `.tex`
  paper to PDF with tectonic, latexmk or pdflatex/xelatex/lualatex, BibTeX included, the
  auxiliary files kept out of the paper's folder. Without an engine it says to use
  Overleaf.
- **Figures, strictly.** `check.py` now counts every figure (a year that appears twice and
  is kept once is lost), compares decimals with their precision («0.50» is not «0.5»,
  «1.5» is not «15», «1,990» is «1990»), reads roman numerals («siglo XX», «Phase II»),
  reports figures a version **added**, and exits with 1 on any change. `rewrite.py` never
  uses a try that adds or changes a figure. `rewrite.py --take` warns when the candidate
  taken (perhaps edited by hand) changed a figure. `convert.py` reports the figures it read
  from a PDF and reads back the PDF it makes to confirm every figure is in it. A table cell
  or a section number alone on a line is no longer taken for a page number. `join.py`
  is tested never to change a figure.
- The English example now shows its added figure: "COVID-19 pandemic" for "global pandemic"
  adds a 19 the original never had, and `check.py` says so.
- `examples/latex/`: a short paper with math, citations, a figure, a table, a list and a
  bibliography, and its PDF.
- Docs: the paper workflow in SKILL.md and both READMEs; a note to check the venue's
  policy on AI-assisted writing and disclosure. 110 tests.

## 3.3.0 — October 23, 2026

**Documents, not only essays.** Emails, posts and documentation carry Markdown; until now
a fenced code block with a blank line split into two «paragraphs», code and tables were
rewritten and joined like prose, and a list came back as one run of sentences.

- `scripts/blocks.py`, shared by every script: a fenced block stays one block; code,
  tables, headings, quotations, HTML and rules are kept as they are; a list is rewritten
  (and joined) item by item, keeping its markers. Plain texts split exactly as before.
- **Fidelity guards** in `rewrite.py`: a try that changes a URL, a link target, an e-mail
  address or `inline code` is never used; a try that drops a figure of the original (a
  year, an amount) is retried, and if every try does, the closest is kept and the report
  names the figure to put back (a one-word fix).
- `check.py` lists the figures of the original missing from a version («60%» → «sixty
  percent»), matches plurals like policy → policies and luz → luces, and lets a concept
  contain `#` (C#).
- `tells.py`: formatting tells (a bold label on every list item, bold in prose, emojis,
  arrows, Title Case Headings), reported apart because they are the one kind you may fix
  by hand; three sentences in a row opening with the same word; code, tables and headings
  are not scanned as prose.
- `install_model.py` checks the free space before downloading, honours `HF_ENDPOINT` for a
  Hugging Face mirror (the sha256 check still applies), and ends with one test rewrite, so
  a llama.cpp that cannot run the model fails at install time with its error
  (`--no-test` skips it).
- CI runs pyflakes. The evidence's limits section was out of date (it said English was
  not measured).

Fixes from an independent review, each with a test that reproduces it:

- `join.py` dropped the period of initials and abbreviations and lowercased the name after
  them: «J.R.R and tolkien», «D.C and the city», «Rev and martin», «a.m and everyone»,
  «EE.UU y allí», «cap y VI», and «1 and open the box» in numbered steps. Now
  dotted abbreviations, initials, more titles (Rev., Lt., Capt.…, cap., pág.) and bare step
  numbers do not end a sentence.
- `join.py` lowercased «Microsoft's» even with Microsoft in the concepts, and «I’m» with a
  curly apostrophe; names that end like verbs (Italy, Boeing, Javier, Pilar) were left out
  of the REVIEW warning.
- `join.py --no-dashes` turned ranges (1990—2000, 1939 – 1945) and list dashes into commas.
- `check.py` hid a lost negation when the same pair appeared elsewhere ("no es" twice, one
  lost), and did not see English "n't".
- `install_model.py`: a server that closed early without an error left a partial file
  that was then called corrupted and deleted, so every retry started from zero. It now
  resumes, and an incomplete file is kept.
- `rewrite.py`: two short quotations made the words between them a «quote» that every
  try failed; a curly apostrophe counted as a changed quote; any reworded bracket with a
  number counted as an invented reference (now only a new number, numeral or name does);
  a URL inside «» was taken with the »; «60%» became «60% percent», and a % could land
  on the wrong 5.
- `install.py` refused to reinstall over its own `--symlink` install.
- `tells.py` flagged ordinary prose as strong: "not publicly disclosed", "let me know if"
  and «no dudes en» in e-mails, two paired dashes (they were counted twice), the Old
  Testament, foster care, robust standard errors. A paragraph is now worth regenerating
  with one strong tell, two stock words, or 6 points.
- A UTF-8 byte order mark (Notepad, PowerShell 5) hid the first concept and the opening of
  the text; all scripts now read it away.
- One indented line is a paragraph (essays indent their first line), not a code block.
- List bullets of 6 to 12 words without a final period were kept as titles; now only
  items of 5 words or fewer are.
- Three patterns were quadratic on pathological input (long hyphen chains, thousands of
  unclosed quotes); they are bounded now.
- 93 tests (were 65).

## 3.2.0 — October 23, 2026

**English: tells of AI writing.** A new `scripts/tells.py` scores each paragraph against the
catalog of Wikipedia's *Signs of AI writing*, as ranked by
[blader/humanizer](https://github.com/blader/humanizer): chat residue, "not only… but",
inflated significance («plays a crucial role»), stock words (delve, pivotal, furthermore…),
filler, -ing riders, triads and dashes, plus a Spanish list («juega un papel crucial», «cabe
destacar», «no solo… sino»). It names the paragraphs to regenerate and suggests a `--lead`;
it never rewrites, since a hand fix brings the chat fingerprint back. On the English
example the original scores 29 and the rewrite 17. **Not measured against detectors yet.**

- `rewrite.py --candidates` prints each candidate's tells score and lists them fewest
  first; `--max-tells N` retries a try above N and keeps the one with the fewest if all are
  above. The end of a run lists the paragraphs with strong tells left.
- `rewrite.py`, English: a paragraph that opens with "Moreover,", "Furthermore,",
  "Additionally,"… leads the model with the words after it.
- `join.py`, English: those filler openers are left out instead of becoming "and also";
  "Nevertheless," and "Nonetheless," join as ", but"; more discourse markers to cut at;
  acronyms (AI, COVID-19) and names like McDonald's keep their capitals; initials (John F.
  Kennedy) and more abbreviations (Inc., Jr., et al.) no longer split a sentence;
  `--no-dashes` turns dashes between words into commas. Spanish output is unchanged.
- SKILL.md: leave out the chat wrapper when saving the original; scan for tells in step 6;
  prefer the faithful candidate with the fewest tells in step 9.

Fixes:

- `rewrite.py` reports a failing llama.cpp (exit code and its last lines of stderr) and
  stops; it used to retry with empty output and keep the original as "truncated".
- The context grows with the paragraph instead of a fixed 4096 tokens, which a paragraph
  of ~700+ words overflowed.
- The invented-reference guard no longer takes words made of roman-numeral letters
  («(civil)», "(I think)", "(mix)") for numerals.
- `--lead` without `--only` is an error, like `--candidates`; `--only` rejects paragraph
  numbers that don't exist; `--take` checks the paragraph count against the original.
- `join.py --pauses`: a sentence that opens with "And" / «Y» no longer joins as "and and";
  a joined question is lowercased after «¿» («y ¿vienes?»).
- 65 tests (were 48).

## 3.1.1 — October 7, 2026

**English, measured.** Two AI-generated English essays went from 100% to **0% in ZeroGPT**
(one of them with selection of three paragraphs). **GPTZero in English is the next
milestone**: its newer English model (4.1o) scored 100% AI on every variant tested on the whole
document - one and two passes of Qwen3-4B + HIP, temperature 1.3, mixed paragraphs, and two
other base-model families (Llama 3.1 8B, Mistral 7B) - while a 2016 human control read 100%
human. Spanish keeps passing all three detectors. Evidence: references/evidence.md, 2d.

- Docs: English results, the GPTZero limitation in the README, the skill and the detectors
  guide; GPTZero percentages explained as confidence; famous classics as ZeroGPT false
  positives (Emerson, 64.5%).

## 3.1.0 — October 7, 2026

**ZeroGPT passes.** The same 1,990-word essay now scores **0% in ZeroGPT, 0% and 0% in
Grammarly and 0% AI / 98% human in GPTZero**, keeping 24 of 24 concepts and its two
quotations verbatim. A fourth stage, selection, was added after taking ZeroGPT apart:
it scores sentence by sentence and weighs by words, so rhythm alone made it worse
(34% → 52%), and the base model gives a different version of a paragraph each run.

- `rewrite.py --candidates N --only K`: N acceptable versions of each listed paragraph in
  `<output>.candidates/`, without touching the output; `--take K=FILE` adopts one.
- `rewrite.py --lead "Desde la"`: other opening words. The original's first two words
  («Uno de los problemas…») made the model rebuild the stock sentence detectors flag.
- `rewrite.py --temperature` (1.0 by default; 1.1 gives more varied candidates).
- Fidelity guard: a try that changes a quotation of the original or adds a reference in
  brackets the original never had is rejected (the model wrote «(De Anima, libro i,
  cap. vi)» on a test essay).
- `join.py --pauses`: a sentence that opens with «Pero» / "But" joins as «, pero»; it
  used to produce «y pero».
- Docs: the method in four stages, what each detector measures, the ZeroGPT experiments
  (references/evidence.md, section 2c), and the selection step in the skill. 48 tests.

## 3.0.0 — October 7, 2026

A pipeline for two audiences: Spanish and English, with docs in both. Same name and URL,
so existing installs keep working.

**Measured:** a 1,990-word essay reached **0% and 0% in Grammarly** (two halves) and
**0% AI / 99% human in GPTZero**, keeping 24 of 24 key concepts. ZeroGPT does not pass yet.

- **Rhythm in blocks:** `join.py --pauses 2` leaves two or three periods per paragraph, in
  blocks of uneven length of at least two sentences, cutting first where a sentence already
  opens with a discourse marker. It reads like a person instead of one endless sentence.
  (6% while a block could be a single sentence; 0% once not allowed.)
- **Copy guard:** `rewrite.py` retries a try that copies more than 60% of its words from the
  original in runs of 8+ words (`--max-copied`); if every try does, it keeps the least copied
  one and warns. HIP had left half a paragraph word for word.
- **Regenerate instead of rewriting by hand:** `rewrite.py --only 6,11` redoes just those
  paragraphs and keeps the rest with their fixes. A hand fix is one to three words; bigger
  hand fixes kept half an essay at 3%, regenerating them gave 0%.
- `--tries` defaults to 6 (only a failing paragraph uses them); the warning for an unchanged
  paragraph names the concept it kept losing.
- English: `join.py` detects the language and links with "and"/";"; `check.py` knows English
  negations; `rewrite.py` restores the `%` sign the HIP adapter drops.
- Scripts in English: `rewrite.py` (was `hip.py`), `join.py` (`unir.py`), `check.py`
  (`verificar_fidelidad.py`), `install_model.py` (`instalar_hip.py`). The old names, flags
  (`--conceptos`, `--pausas`…) and environment variables still work. The model stays in
  `~/.cache/humanizar-es/hip`: no re-download.
- Docs: `README.md` (English) and `README.es.md` (Spanish), with the method, the controlled
  measurements and how we measure (a human control and the AI original in every session).

---

*Earlier entries, in Spanish:*

## 2.1.1 — 2 de octubre de 2026

- README en español y en inglés (`README.en.md`), con preguntas frecuentes.
- Tabla de detectores: optimizado para Grammarly; GPTZero y ZeroGPT, próxima mejora.
- `CITATION.cff` para citar el repo. Licencia a nombre de ervin-mo.

## 2.1.0 — 1 de octubre de 2026

Funciona en **Windows** igual que en macOS y Linux, sin Git Bash ni WSL.

- `install.py` e `instalar_hip.py` reemplazan a los `.sh` (que quedan como atajos). La
  descarga del modelo ya no necesita curl ni shasum, y si se corta sigue donde se quedó.
- `hip.py` le pasa el prompt a llama.cpp en un archivo UTF-8 y lee su salida como UTF-8: en
  Windows los acentos se habrían roto. Baja la prioridad del proceso también en Windows.
- `hip.py` encuentra llama.cpp recién instalado con winget sin abrir otra terminal, y
  acepta la ruta en `HUMANIZAR_LLAMA`.
- Las pruebas corren en Ubuntu, macOS y Windows, con una prueba de punta a punta de
  `hip.py` con un llama.cpp falso.
- `.gitattributes`: los scripts conservan los saltos de línea de Unix al clonar en Windows.

## 2.0.1 — 1 de octubre de 2026

- Evidencia: un tercer ensayo (690 palabras) pasó a **0%** en Grammarly en la primera
  corrida de la skill hecha por un agente, con 9 correcciones a mano y 18 de 18 conceptos.

## 2.0.0 — 1 de octubre de 2026

La repo queda solo con la receta que funciona: **`hip.py` → corrección a mano →
`unir.py`**. Dos ensayos completos a 0% y 10% en Grammarly, sin errores.

- `instalar_hip.sh` ya no convierte nada: baja el adaptador HIP ya convertido a GGUF desde
  las descargas del repo y verifica los dos archivos con sha256. Sin paquetes de Python.
- Se quitaron el cubo, la ruleta, `ensuciar.py`, el detector local, la cadena de
  traducción, la guía de reescritura a mano y los ejemplos viejos. Lo que se probó y no
  funcionó queda resumido en `references/evidencia.md` §4.
- Ejemplo nuevo en `ejemplos/`: un ensayo, su reescritura corregida y el resultado.
- `SKILL.md` reescrita para que el agente siga la receta de punta a punta.

## 1.4.0 — 1 de octubre de 2026

- **`scripts/unir.py`** reemplaza a `ensuciar.py` en la receta: une las oraciones de cada
  párrafo con «y», sin meter errores de ortografía ni de puntuación. `hip.py` + `unir.py`
  llevó dos ensayos completos a 0% y 10% en Grammarly.
- La receta corrige a mano **antes** de unir: corregir después subía el número.
- `ensuciar.py` queda como alternativa; ya no se recomienda.
- Evidencia nueva en `references/evidencia.md` §4f: qué castiga Grammarly, un cambio a la vez.

## 1.3.0 — 1 de octubre de 2026

- **Receta nueva, local y sin costo:** `scripts/hip.py` reescribe cada párrafo con un
  modelo base (Qwen3-4B-Base + adaptador HIP de Xu et al. 2026) y `scripts/ensuciar.py`
  le quita la redacción demasiado limpia. Un ensayo completo de 1,150 palabras: 8% IA en
  Grammarly, en unos 4 minutos de CPU.
- `scripts/instalar_hip.sh`: descarga el modelo y convierte el adaptador (~5.5 GB).
- `ensuciar.py` no toca la ortografía por defecto; `--ortografia` es opcional.
- El cubo pasa a ser la alternativa con API.
- Corregido: si el revisor del cubo contestaba vacío, se vetaba el lote entero y el
  párrafo se quedaba sin tocar. Ahora reintenta y parte el lote.
- Corregido: el `*` de los conceptos por prefijo ya no se cuela al texto.
- Evidencia nueva en `references/evidencia.md` §4e.

## 1.2.0 — 30 de septiembre de 2026

- **El cubo** (`scripts/cubo.py`): reescritura oración por oración guiada por un detector
  local. Llevó un párrafo de 100% IA a 0% en Grammarly y 99% humano en CleverHumanizer.
  Trabaja párrafo por párrafo por defecto; `--texto-completo` gira todo a la vez.
- Detector local (`scripts/sustituto.py`): Binoculars + Fast-DetectGPT sobre Qwen2.5.
- Revisor de sentido: otro modelo veta los giros que cambian, inventan o no tienen lógica.
- Varias familias de generadores (`HUMANIZAR_MODEL="a,b"`) y aviso de palabras repetidas.
- `scripts/calibrar.py`: mide qué tan bien predice el detector local a tu detector.
- `scripts/ruleta.py`: sinónimos guiados por detector (opcional; no movió a Grammarly).
- La skill funciona en Claude Code, Codex, OpenCode, Antigravity y DeepSeek Harness;
  `install.sh` instala por defecto en `~/.claude/skills` y `~/.agents/skills`.
- CPU por defecto: en Mac, la GPU traba la pantalla.

## 1.1.0 — 30 de septiembre de 2026

- `scripts/estilo.py` (sin dependencias) y `verificar_fidelidad.py` configurable, con
  detección de negaciones perdidas.
- Benchmark revisado con dos rondas de refutación; resultados de Grammarly.

## 1.0.0

- Guía de reescritura, benchmark inicial y scripts de medición.

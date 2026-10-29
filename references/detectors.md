# How to measure

## Grammarly

[grammarly.com/ai-detector](https://www.grammarly.com/ai-detector). This is the detector
the recipe was measured and tuned for.

- **Limit:** on a free account, about 3 scans a day. After that, the button stops starting
  a scan without showing any error. It resets after 24 hours.
- **Clear the box before pasting.** If older text is left below, Grammarly only analyzes
  the first 1,400 words and mixes both versions.
- **Read the big number:** "X% of this text appears to be AI-generated".
- The detector built into Grammarly's document editor, on a free account, always shows
  20%: it can't be used to measure.

- **Texts over ~1,400 words: measure them in two halves.** Otherwise Grammarly only reads
  the beginning.

## GPTZero

[gptzero.me](https://gptzero.me). The free scan reads the first 10,000 characters, and a
free account has a few scans a day ("0 scans left" when they run out).

- **Read "AI X%"**, not the mixed one. "AI 0% · Mixed 1% · Human 99%" means "entirely
  human"; the three always add up to 100%.
- Text past 10,000 characters is not read: scan the rest separately.
- **The percentages are confidence**, not a share of the words: "Human 100%" means the model
  is sure the whole text is human.
- **Spanish and English use different models** (4.1m and 4.1o). The English one recognizes
  base-model paraphrases; the Spanish one does not.
- **Measure whole documents.** A ~100-word paragraph can read 99% human while the same text
  at 285 words reads 100% AI.
- Free accounts get 10,000 credits a month (about one per word): a 600-word essay costs ~600.

## ZeroGPT

[zerogpt.com](https://www.zerogpt.com). No account, 15,000 characters. Reads "X% AI GPT"
and highlights in yellow the sentences it flags: that is the list to regenerate.

- **Deterministic:** the same text always gives the same score, so a change you see is
  real.
- **Sentence by sentence, weighed by words:** a long sentence with one textbook clause is
  flagged whole.
- **Measure the format you will hand in.** Headings and bibliography change the score.
- **Brittle:** after any fix, measure again.
- **Famous classics are false positives:** Emerson's *Self-Reliance* (1841) scored 64.5% AI.
  Use an obscure human text as control (we used Hacker News comments from 2016: 1.5%).

## Originality.ai

[originality.ai](https://originality.ai). Models 5.0 and 5.0 Max since October 2026 (the
older Lite, Turbo and Academic models were retired in September 2026); 5.0 Max is the one
it recommends for high-stakes decisions. It detects the language by itself: English and
Spanish are among its 30.

- **Free checker:** 3 scans a day, up to 2,000 words each. Beyond that it is paid: about
  $0.01 per 100 words on 5.0 and $0.10 on 5.0 Max (pay-as-you-go credits, or a monthly plan).
- **At least 100 words**; below that the score is unreliable. Measure whole documents, as
  with the others.
- **Read the AI score of the whole text**, and the highlighted passages: those are the
  paragraphs to regenerate.
- **It claims to catch humanizers** (it reports 92% on a benchmark of humanized texts with
  no human controls), so a version that passes the others may not pass it. Treat it as the
  strictest of the public detectors.
- **Your text stays in its dashboard** until you delete the scan, and scans may be used to
  improve its service unless you turn that off in the settings. Delete the scans of an
  unpublished paper.

## Turnitin and iThenticate

What journals, conferences and universities run. **There is no way to measure them from
here:** Turnitin's AI detection is sold only to institutions, and iThenticate's AI add-on
only to publishers (its pay-per-document credits for individuals include no AI score).
What is known, from Turnitin's own notes (October 2026):

- English, Spanish and Japanese, then Arabic, Dutch, German and Turkish; 300 to 30,000 words
  of prose. A score from 1% to 19% shows as "*%", without highlights.
- **Since August 2025 it counts English text from "AI bypassers" (humanizers) as
  AI-generated.** An independent study (Int. J. Educational Integrity, 2026) found it
  underestimating humanized and mixed papers and flagging no human ones; nobody has
  published how it scores base-model rewrites.
- Its release notes name the generators each model was trained on for some languages
  (Claude among them for Arabic); for English they do not say.

So the public detectors are a proxy, never a promise: a paper that passes Grammarly,
GPTZero, ZeroGPT and Originality.ai can still be flagged by Turnitin.

## Always with two controls

In every session, before comparing versions:

1. **A human control:** a text you wrote without AI, of the same kind and similar length.
   It must come out human.
2. **The AI original:** it must come out as AI.

If either fails, the detector isn't measuring that kind of text (QuillBot scored our AI
original 100% human) or it is throttling you (GPTZero, after many scans from one browser,
scored a 1914 text 100% AI). Then its number for your version means nothing. And measure
the reference version again in the same session: don't compare with a number from hours
before.

## A/B test: does step 4a (cleanup before the model) help?

Step 4a is not measured. It becomes the skill's default only if this test shows it helps.

1. **One text, two arms.** Take one English AI text (300 to 1,400 words). Arm A: the
   pipeline as it is (steps 5 to 8 on `00-original`). Arm B: step 4a first, then steps 5 to 8
   on `00-clean`. Same `concepts.txt`, same `--pauses 2`, both arms on the same day. Save
   `02-final-A.txt` and `02-final-B.txt`.
2. **Same fixes.** Make only the 1–3-word fixes each arm's own review asks for, and count them:
   more hand fixes in one arm would bias it.
3. **One session, five texts.** In each detector, in one sitting: the human control, the AI
   original, `00-clean` (cleaned but not rewritten), arm A and arm B. The two controls must
   pass first (above). Paste each as the user will hand it in.
4. **Record** in `references/evidence.md`, one row per detector: the five scores, the date,
   the detector's model or version, the word count, the hand fixes per arm, and `tells.py`'s
   total for A and B.
5. **Read it honestly.** One text is a hint, not a result: B counts as better only if it beats
   A in at least two detectors on at least two different texts, with neither control failing.
   A tie keeps the default as it is (arm A costs one step less).

`00-clean` on its own also tells you something: if it already passes a detector, the slop was
what the detector saw; if it fails and arm B passes, the base model did the work.

## Other detectors

They don't agree with each other: a version that passes one may not pass another. If you
care about a detector, measure in that one.

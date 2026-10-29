# Slop patterns for step 4a (cleanup before the base model)

Step 4a is optional, English only, and runs only when the user asks for it ("clean it
first"). You edit the AI patterns out of the original; then the base model rewrites the
cleaned text. `scripts/clean.py import` refuses a cleanup that changes a figure, loses a
concept, alters a quotation or a LaTeX placeholder, or edits more than half of a paragraph's
words or a third of the whole text's.

The catalog below is the 26 patterns of [blader/humanizer](https://github.com/blader/humanizer)
(MIT), itself built on Wikipedia's
[Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing), summarized
here in our own words. `scripts/tells.py` counts many of them.

## The rules of this step (they override the humanizer's own workflow)

The humanizer skill rewrites freely: it merges and splits paragraphs and restates every
point. Here you do much less, because the base model does the rewriting next.

1. **Edit only sentences that carry a pattern.** Every other sentence stays word for word.
2. **Keep the paragraphs.** Never merge, split or reorder them. An abstract stays one.
3. **Keep every fact.** Each figure as written (signs included), name, term, negation, hedge
   the source supports, citation and quotation. Cutting a pattern never cuts a claim: keep the
   fact under the dressing.
4. **Add nothing.** No new fact, example, date or source; a simpler sentence instead.
5. **Papers keep their register.** Passive voice (§11) and hedges the authors chose are normal
   in a paper; leave them. Formatting patterns (§19–§21) do not apply to LaTeX prose.
6. **LaTeX placeholders** `[1]`, `[2]`… stay, each once, next to the words they belong to.

## A. Staging instead of stating (act on one sighting)

1. **Not X but Y.** "not just X, but Y", "it's not X, it's Y", the contrast split over two
   sentences. State Y. Keep a contrast only when X is a belief the text corrects.
2. **One-line closers.** A short sentence that restates the paragraph ("That distinction
   matters."). Cut it unless it adds a fact.
3. **Sayings that sound deep.** "at its core", "the real question is", "X is the Y of Z".
   Replace with the specific claim.
4. **Staged run-up.** "Let's dive in", "Here's the thing", "It is important to note that".
   Delete the run-up and keep the point.
5. **Arguing with no one.** "This is not to say…", "One might be tempted to…" against an
   objection nobody raised. Delete; state any real claim plainly.

## B. Rhythm by rule

6. **Forced triads.** Three items where the content has two or four. Keep what the source has.
7. **Repeated sentence openings.** The same subject or opener several times in a row.
8. **Dashes as the universal connector.** Em or en dashes between clauses everywhere: use a
   period, comma, colon or parentheses. (Number ranges like 66–80% are not this.)
9. **Stacked qualifiers.** "could potentially", "might arguably". Keep one qualifier only where
   the source has real doubt.
10. **Hyphenated pairs after the noun.** "the report is high-quality" → "high quality".
11. **Passive voice and missing subjects.** Weak alone; in papers, leave it.

## C. Inflation and borrowed authority (keep the fact, drop the dressing)

12. **Overused AI words.** additionally, crucial, delve, enhance, foster, garner, intricate,
    interplay, key (adjective), landscape, pivotal, showcase, tapestry, testament, underscore,
    vibrant… Use the plain word, or none.
13. **Inflated significance.** "plays a crucial role", "a pivotal moment", "evolving landscape",
    "setting the stage for". Say what the thing does.
14. **Vague connection.** "associated with", "linked to" where the source gives the relation.
    Name it; if the source does not, keep "associated with".
15. **Shallow -ing riders.** ", highlighting…", ", underscoring…", ", ensuring…" bolted on a fact.
16. **Sales language.** groundbreaking, renowned, profound, rich, a diverse array of.
17. **Borrowed authority.** "experts argue", "studies show" with no source. Keep a named source;
    do not invent one.
18. **Avoiding is, are, has.** "serves as", "stands as", "boasts", "features". Use is/are/has.

## D. Formatting by rule (text and Markdown only)

19. **Bold as decoration**, and a bold label on every list item.
20. **Decorative headings**: Title Case, emojis, arrows.
21. **Curly quotes** where the format uses straight ones (weak alone).

## E. Leftovers from the chat and the draft (remove outright)

22. **Chatbot residue.** "Certainly!", "I hope this helps", "Let me know if…".
23. **Knowledge-limit disclaimers.** "as of my last update", "based on available information".
24. **A heading repeated in the first sentence.**
25. **Writing about the document.** "This section provides an overview of…".

## F. Writing for the wrong reader

26. **Re-explaining what the reader knows.** Mostly for replies; rarely applies to a paper.

## When not to act

Leave a pattern inside a quotation, a title, a proper name, or where the text discusses the
phrase rather than uses it. One dash or one list of three is ordinary prose.

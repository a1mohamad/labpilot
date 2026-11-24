# Section 17.24: slice 6, follow-ups and respond

[Docs home](../README.md)

#### 17.24 Slice 6 is DONE: follow-ups, `respond` for 0, 1 and 2 files, the door and the closing review — 2026-10-21 and 22

**Status: DONE.** Slice 6 has TWO lessons, as D56 planned. The user typed the product code on branch `feat/follow-ups` (made from the tip of `feat/plan-to-run`). Lesson 1 is the follow-up rewrite. Lesson 2 was first built as "2" and "2b" and merged into one lesson at the user's request. It holds the prompts for 0, 1 and 2 files, the budget, the API and the page. **For a while Claude called the API and the page "lesson 3". That was Claude's mistake: the plan has no third lesson, and D56 puts the door inside lesson 2.** The user's question ("this slice only has 2 lessons") is what found that the door was still missing, and the door was then built before the review pass.

**Lesson 1 (2026-10-21): a follow-up becomes a standalone question.**

- `prompts/followups.py` holds the instruction `FOLLOW_UP` (two examples, "copy a specific question exactly", "never guess"), `FOLLOW_UP_VERSION = 1`, `FOLLOW_UP_MAX_TOKENS = 3,000`, `RECENT_QUESTIONS = 4`, `QUESTION_CHARS = 300`, `LAST_ANSWER_CHARS = 2,000` and `MAX_REWRITE_CHARS = 600`. `agent/rewrite.py` is the node. `api/followups.py` gives it `make_rewriter(client)` and `last_answer_text`.
- It is the first reader of `history`. The graph starts `START -> rewrite -> {plan, summarize_a, summarize_b} -> measure`. With no history, or when the rewrite equals the question, the node returns `{}`. A rewrite that is blank, has more than one line, or is longer than `max(600, len(question))` is refused and the next tier writes it (D50). If every tier fails, the question is kept as it was.
- **`last_answer` (D58).** The chat kept only the questions, so "do the second one" had nothing to point at. The state has a new key `last_answer` with the REPLACE rule (a new answer replaces the old one). `remember` writes the END of the answer, at most 2,000 characters, with a leading "…" when it was cut. No saved table, row or prune query changed: the saver stores the new key like any other.

**Lesson 2 (2026-10-22): `respond` for 0, 1 and 2 files, one prompt function, the budget and the door.**

- `prompts/answer.py` (new) holds three instructions and `instructions_for(files)`: `CHAT`, `ONE_FILE` and `TWO_FILES` (D60). `build_chat_prompt` is the prompt without parts.
- `api/prompting.py` has ONE function, `build_answer_prompt(chunks, *, question, files, totals, summaries, last_answer)` (D59). `respond` counts the files and calls it with `files=` and `last_answer=`. `build_report_prompt` is gone. `REPORT` stays in the code only as the frozen baseline of the smoke tests.
- An empty id means "no file". `measure_sides` skips it, the summary node returns nothing, and the planner already made a default plan for no files. A chat question therefore makes only the rewrite call (when there is history) and the answer call.
- The last answer is in every prompt, after the parts and before the question, written by one function (`last_answer_block`).
- The door (D62): `CompareRequest.a` and `.b` are optional, `ask()` puts a lone artifact in the slot of its own side, the reply lists only the sides that had a file, and the page asks with 0, 1 or 2 stored sides.
- The budget and the outline (D61): `PROMPT_BUDGET` is 30,000, `fits_whole` prices the outline by files, and a "fits" verdict now keeps every part.

**What was measured, and it is SMALL.** Exit `194.5.192.239`, AS57568 ARVANCLOUD, Frankfurt, Google 200 (earlier runs the same ISP). Pair: `quora_siamese` (100 parts). Findings are counted against the 19 of `EXPECTED.md` as findings / the 5 that carry the story, by a regex screen.

| | REPORT (old) | R2 (answer first) | R3 / final `TWO_FILES` |
|---|---|---|---|
| short questions, right numbers in the first lines (Flash-Lite 3.5 and 3.1) | plain 1 of 2, clip 0 of 2 | 4 of 4 | **4 of 4** (answers 3-4 times shorter) |
| default question, Cline GLM-5.3 | 16 / 5 | 16 / 5 | 15 / 5 |
| default question, Gemini 3.6 Flash | 15 / 5 | 10 / 4 | 14 / 5 |
| default question, Gemini 3.8 Flash, key 1 and key 2 | not run | 13 / 4 and 14 / 5 | 15 / 5 and 12 / 5 (final text) |
| default question, Flash-Lite 3.5 | 6 / 3 | 7 / 3 | 7 / 2 (R3), 6 / 3 (final) |
| default question, Flash-Lite 3.1 | 8 / 4 | 5 / 2 | 7 / 4 (final) |
| "do the causes add up to the gap?" (the right answer is NO: sizes sum to about 6-8 points, the gap is 2.5) | right on 1 of 4 tiers | right on 1 of 8 | right on 2 of 3 (R3); both 3.8 runs right, Flash-Lite 3.1 wrong, 3.5 silent (final) |

Also: the follow-up "Explain that more simply." with and without the last answer in the two-file prompt (Flash-Lite 3.5, Gemini 3.6) showed **no visible difference**; the model wrote a full comparison both times. The header sizes are REPORT 2,100 bytes and `TWO_FILES` 2,914.

> **THESE NUMBERS ARE A SMALL SAMPLE, AND NO DECISION RESTS ON THEM YET.** One pair, at most 8 tiers, ONE run per cell (at temperature 0 a repeat gives the same text, so a repeat adds nothing), findings screened by regexes that were wrong more than once (a screen, not a score), the pair was almost whole (about 29,000 of the budget), and 5 calls were lost to Google 503. R3 beat the old report on short questions and on the "adds up" verdict and was a little behind it on coverage on two tiers. That is a direction, not a result. **Slice 13 must run more (M18): more pairs (the new pair of slice 12), more tiers, several worded versions of each question, the SEARCH path, and the three instructions together. It may find better instructions and prompts, or a better approach altogether** (for example one call for the answer and a second for the arithmetic, or the verdict from Jev). D60 is a first choice, not a decision.

**The closing review of slice 6 (2026-10-22).** The standing question was: which real failure is still unprotected?

Four real defects were found, and none of them was on a list.

1. **A misspelled name, in four files.** The typed `last_answer_block` was `last_asnwer_block` everywhere, so the names did not match the tests and the page of the package imports. Renamed back; `ruff` re-sorted one import block that the rename had moved.
2. **A call that crashed every 0-file question.** `build_answer_prompt` called `build_chat_prompt(chunks, question=question)`, which raises `TypeError` (two values for `question`). The tests written beforehand caught it the first time they ran.
3. **A "fits" verdict that could still lose parts** (D61). Found by a probe, not by a test: 2 of 280 parts were lost with no error. The exact outline charge would have made it more common, so both were fixed together.
4. **A lone artifact in the wrong slot** (D62). The graph reads slot `a` as side A. A subject sent alone in slot `a` was searched as a side A that did not exist, and the search failed on a missing key. It was reachable only once the door opened, so it was found while building the door.

Tests added: `test_answer.py`, `test_last_answer.py`, `test_respond_files.py`, `test_answer_prompt.py`, `test_reading_files.py`, `test_fits_whole.py` (11, including a sweep of sizes that must keep every part with the largest summaries and last answer), `test_ask_slots.py` (8), the door tests in `test_compare.py` (5 new), 3 page-contract tests, 3 real-database tests over HTTP (no file, one file in either slot), 6 new ones in `test_ask.py` and 2 store tests for `files`. **Deliberate breaks: 22 on lesson 2 (all caught) and 13 on the door and the outline charge (12 caught).** The survivor was "the page lists both sides always": the page's rendering has no automated test, so it was checked by hand in a real browser against a stub server (0, 1 and 2 stored sides: the ids sent, the prefilled question, the button, the coverage tags). It stays an untested rendering, as the page is thrown away in Step 3.

**Added the same day (2026-10-22), after the review pass: the page keeps the stored files across a refresh, and an empty id clears the old summary.** The user asked whether the files survive a refresh and whether the page must keep them. The files stay in the database (nothing deletes an artifact, 17.6). The PAGE forgot them: the ids lived in a JavaScript variable, so after a refresh both slots were empty while the chat id (saved in `localStorage`) went on with the old chat. The person had to upload again and wait for the whole ingest again, and the chat then held a summary of a file that the new message did not send.

- `web/app.js` saves `stored` in `localStorage` under `labpilot.artifacts` every time an upload changes it, and restores the slots when the page loads (`restoreStored`). If the server answers `404 unknown_artifact` for a saved id, the page empties that slot, saves, and says "A file this page remembered is no longer stored, so its slot was emptied. Add it again."
- `summarize_node` returns `{"summary_a": ""}` (or `summary_b`) for an empty id and not `{}`. Before, the summary of an earlier message stayed in the saved chat when a later message sent fewer files. It was found by running one chat through the graph with 0, 1, 2 and then 1 files.
- Tests: `test_chat_files.py` (3: the chat grows from 0 to 2 files, the last answer follows, a left-out file leaves no summary), one real-database test (`test_a_chat_that_sends_fewer_files_drops_the_summary_of_the_missing_one`) and 3 page-contract tests (the key is saved, read back and restored; it is saved at each change; the error code is the one the server sends). **5 deliberate breaks, all caught.** The first run of the page breaks showed two survivors, because the contract test only looked for names; a test that pins the save after each change fixed that. The refresh and the 404 were also checked in a real browser against a stub server: a refresh restores the slot and the question is asked with its id, and a remembered id that the server does not know empties its slot and shows the message.
- This is a STOPGAP. The proper version belongs to Step 3 (see "Notes for Step 3 from slice 6" in the UI section).

**Suite on 2026-10-22: 1653 passed, 120 skipped.** Unit and api: 1496 passed, 5 skipped. Database (integration): 157 passed. `ruff check` and `ruff format --check` are clean. The weekly smoke run was NOT run (it spends quota); its premise was changed (the search path is forced, see D61) and is unproven until a real run.

**Open items (none is fixed).**

- **M18** (above) and the other slice 13 measurements: M4, M5, M6, M7, M8, M15, M16, M17.
- `retrieval/gate.py` still has no caller (D57). `REPORT` has no caller in the product, only in the smoke baseline.
- The history keeps the questions only. The rewritten question is not shown to the user (the reply and the page could carry it).
- The flat `OUTLINE_BUDGET` of 4,000 per side still caps the long outline of a searched prompt. It is a guess, as it always was.
- `_in_their_own_slots` reads the side from the id prefix (`A-`, `B-`). If the id format changes, it must change too.
- The question prefilled for 0 files ("Ask a question, or add files to compare.") is sent as it is when the person does not edit it.
- `store/writer.py` still uses `executemany` (17.23): try one big upload to Supabase once.
- The smoke test `test_ask_answers.py` forces the search path by lowering one constant; a real run with `--run-smoke` has not been done since.
- Branch: slice 6 is on `feat/follow-ups`, pushed. Slice 7 starts on a NEW branch from its tip (ask the user first).

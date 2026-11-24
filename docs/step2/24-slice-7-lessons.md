# Section 24: slice 7, lessons 2 and 3

[Docs home](../README.md)

### 24. SLICE 7, LESSONS 2 AND 3, EVALUATION LOOPS AND THREE NEW DECISIONS — 2026-10-24

*Lesson 2 was typed by the user and its tests are green. Lesson 3 was built and tested in a scratch copy first, then typed by the user, and its tests are green. After the user asked GPT for advice, a talk about evaluation loops and sub-agents produced three decisions (D74 to D76). The user asked for them, and for lesson 2, to be written down.*

#### 24.1 Lesson 2 is DONE: the check of each claim (typed on `feat/check-claims`, committed as `4c90193`)

**The flow now.** After the search (or after stuffing) the plan decides (D64). If `extract_claims` is listed, it runs: one call reads A whole and now gives a QUOTE for every claim. Then one `check_one` runs for each claim through `Send`, all at the same time. Each searches B with the claim's own text (`EVIDENCE_SIDE = "B"`, the first `EVIDENCE_PARTS = 6` parts of the fused search, no rerank: M24), then one call says match, mismatch or absent. `respond` reads the findings, and `remember` clears `claims` and `findings` with `Overwrite([])` at the end of the message (D67).

| file | its job |
|---|---|
| `agent/_quote.py` | `has_quote(part, quote)`: true when the cleaned quote is inside the cleaned part. Both sides: spaces collapsed, `\`, `$` and `*` removed, lower case. A blank quote is never a quote |
| `agent/claim.py`, `agent/claims_schema.py` | `Claim(text, source, quote)`. The model must give a quote for every claim. `read_claims` drops a claim whose quote is not in the part it named, and refuses the whole answer when none is left (`ClaimsError`, so the next tier writes a new one) |
| `agent/finding.py` | `Finding(claim, verdict, kind, source, quote, note)` and `UNCHECKED` |
| `agent/check_schema.py` | the tool `give_verdict`. `VERDICTS` are match, mismatch, absent. `KINDS` are choice, mistake, unclear, and only a mismatch needs one. `read_finding`: an absent needs no part, the other two need a part number and a quote that is in that part |
| `agent/check_one.py` | `make_check_node(search_one, check)` |
| `agent/fan_out_claims.py` | one `Send("check_one", ...)` for each claim, with only side B. With no claims the run goes straight to `respond` |
| `agent/remember.py` | also clears `claims` and `findings` |
| `agent/graph.py` | `extract_claims=` and `check=` are optional arguments, and `after_search` sends the run to `extract_claims` only when the plan lists it |
| `prompts/checks.py` | `CHECK` (version 1), `CHECKS_NOTE`, `build_check_prompt`, `render_checks` |
| `api/checking.py` | `make_checker(client)` |
| `api/chains.py` | `for_claims(client)`: the same tiers with the Flash-Lite ones moved to the front. Claims and checks use it. It is a first version of the cheap chain, and slice 11 builds the real one |
| `api/prompting.py` | `checks_text`: the findings go into the `prior` block of the report prompt, mismatch first, then absent, unchecked and match. A line is cut at 300 characters |
| `api/asking.py` | the wiring. `Claim` and `Finding` are in `SAVED_TYPES` (D37) |

`CLAIMS_VERSION` is 2 (the quote was added).

**Result.** The whole suite on 2026-10-24: 1834 passed, 137 skipped, 15 minutes (database tests included, `--run-smoke` not used). Before it was typed, in a scratch copy: 1662 unit and api tests, 167 database tests and 38 of 38 deliberate breaks caught. A first live look at the quote rule: 5 claims asked, 1 dropped, 4 kept, where lesson 1 gave 15 on the same paper. That is one try, so M10 and M11 must check whether the quote rule makes the list shorter.

**The quote tests of 2026-10-24** (Flash-Lite 3.5 only, one run for each cell, the paper and the code of the sample pair; the scripts are in the session scratchpad, not in the repository):

1. Gemini does not keep the field order of our schema. So "quote before claim" cannot be forced or seen, and only the wording of the instruction differs.
2. Wording A (today: claim, part, quote), B (part, quote, claim) and C (the user's: write the quote for your claim) behave the same on about 50 pairs read by hand. No claim disagrees with its quote. B looked best by 1 to 3 claims, which is not proof, and C was not better. Decision: keep `CLAIMS_VERSION = 2` for now.
3. A real defect: `_plain` removed too little, so TRUE quotes were dropped over markup (the `$` of a formula, the `**` of bold). The fix removes `\`, `$` and `*` on both sides. 15 of 20 quotes of the paper were kept before and 19 after. None of the dropped ones was invented.
4. The quote is checked against the header plus the text (the `parts`), not the text alone.
5. Merged facts: a wording that asks for one value in each claim (D), or also for rules and steps (E), gives single-fact claims but MORE of them. E reached the cap of 15 and lost the results and the threshold rule. Decide wording E and the cap (`CLAIMS_WANTED` 15, `MAX_CLAIMS` 20) together at M10, counting the extra check calls (with M24).

**Traps found while the user typed.** Each was caught by a test, and none reached production.

- A node added as `"check"` while the arrows said `"check_one"` (LangGraph: "edge starting at unknown node"). The name in `add_node` must be the same text as in every edge.
- A node that returned the key `found` (the list of search chunks) and not `findings`. A `Finding` would have gone into the list of chunks, with no error.
- The two arguments of `has_quote` swapped. Every real quote would be refused.
- `kinds` and `parts` for `kind` and `part`, `make_checker(conn, client)` for `make_checker(claims_client)`, `finding` for `findings`, an import of `labpilot.agent.finding` from `api/` instead of the front door, and a `]` in the wrong place in `Callable[[A, B], C]`.
- Failures that share one message are one bug: 22 collection errors were one wrong name.

#### 24.2 Lesson 3: the bounded retry loop (D4). DONE 2026-10-24: built and tested in a scratch copy first, then typed by the user

**Status: DONE 2026-10-24.** The user typed it on `feat/check-claims` and the tests passed. It is committed together with section 24 as `bd46262` (13 files: `agent/check_one.py`, `agent/graph.py`, `api/asking.py`, `api/requery.py`, `prompts/requery.py`, `prompts/__init__.py`, five test files and the two docs). Checked by Claude after the commit: unit and api tests 1705 passed, 5 skipped; `ruff check` and `ruff format --check` clean on 370 files. The user's count for the full suite with the database tests was not written down, so the last full count on record is 1834, from before lesson 3. The deliberate breaks of the next paragraphs were run in the scratch copy only, not again on the typed files.

**Design, decided on 2026-10-24.**

- Only a claim whose verdict is `absent` is searched again, at most `MAX_RETRIES = 2` times. The number is a first guess. D4 and the Dude paper both say that the improvement stops after 2 rounds, and the paper's numbers are author-reported. The model writes the new query, and the code decides everything else.
- The loop is a plain `for attempt in range(MAX_RETRIES + 1)` inside `check_node`, NOT a cycle in the graph (the plan said a cycle with a `tries` key). The claims run together through `Send`, and the state is one dictionary for the whole chat. A `tries` key would be one number shared by all claims, and the input of a `Send` is not in the state after the node. So the counter, the queries tried and the last finding are local variables of one call of the node. No new State key and no new error type are needed.
- The loop stops when: the verdict is not absent (found, or unchecked); the retries are used up (the model is not asked for a query that would never be used); the writer returns `None` (no tier could write one); or a check fails during a retry. Then the earlier `absent` stays, because it says more than `unchecked`. A check that fails on the FIRST search gives `unchecked` and never loops.
- A search that finds nothing is `absent` without a model call, and it can loop.
- Inside one claim the passes go one after another, because the next query depends on the last result. Between claims they run together, so the time is about that of the slowest claim.
- The report sees only the final verdict of a claim. The log shows the queries (`a claim was searched N times, ...`).
- The writer is `new_query(claim, tried, note) -> str | None`, handed in from outside (D7), as `build_graph(new_query=)`. Its instruction `REQUERY` (version 1) asks for a few key words in the names the other file could use, and never a repeat. `REQUERY_MAX_TOKENS` is 2,000 and `MAX_QUERY_CHARS` is 200. `requery_problem` refuses a blank answer, many lines, more than 200 characters and a repeat of an earlier query (case and spaces ignored), and a refused answer goes to the next tier. It uses `claims_client` (Flash-Lite first).
- Files: `prompts/requery.py` (new), `api/requery.py` (new), `agent/check_one.py`, `agent/graph.py`, `prompts/__init__.py` and `api/asking.py`.

**The math.** With `R` retries and `N` claims, one claim has at most `R + 1` searches, `R + 1` checks and `R` query writings. So the model calls are at most `N (2R + 1)`: for `N = 15` and `R = 2` that is 75, against 15 before the loop. The expected extra calls are about `N p (2 + 2q)`, where `p` is the share of claims that are absent on the first search and `q` the share that are still absent after one retry. Both are unknown until M24. As an example only, `N = 15`, `p = 0.3` and `q = 0.5` give 13.5.

**Checked in the scratch copy.** 38 new tests. Unit and api tests: 1703 passed and 7 skipped (without `.env`). The claims database file: 11 passed. 24 of 24 deliberate breaks were caught. One test was fake first: the wiring test passed with the stand-in client string, because the claims client and the plain client are the same string there, so it needs a real `LLMClient()`. A live look (exit AS58212 dataforest, Google 200, Flash-Lite, 4 claims of the sample paper, 8 requests) gave queries such as `clip_grad_norm max_norm 1.0` and `vocab_size 20000 max_tokens`, and most of their words are in `B_train.py`. That is one try on one tier, NOT a measurement. NOT measured: whether the retry finds the right part with the real search, and how often it changes a verdict (M24).

#### 24.3 Evaluation loops: what the talk of 2026-10-24 settled

The user was told by GPT that an evaluation loop is essential, that every agent in the world has one, that LabPilot lacks it, and that some tasks could be sub-agents and not simple functions.

- **What it is.** Make something, let an evaluator judge it, send the judgment back, make it again, and stop when it is good enough or the tries are used up. A coding agent that runs the tests and fixes the code is the usual example.
- **Three kinds of evaluator.** (1) A code rule, which cannot be fooled: the quote is in the part, the citation resolves, the JSON parses, the tests pass. (2) A model that sees evidence: the claim and the retrieved parts. (3) A model that re-reads its own answer with no new evidence, which is the weakest. The last point is from published work that I know from memory and did not re-read.
- **What one LabPilot run has:** `check_plan` (code) and the next tier for a wrong plan, the quote guard, the check of each claim, the retry loop, and `resolve()` for the citations. It has NOTHING that evaluates the final report as a whole. The retry loop is itself an evaluation loop: the check is the evaluator, the note is the feedback, and the query writer is the maker.
- **Three meanings of "evaluation" in papers:** the score of a finished agent on a benchmark (offline), an evaluator inside the loop (called evaluator-optimizer, generator-critic, self-refine or reflexion; names from memory), and LLM-as-judge, which is a model used as the scorer in either.
- **What is right in GPT's advice:** we have never scored one whole run of the agent on the search path (C3), and M6 is in the last slice, so slices 8 to 12 would change the behavior with no starting number.
- **What is too strong:** "every agent" has one. A critic over the final report would cost another report-sized call, and 98% of the time is generation. Each strong Gemini tier gives 20 calls a day. A critic with no outside evidence is the weak kind.
- **A correction of an old answer.** If Step 0 was answered as "repeat the call and it finds more", that was too strong. Three passes of one model at temperature 0.8 gave 11, 11 and 13 findings, no gain (2026-08-17). What helps is a different question in each pass, and checks against the text (the seven missed findings belonged to the question, not to the call). The Dude paper's gain (recall 58.7% to 80.4%, precision 91.5% to 93.7%, author-reported) comes from claim-by-claim verification with search.

#### 24.4 Decisions

| # | decision |
|---|---|
| **D74** | **A small end-to-end baseline is run at the END of slice 7, and again after every later slice, and not only in slice 13.** One run of the sample pair with the default question, the search path forced (the pair is almost small enough to be read whole), counting how many known findings of `EXPECTED.md` the report has, weighted by impact, in three states (judged, surfaced, absent), checked by reading and not by regex. It needs the impact column in `EXPECTED.md` first, which has been owed since Step 0. Estimated cost (not measured): 20 to 30 calls, mostly Flash-Lite, plus one report call. M6 stays the full version in slice 13. The reason: slices 8 to 12 will change the behavior, and without a baseline nobody can say whether a change helped |
| **D75** | **A precision pass for `find_bugs`, in slice 9.** Asking a model to find bugs makes it invent some (measured in Step 0: two pieces of correct code were flagged, and one wrong finding was ranked first with high confidence). Each suspect becomes a claim with an exact quote. The code checks that the quote is in the file (`has_quote`). Then a short second call sees only those lines and says: real bug, a deliberate choice, or unclear. The suspects run at the same time with `Send`, in the shape of `check_one`. The report shows the label and nothing is deleted, so a wrong judgment of the checker cannot remove a real bug. It lowers false alarms and does NOT find the bugs that `find_bugs` missed. The idea was written twice in this file as "a cheap precision pass" and was in no slice |
| **D76** | **Workers stay bounded functions.** A worker becomes a sub-agent (its own model loop that picks its steps and tools) only when a measurement shows that the fixed version misses what a loop with tools finds. The candidates are the check of a claim in a big B, `find_bugs` on a big B, and the summary of a big repository (slice 12). D8, the exact-match tool, would be the first extra tool. The check of a claim already has a small loop of its own (lesson 3). No critic over the final report for now |

**M26** (slice 9): does the precision pass reject the known false alarms and keep the real bugs? The ready test is `DEVICE = get_device.__func__()`, `EMB_DIR = ROOT_DIR.parent.parent` and the wrong finding `P1`, against the real problems of `EXPECTED.md`. Count both ways, the false alarms removed and the real bugs wrongly removed, and name the model that judged.

#### 24.5 What slice 7 still owes

Lesson 3 is DONE (typed, green, committed as `bd46262`). Still owed: M10 and M11 (claims on real prose and on code, with wording E and the cap), M21 (the quote rule on real claims), M24 (rerank for each claim, and what the retry fixes alone), the Jev pilot M15 (D73), the small baseline of D74, the closing review of slice 7 ("The closing review of slice 7"), and the docs update.

**UPDATE 2026-10-24 (night): everything in that list ran, and the results are in section 25.** What is still owed to close the slice: the user types the patches of 25.10 (R15 and R5, the stray `+`), and decides R1 to R24 (the complete list is in 25.11); the cause-finding step (R13) is designed next. **The user's plan for the next session (2026-10-24): make claims and retrieval much better (R1 to R4, R13), and ALSO try the stuffed approach, that is the current app on the full pair read whole, the control that 25.8 lists as not measured. This reverses the user's earlier "no stuffed run" of the same night.**

**UPDATE 2026-10-24 (late night): the user asked Claude to do every change of 25.11 alone, with no questions, and to reconsider Step 1 too. It is built and measured in section 26:** the search path scores 29-31 of 39 against 13-16 before (one repeat gave 23), the stuffed answer 30 of 39 in 36 s (R21: no claims and no scan there), the claim check 30 of 32 with 11-12 of 12 mismatches found and no false match, and citations resolve again. 20 commits on `feat/check-claims` (9761758 to 0642da0), local, not pushed, not on `main`. Owed: a big test pair (slice 12) to judge the scan, the rerank window and a cap on the parts list; the negative-claim gap of 26.3 (G20); Jev in the graph (slice 14).

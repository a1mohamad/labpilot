# Section 29.10 to 29.20: slice 9, follow-ups and review

[Docs home](../README.md)

#### 29.10 Follow-up questions: the whole last answer and the saved findings (D104, decided 2026-11-08, moved 2026-11-09 to the end of slice 9)

*Talked through with the user while lesson 4 was being read. Nothing is built.*

**What the design does today.** The chat saves only the questions (`history`; the follow-up rewrite reads the last `RECENT_QUESTIONS = 4`, each cut to 300 characters) and the END of the last answer (`last_answer`, `LAST_ANSWER_CHARS = 2,000`, replaced on every message). Older answers are never sent. `remember` clears `differences` and `bugs` after each message, because both are lists with the add rule. So a follow-up such as "fix bug 3" or "explain the second difference" sees at most the last 2,000 characters of a report of about 10,000, and most findings are lost.

**Why "stop clearing them" is not the fix.** The planner runs again on every message, and when it plans `find_differences` and `find_bugs` again they really run again. The models do not repeat their words, so with the add rule the same bug comes back as a second line, and the list grows on every message.

**The user's point:** the findings depend on the two files and the instruction versions, not on the question (the claims instruction does not read the question, R3). So with the same files they should be computed once.

**What the big chat products and agents publish (not their internal code):** they send the recent turns whole, previous answers included, and cut or summarize the oldest turns when the context gets long (Claude Code calls it compaction; OpenAI's API keeps the history with `previous_response_id`). Agents drop bulky old tool results (Anthropic's "context editing") and keep key facts in a store that they read back (Anthropic's "memory" tool). D104 is the same shape.

| # | decision |
|---|---|
| **D104** | **Follow-up questions get the whole last answer and the saved findings, built at the END of slice 9.** **BUILT 2026-11-10, see 29.17 (path (b) as written is not built).** (1) **Compute the analysis ONCE for each pair of files** and save the final lists of `find_differences` and `find_bugs` (after the judge, the skeptic and the merges), keyed by the two artifact ids and the instruction versions (`DIFFERENCES_VERSION`, `BUGS_VERSION`, `CLAIMS_VERSION`). Store them in the database next to the artifacts, not only in the chat, so a new chat with the same files reuses them. Compute again only when a file or a version changes. (2) **Keep the whole last answer**, not its last 2,000 characters (a report is about 10,000 characters). Older answers stay out, or are summarized. (3) **On a follow-up, choose one of three paths:** (a) the question is about the saved findings: answer from the saved list and the last answer, plus a short search of B for the finding it names, so the model sees the real code; no audit and no hunt; (b) the question asks something new ("does B also shuffle the test set?"): treat it as a claim and run one audit on it, or one small bug hunt on the parts it names, and add the new findings to the saved list through the merge step that removes repeats; (c) the question is not about the files: just answer. (4) **Show the user which path ran** ("answered from the earlier analysis" or "checked again"). (5) Never send the bulky working material again (the parts, the votes, the audit answers). |

**Costs and limits, plainly.** The choice of path can be wrong: it needs a cheap model call (or Jev later, close to D73 job 8) and a test on real follow-up questions. It is more code and a new table. A saved list cannot answer a question the first run did not look at; path (b) exists for that. **Nothing here is measured.** In slice 6, adding the last answer to follow-up prompts showed no visible gain on two tiers (D58); that was one pair and a small test, so it does not prove D104 useless. It must be measured on real follow-ups when it is built.

**Moved to the end of slice 9 (the user's call, 2026-11-09).** It was first planned for slice 12. The user decided that its right place, and its measurements, are in slice 9, because slice 9 makes the findings it saves and uses. It is built after lesson 4 and M31, before the closing review of slice 9. Slice 12 then EXTENDS it for big repositories: many more findings, the storage shared with the stored summaries (D47, D110) and the verdict of the gate kept for each pair (28.4), and the ranking of findings (M32).

**Also, as part of D104 (2026-11-09):** the claims depend only on A and `CLAIMS_VERSION` (R3), but today `remember` empties them after each message and they are written again on the next one. Save them once for each artifact, in the same way as the findings.

| # | measurement |
|---|---|
| **M33** | **At the end of slice 9, after D104 is built.** **MEASURED 2026-11-10 (29.20): 7 calls instead of 27 a follow-up.** About 10 real follow-up questions of each kind (about a saved finding, "fix bug 3" or "explain the second difference"; something new about the files; not about the files), on the slice 9 cases, on two tiers. Count: how often the right path is chosen, whether the answer uses the right saved finding and cites its code, the seconds and calls against running the whole analysis again, and faults read by hand. Compare with today's design (the end of the last answer only) |

#### 29.11 A question about ONE file when TWO are sent (D105, decided 2026-11-08, for the end of slice 10)

*Found while reading lesson 4 with the user. Nothing is built.*

**What works today.** A question with only A or only B works: the door takes one id (D62), `ask()` puts it in its own slot, `respond` answers with `ONE_FILE`, and with one file `find_bugs` reads that file, whichever side it is. No special "ask" node is needed.

**The gap.** When BOTH files are sent and the question is about only one of them (for example "what does section 3 of A say?" or "explain `fit` in B"), the planner can search only that side, but `respond` always uses `TWO_FILES`, an instruction written for a comparison. It writes ANSWER first, so a short question still gets an answer, but it also adds the comparison sections, and the planner may still plan `find_differences` and `find_bugs`, which cost minutes. Never measured.

| # | decision |
|---|---|
| **D105** | **Fix the "two files, question about one" gap at the END of slice 10.** The planner (which already reads the question) returns which file the question is about: `A`, `B` or `both`. With `A` or `B`, the plan has no `find_differences`, its queries search only that side, and `respond` answers with `ONE_FILE` on that file's parts (the other file may still be named, but no comparison sections are written). With `both`, nothing changes. A question that is unclear counts as `both`, because a wrong one-file answer hides a difference and a wrong `both` only costs a longer answer. Measure it first on about 10 real questions of each kind (about A, about B, a comparison), on two tiers, and count how often the planner chooses right (with M18). The field is checked in code like the rest of the plan (D50), and `PLANNER_VERSION` goes up |

**Why the end of slice 10.** It changes the planner and `respond`, which slice 10 touches anyway (the `ask` field of D109 and the choices of D107), so the planner is changed once and measured once. (Until 2026-11-12 this sentence named `extract_outcomes` and the comparability check; both were withdrawn, D108, section 31.)

#### 29.12 The prompt id in each finding line (M31, planned 2026-11-09, for the end of slice 9)

*Raised by the user while lesson 4 was read. Nothing is built.*

**Today.** `respond` gets the parts (the RAG parts, plus the `evidence` part of each finding, added at the END and never twice) and one short line for each finding. A line names its place by the part's header and an exact quote, for example `B (train.py · lines 40-60): "CLIP_NORM = 1.5"`. The model must match that header and quote to a part that may sit far away in a long prompt. It was never measured whether this works.

**The idea.** Write the part's prompt id in the line too, for example `see B-12`, so the model has a direct pointer and cites the id our citation check (`resolve()`) reads. The ids are given out when the prompt is built (`assign_ids`, after the parts are chosen), so the finding lines must be written after that step (`api/prompting.py`, `api/finding_lines.py`). A part cut for room has no id, and its line keeps today's form.

| # | measurement |
|---|---|
| **M31** | **At the end of slice 9, after lesson 4 and before the closing review.** **MEASURED 2026-11-10 (29.20): no gain, the code was taken out.** The same pairs and the same question, with and without the id in the finding lines, at least 2 runs each, on the search path and on the stuffed path. Count: citations that resolve, findings the answer uses or states, and faults read by hand. Keep the change only if the numbers go up; a gap of one or two is noise. One small change, typed by the user like the other lessons |

The current design has shown no failure here, so this is a "maybe better", not a fix.

#### 29.13 Ranking the findings with a cheap model call (M32, planned 2026-11-09, for slice 12)

*The user's idea, while lesson 4 was read. Nothing is built.*

**Today.** Before `respond`, `prior_text` (`api/finding_lines.py`) sorts the difference and bug lines by a fixed rule in code, with no model call: `B differs` and `B leaves out` first, then a real high-severity bug, then a real low-severity bug and `A silent`, then the rest (unclear, unchecked). The lines are taken from the top until 25% of the prompt budget (about 7,500 tokens, about 70 lines) is used, and the lines left out are counted. Each kept line still goes into its own block (differences, then bugs). The rule does not know which finding matters most for THIS question.

**The idea.** Rank all the finding lines (differences and bugs together) against the user's question with ONE cheap, fast call, Gemini 3.5 or 3.1 Flash-Lite. Reuse the rerank chain that already exists (`rank(query, documents)`, Flash-Lite first and tuned, about 1.3 s, then Jev): the lines are the documents, so no new prompt or schema is needed. When the call fails, today's rule order is the fallback.

**Why slice 12 and not now.** On the pairs of slice 9 the cut almost never happens (`find_differences` about 6 lines a case, `find_bugs` 10 to 47 a file, against about 70 that fit), so the order changes almost nothing that is sent. A big repository gives many more findings, so the cut is real there, and a narrow question ("why is F1 lower?") is where an order by meaning should help. The cost: one more call in series before `respond` (about 1 to 5 s), one more failure path, and an order that changes between runs.

| # | measurement |
|---|---|
| **M32** | **In slice 12, on the big test pair.** Today's rule order against the Flash-Lite rank, the same questions (narrow ones and the default one), at least 2 runs each. Count: how many lines are left out, which known findings are kept, which findings the answer uses or states, faults read by hand, and the extra seconds. Before that, at the end of slice 9 (with M31), read the count of left-out lines on the slice 9 cases: if it is zero, the rank changes nothing there |

#### 29.14 Keeping the most important parts when B is cut (M34, planned 2026-11-09, for slice 12)

*Asked by the user while lesson 4 was read: "what makes sure that the parts we keep are the most important, and that we did not lose an important part after the cut?"*

**The honest answer today: nothing makes sure.** On the search path `respond` gets a list of parts and `select` (`retrieval/selector.py`) takes them from the top until the budget is full, half for each side, the leftover of one side to the other. What protects the important parts is only the ORDER of that list:
1. the parts behind the findings first (`_first` in `api/prompting.py`, R20), because a finder read B and named that code;
2. then the reranker's best 10 of each side (`rank_pile`, a window of 20, `RERANK_WINDOW`);
3. then the rest of the pile in search order (the best hit of each query, then the second best, and so on, D53).
Below the 10 reranked parts the order comes from search scores, not from importance, so an important part at place 70 can be cut. No step checks it, and no test, log line or measurement shows it. The outline tells the model which parts it did not read, so it can say "not in the parts I read"; that lowers the harm, it does not stop the loss. Perfect is not possible (a part is known to be important only after a model reads it), but the best possible must be done for big repositories, where most of B is cut. On the small slice 9 cases almost nothing is cut, so this is a slice 12 job.

**What was already in the docs, only in pieces:** re-run `run_r23.py` on a big B (26.4, 26.9, 26.11); the rerank window and a cap on the parts list on a big B (26.9, 26.10); low coverage should tell the user and ask for a folder or a file (13.7, hole 2); RRF by how many queries found a part (D53). This section joins them, adds the rest, and is the one place for them.

**Step 1, measure the loss first (M34).** On the big pair of slice 12, with its answer key, for each known finding: is its code (a) in the pile and sent, (b) in the pile and CUT, or (c) never found by any search. (b) is a cut problem, (c) a search problem (queries, summaries, D46), and they need different fixes. Also log, for every answer on the search path: parts in the pile and parts sent for each side, and the place of each evidence part. `harness/coverage.py` is the start of this instrument.

**Step 2, the candidates, each measured against today on the same questions:**

| # | candidate | note |
|---|---|---|
| K1 | keep the evidence parts first (today) | the base of every arm |
| K2 | rerank MORE of the rest: windows 20, 50, 100 | slice 8: quality turns over between 50 and 100 parts in ONE call |
| K3 | rerank the rest in several calls of about 50 parts, then join them round-robin | listwise scores of different calls cannot be compared, so join by place, not by score |
| K4 | a part found by several queries goes up (RRF count, D53) | free, no model call |
| K5 | the files closest to the question and the queries go up (`file_scores`) | free |
| K6 | cap the list given to the prompt at a few times what fits | at a 12K budget the long outline of a big pile cost room (26.4) |
| K7 | on low coverage, say how much was read and ask for a folder or a file (13.7) | a confident answer over 3% of a repository is the wrong answer |
| K8 | better queries for a big B: the good summary of D46 and the map | this is the fix for case (c) |

Count for every arm: the known findings whose code is sent, the findings the answer uses, the citations that resolve, the seconds and the calls. Choose by the loss of case (b), not by one total score. Name the pair and the tier beside every number. Related: M32 (the order of the finding lines, 29.13) is the same question for the findings.

#### 29.15 Only B is hunted for bugs; a reference alone is explained (D106, 2026-11-10)

*The user's point: slot A is the reference the person chose to trust, so hunting it for bugs goes against that choice. If A is correct, the hunt invents "bugs" and makes the person doubt a good reference; if A is wrong, that is not what they asked, because slot B is the place for the work being checked. Built by Claude at the user's request (an exception to "the user types the product code").*

| # | decision |
|---|---|
| **D106** | **find_bugs reads only B.** With A and B: B, as before. With B alone: B. **With A alone: no hunt.** `bugs_task` returns nothing without B, and `allowed_steps` drops `find_bugs` (`NEEDS_B`) when B has no file, so a plan that hunts A alone is refused and goes to the next tier. `PLANNER_VERSION` 5 (`find_bugs` means "read B alone"). **A alone is answered with a new instruction, `REFERENCE`** (not `ONE_FILE`, which checks the work it reads): ANSWER, WHAT IT IS (purpose, input and output, main steps), KEY VALUES (every setting and number a faithful copy must use, cited), HARD PARTS (two to five hard formulas, steps or pieces of code in plain words, with a tiny worked example), UNCLEAR OR MISSING (what a rebuild needs and the parts do not say, why it matters, the usual choice: gaps, not errors), TO GET RIGHT (5 to 15 rules a copy must follow, which can later be checked against B), and the last line, word for word: "This file is your reference, so I did not look for bugs in it. To have it checked, add it in slot B." It never calls anything in A a bug, a mistake or wrong. 2,123 bytes, under the 2,200 guard. `respond` passes `reference=True` only when A is the only file, and `fits_whole` charges the longer instruction then |

**Not measured.** The REFERENCE instruction was never run on a real model: whether the sections are useful, whether the last line is always written, and whether a model still slips in "bugs" are open. Measure it with M31 at the end of slice 9: a paper alone and a code file alone in slot A, two tiers, read by hand.

#### 29.16 Shared helpers, tests on today's behavior, and the old skip gate removed (2026-11-10)

*At the user's request ("don't repeat yourself", and "make the tests support only the new behavior"). Built by Claude at the user's request.*

- **One reader of a stored file.** `api/claims.py` and `api/summaries.py` read the parts with `read_parts` (`api/file_parts.py`) instead of reading the rows and joining header and text by hand. A dropped connection is now a `ClaimsError` for the claims (no claims, the answer goes on) and a `StorageUnavailable` (503) for a summary, never a raw database error. `read_parts` builds its texts once, from `FileParts.of`.
- **One part numbering.** `numbered_parts` (`prompts/_groups.py`) writes `[part 0]`, `[part 1]`, ... for the six prompts that use it (audit, bugs, checklists, claims, review, scan). A test fails if a prompt file numbers its parts by hand again, because the code reads the number back from the answer.
- **`respond` passes every keyword every time:** `differences`, `bugs`, `evidence` and `reference`, empty or `False` when there is nothing. The old rule "hand them over only when there are some" existed only so that old strict fake functions kept working; those fakes now take `**_`.
- **The database test fakes answer each tool by its name** (`tests/integration/test_ask.py`, `test_the_two_doors_together.py`). Before, every tool got the planner's plan, so the gate could not read its answer and always took its fail-open path (noted in 28.10). Now the gate gets a real `PARTIAL` verdict and a new test checks that it judged. Any other tool (the finders' claims, audit, hunts and checklists) gets "no tier answered", so those finders take their fail-open path on purpose, as in a real outage.
- **The old rerank skip gate is deleted** (`retrieval/gate.py` and its test: `should_rerank`, `margin`, `SKIP_MARGIN`). Nothing in the product called it since D57, and its name was confusing next to the correspondence gate. `scripts/retrieval/score_rerank.py` keeps its own `margin` for the measurement.
- **Kept on purpose:** the frozen `FULL`, `CORE` and `REPORT` templates, which the weekly smoke run compares against.

#### 29.17 D104 is BUILT: saved findings, the whole last answer, and what the reply says (2026-11-10)

*Designed and built by Claude at the user's request ("design and build it now, do it yourself"), an exception to "the user types the product code".*

**What it does.**
- **Saved results** (`labpilot/store/saved.py`, `labpilot/api/saved.py`, table `saved_results` in `store/schema.sql` with row level security). The claims of A, the differences of A and B and the bugs of B are saved once, keyed by the step, the files and the instruction versions: `claims:<A>:v<CLAIMS_VERSION>`, `differences:<A>:<B>:a<AUDIT>s<SCAN>r<REVIEW>:<hash of the facts>`, `bugs:<B>:v<BUGS_VERSION>`. The next message, or a new chat with the same files, reads them and runs no audit and no bug hunt. A new instruction version, or other facts, gives a new key, so an old result never answers. The rows go with their artifacts (`on delete cascade`), so a file stored again is analysed again. A database error never stops the answer: a result that cannot be read is made again, one that cannot be saved is still used. A failed step is not saved.
- **A saved step is always planned** (`with_saved_steps`): a follow-up planned with no step (for example "explain bug 2") still gets the saved bugs and differences, because they cost nothing. (S4 of 29.21: they are also added to a question that does not need them; slice 11.)
- **The whole last answer.** The chat keeps the whole answer up to `KEPT_ANSWER_CHARS` = 20,000 characters (was the last 2,000). The answer prompt and, since the measurement of 29.19, the follow-up rewrite read all of it. The check "does the pair fit whole?" now counts the real last answer (`fits(sides, question, last_answer)`), so a follow-up whose last answer is long may be searched instead of read whole; `PROMPT_EXTRAS_TOKENS` covers only the two summaries now.
- **The reply says which path ran:** `reused` lists the steps read from the earlier analysis, and the page shows "from the earlier analysis: claims, differences, bugs".

**What is NOT built from the D104 plan.** Path (b) as written ("a new question is audited as one more claim, or a small hunt runs on the parts it names") is not built: a new question is answered from the saved findings, the planner's searches and the whole last answer. In M33 the two new questions were answered correctly that way. The path choice is made by the planner and the saved results, not by a separate model call. **The full choice of the three paths is moved to the end of slice 10 (D107, 29.22).**

#### 29.18 The reference alone, checked on four real files (D106, 2026-11-10)

One run each, tier 1 (GLM-5.3 Flash on LiteRouter), the page's default one-file question "Summarize this and find likely bugs.", every file read whole:

| file | parts | seconds | 6 sections | last line | calls anything in it a bug |
|---|---|---|---|---|---|
| Word paper (`ddos_ensemble.docx`) | 24 | 434 | yes | yes | no |
| PDF (ResNet) | 52 | 440 | yes | yes | no |
| notebook (`univariate_regression.ipynb`) | 11 | 151 | yes | yes | no |
| repository (`pallets/markupsafe`) | 130 | 307 | yes | yes | no |

Every answer said politely that a reference is not checked, and put real flaws of the paper (missing formulas, a swapped `train_test_split` order, numbers that disagree between a table and the text) under UNCLEAR OR MISSING. 89 to 138 citations each. **Limits:** one run, one model, one question; the answers are long (11,000 to 19,000 characters) and slow (29.21); the search path of a big reference alone was not tried. A first try with a local folder was refused by the walk (`SourceTooLarge`, more than 20 MB of data files), which is the right behavior.

#### 29.19 The follow-up rewrite reads the whole last answer (measured, 2026-11-10)

In M33 the follow-up "Explain the first difference you listed in more detail" was answered about the WRONG difference. The rewrite read only the last 2,000 characters of the answer and could not see which difference came first. A direct test of the rewrite alone, two runs each, on that answer: with the end only it copied the question 2 of 2 times; with the whole answer it named the right difference ("the TOTP counter is rounded instead of floored") 2 of 2 times. So `build_follow_up_prompt` now uses `KEPT_ANSWER_CHARS`. Small (4 calls), but it is a measurement and the cause is plain.

#### 29.20 M31 and M33, and the closing review of slice 9 (2026-11-10)

**M31: the prompt id in each finding line** (`[B differs, see B-12]`, tried behind a switch in `api/prompting.py`). The findings were made ONCE per case by the real pipeline and frozen; only the answer prompt changed between the arms.

The question was the default comparison question; one answer for each arm (the first run had two for quora without ids); the real chain (it answered with GLM-5.3 Flash, GLM-5.3 Flash cheap or GLM-5.3 cheap on LiteRouter, so the two arms were not always answered by the same tier). Quora was read whole (bugs only, R21); OTP was forced onto the search path (differences and bugs); Adam was searched (differences only, the bug hunt gave none). Scored by code: citations that resolve, and how many of the parts behind the findings the answer cites.

| case | ids | citations that resolve | finding parts cited |
|---|---|---|---|
| quora | no | 0/0 (the 125 citations had the wrong shape, quote first and then `[A-1]`) | 0/6 |
| quora | no | 107/107 | 6/6 |
| quora | yes | 76/76 | 6/6 |
| OTP, search | no | 90/90 | 3/4 |
| OTP, search | yes | 87/88 | 4/4 |
| Adam | no | 59/62 | 6/7 |
| Adam | yes | 64/65 | 6/7 |

With ids 16 of 17 finding parts were cited, without them 15 of 17 (the broken answer left out). One part apart, with different tiers answering the arms, is noise, and no answer ever repeated the "see B-12" text. **Decision: the measurement does not support the change, so the code was taken out again** (`finding_lines.py` and `prompting.py` are back to their committed versions). It may be measured again in slice 13 (M18), on many pairs and more runs. One answer of quora failed: two LiteRouter tiers hung and spent the whole budget (below).

**A finding on the side: one tier wrote its citations in the wrong shape** (the quote, then a bare `[A-1]`), so none of them could be resolved. The instruction says the shape exactly; a check that refuses an answer with no resolvable citation (the next tier writes again) would catch it. Not built: slice 11 or 13.

**M33: follow-ups with D104 against the old design** (OTP pair, one real chat, the real chain).

One run of each, OTP pair (RFC 4226 + RFC 6238 against `pquerna/otp`, search path), the real chain, every model call counted (every LLMClient, the finders' own included). M31 ran on the same providers at the same time, so all times are slower than one run alone would be.

| message | new design (D104): seconds, calls | old design: seconds, calls | answer read by hand |
|---|---|---|---|
| first: "Compare these and explain why the results diverge." | 1,318, 37 | 1,136, 37 | both full reports |
| saved: "Explain the first difference you listed in more detail." | 357, 7 (all three steps reused) | 497, 27 | new: WRONG difference (the rewrite saw only the end of the answer; fixed, 29.19); old: right |
| new: "Does B make sure that a one-time code cannot be used twice?" | 336, 7 | 388, 27 | both right ("No, nothing records a used code"), cited |
| chat: "What is HMAC, in two sentences?" | 226, 7 | 330, 6 | both right, but both written in the two-file format (COMPARABLE, DIFFERENCES: S2 of 29.21) |
| saved: "Write the fix for the most serious bug you listed." | 356, 7 | not run | right: the 0x7 mask becomes 0xf, cited |
| new: "What does B do with a secret shorter than 16 bytes?" | 451, 7 | not run | right: no minimum length, and the 10-byte HOTP default |
| chat: "Thank you, that is all for now." | 88, 7 | not run | fine, but in the two-file format again |

**Result.** A follow-up costs 7 model calls with D104 against 27 without it (the old design runs the claims, the audit, the scan, the judges and the bug hunt again every time). The time fell less, by about 10% to 30%, because the final answer is most of the time of a follow-up (29.21). The path the reply shows (`reused`) was right on every follow-up. **Limits:** one pair, one run per cell, the old design only on three follow-ups, two measurements running at once; the wrong "first difference" of the new design was fixed and re-checked on the rewrite step alone (29.19), not with a new full chat.

**A provider fault seen in M31.** One report call spent its whole 900-second budget on two LiteRouter tiers that hung and then closed the connection, so no other tier was tried, and the answer failed. Same weakness as S3 of 29.21, in the final answer.

**The closing review.**
- Joins that no test crossed got tests: D104 through the real store and two real `ask()` calls (`tests/integration/test_saved_results.py`: round trip, cascade for both artifacts, a second message reads the bug hunt and says so, a saved chat carries the whole first answer into the rewrite and the answer); the last answer reaching the fit check through the graph (`test_graph_fan_out.py`); the save-and-reuse rules with a fake store (`tests/api/test_saved.py`, 12 tests).
- **16 deliberate breaks, all caught** (each on a kept copy of the file, restored from that copy): A alone hunted; `find_bugs` allowed without B; the reference flag never set; the REFERENCE instruction never chosen; the fit check ignoring the last answer; the graph not passing it; the chat keeping only the end; the answer prompt reading only the end; the rewrite reading only the end; a saved result never read; a saved step never planned; the differences key ignoring the facts; `reused` not reported; saved rows not going with their artifacts (this one SURVIVED first, because the test stored B again but the break was on A; the test now stores both); the parts numbered from 1; a claims read error escaping raw.
- Dead code removed: `INPUT_BUDGET` (`select()` now requires its budget).
- Tests run: every affected unit, api and database test (unit and api: 1958 passed, 5 skipped; the database files of D104, the fakes and the readers passed), `ruff check .` and `ruff format --check .` clean. The full suite was NOT run, at the user's request.

**Slice 9 is DONE** (2026-11-10). Open from it: S1 to S4 (29.21), the D104 path (b) as planned (moved to the end of slice 10, D107), the speed of tier 1, and the measurements of slice 13 (27.1, 27.2, M18).

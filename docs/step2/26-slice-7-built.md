# Section 26: slice 7, every change built and measured

[Docs home](../README.md)

### 26. SLICE 7 — EVERY CHANGE OF 25.11 BUILT AND MEASURED, AND STEP 1 RE-CHECKED — 2026-10-24 (late night)

*The user said: "do every one of them yourself, one by one, do all measurements, do not answer me, only a final report; if the RAG system of Step 1 needs changes too, reconsider it". So, for this one job, Claude wrote the product code (an exception to "the user types all product code", given by the user in words), made the decisions, and committed locally on `feat/check-claims` (not pushed, not on `main`). Exit AS58212 dataforest; Google answered 200 before each batch (once 429: key 1's Flash-Lite day was spent, and the chain moved on to keys 2 and 3). Every model run used the throwaway schema `labpilot_m7_4a046f` (18 parts of A, 82 of B, `codestral-embed`). Raw results: `artifacts/slice7-review/results/` (git-ignored). Harness: `artifacts/slice7-review/harness/`; new tonight: `coverage.py`, `coverage_saved.py`, `run_r23.py`, `writer_ssl.py`, and a "wired" arm in `run_m24_arms.py`.*

#### 26.1 How to read the numbers

- **One pair, one paper.** Everything is `quora_siamese`. A fixture may reject an idea; it never confirms one.
- **Score (/39)** = the weighted findings a report JUDGES, read by hand against the impact column of `EXPECTED.md` (R22): a story finding 3, a secondary one 2, a "moves nothing" one 0. **The one rule used for every cell:** "judged" = the report names it as a cause or a problem and says what it does; "surfaced" = only mentioned, worth 0; a wrong statement about it counts as absent and is listed as a fault. Earlier readings of the same night (E4w 33, the medium-effort run 31) used a looser rule and were re-read with this one.
- **One run for each cell.** The repeat of F4w (F4wb) moved by 6 points (29 against 23), so **a gap under about 6 is noise.**
- **Coverage (/39)** = how much of the code behind the 19 known findings was in the parts the writer received (`harness/coverage.py`: the B lines of `EXPECTED.md`, the same weights). It says what the report CAN use, not what it says. It costs no quota.

#### 26.2 The grid, all cells

| cell | code | path, budget | claims | scan | B parts sent | coverage | score /39 | seconds | citations resolved | faults |
|---|---|---|---|---|---|---|---|---|---|---|
| D74 | old (before 9761758) | search, 20K | old | - | 10 | n/a | 13 | 185 | 47/48 | #1 called a match; label smoothing "the same"; A "keeps embeddings frozen" |
| E0b | old | search, 20K | old | - | 10 | 13 | 16 | 237 | 78/79 | - |
| E1 | old, tier 1 effort high | stuffed, 30K | off | - | 82 | 39 | 33 **(cut at the token cap)** | 547 | 123/129 | - |
| medium | 22285a1 | stuffed, 30K | off | - | 82 | 39 | 26 | 78 | n/a | - |
| E2 | old, served by tier 3 | stuffed, 30K | off | - | 82 | 39 | 23 | 548 | 44/49 | **2 invented "certain crash" typos** (not in the file); class weight "essentially the same" |
| E3 | f53f684..ec16c24 | search, 12K | new | off | 3 | 12 | 16 | 146 | 18/35 * | B's threshold "0.5" |
| E4w | ec16c24 | search, 30K | new | on | 50 | 39 | 31 | 166 | 7/55 * | - |
| E5 | ec16c24 | stuffed, 30K | new | on | 54 (cut by findings) | 34 | 29 | 212 | 9/37 * | "embeddings never unfrozen" (the unfreeze lines were cut out) |
| F4w | 6782bb9 | search, 30K | new | on | 60 | 39 | 29 | 195 | 8/19 * | - |
| F3 | 200851c | search, 12K | new | off | 6 | 20 | 21 | 222 | 8/34 * | - |
| F5 | 200851c | stuffed, 30K | new | on | 62 (cut by findings) | 39 | 28 | 181 | 7/28 * | attention dropout "regularizes" (its rate is 0) |
| F4 | 200851c | search, 12K | new | on | 6 | 16 | 21 | 401 | 32/35 | a fixed 0.5 threshold called the cause; the unfreeze epoch "equivalent" |
| **E2n** | 048c65d | stuffed, 30K | **off** | **off** | 82 | 39 | **30** | **36** | 43/49 | - |
| F5b | 048c65d | stuffed, 30K, parts first | new | on | 82 | 39 | 26 | 244 | 39/40 | - |
| F4wb | 048c65d | search, 30K (repeat of F4w) | new | on | 56 | 39 | 23 | 254 | 39/49 | a confused "head dimension" problem |
| **F3w** | eee0a70 | search, 30K | new | **off** | 73 | 39 | **30** | 222 | 25/26 | - (and the first run to judge #18) |

\* broken by the citation-id defect fixed in cb34dbc (26.6); the findings scores of those runs stand, because the report text does not depend on it. Every run after the fix resolves 80% to 98%.

**What the grid says:**

1. **The search path at the full budget went from 13-16 to 29-31** (D74/E0b against E4w/F4w/F3w); one repeat gave 23. Most of the gain is NOT the claims: it is R23 (the writer gets the whole budget of parts, not 10), A read whole, and the code behind the findings first (R20). 26.4 measures that alone.
2. **At a 12K writer budget (a stand-in for a big B) the writer still sees only 3 to 6 parts of B**, and scores 16 to 21. That is where a big repository will hurt; slice 12 owns it.
3. **The stuffed path: the plain answer is as good and 5 to 7 times faster.** E2n (no claims, no scan) 30 in 36 s; with claims and scan 26 to 29 in 181 to 244 s. **So R21 is built (eee0a70): when everything was read, the graph answers at once.**
4. **The code-side scan never raised the score on this pair**: at 30K, without it 30 (F3w), with it 31, 29, 23; at 12K 21 both ways, but the scan took 180 s more and its lines pushed code out of the prompt (coverage 20 against 16). **It is kept, not proven**: the case it exists for, a B the writer cannot see whole, was never measured. Slice 12 decides on a big pair.
5. **Only the old code invented bugs** (E2 on tier 3: two typos that are not in the file, called certain crashes). No new-code run invented one; the faults left are misreadings.
6. **Tier 1 at effort "high" ran away** (E1: 547 s, cut); "medium" writes a complete stuffed report in 36 to 78 s (22285a1).

#### 26.3 The claim checks on the new wiring (R6, R8, R17, go-to-definition) — `run_m24_arms.py`, `results/m24_arms.jsonl`

The SHIPPED check node over the 32 key claims, Flash-Lite first. "Wired" = the checker and the query writer exactly as `api/asking.py` builds them (whole-file facts, go to definition, the outline of B).

| arm | code | runs | right /32 | mismatch found /12 | match confirmed /20 | false mismatch | wrong ids |
|---|---|---|---|---|---|---|---|
| plain + retry (section 25, lesson 3) | bd46262 | 4 | 27.2 (26-28) | 7.8 | 19.5 | - | - |
| plain + retry, new prompt (R6, R8 sentence; no facts, no outline) | eee0a70 | 1 | 28 | 8 | 20 | 0 | G22 G25 G29 G30 |
| **wired + retry (CHECK v2)** | eee0a70 | 2 | **29, 28** | 9, 9 | 20, 19 | 0, 1 | G28 G29 G30 / G17 G26 G29 G30 |
| wired + retry, CHECK v3 | 3f1a385 | 2 | 30, 30 | 10, 10 | 20, 20 | 0, 0 | G29 G30 (G30 a false MATCH again) / the same |
| **wired + retry, CHECK v3 + the fixed facts** | 6c43d82 | 2 | **30, 30** | **11, 12** | 19, 18 | 0, 1 | G20 (unchecked) G29 / G19 G20 (unchecked) |
| **wired + retry, CHECK v4 (one sentence for a claim that something is NOT done)** | uncommitted, 2026-10-28 | 2 | **31, 31** | **11, 11** | **20, 20** | 0, 0 | G29 only (absent) / G29 only |

- **G30, the class weight (#6), was a false MATCH in every arm of section 25** (the most dangerous error: B differs and the checker says it matches). With the facts the checker now SEES "pos_class_weight is never called" and answers "absent": no longer a false match, but not the right "mismatch" either. **CHECK v3 (3f1a385)** adds one sentence: such a fact is a mismatch (kind: mistake). It raised the score (30 and 30) but G30 was a false MATCH again. A probe of that one claim (`harness/probe_g30.py`) showed why, and it was not the model: **the whole-file facts were wrong.** They read function names from part HEADERS only, and `QuoraDataset` is one part whose header names only the class, so `pos_class_weight` was never found; and they reported `forward` as never called, though PyTorch calls it through `model(x)`. Fixed in 6c43d82 (the `def` lines of each part are read; names a framework calls by itself are left out). After the fix the probe answers **mismatch – mistake 3 of 3**, and the two arms find **11 and 12 of 12 mismatches with no false match at all.**
- **CLOSED on 2026-10-28 (26.12, CHECK v4).** Before it: negative claims could not name a deciding part. "No layer normalization is applied inside the attention block" (G20) is answered "match" without a part number in both runs, our guard refuses it on all 6 tiers, and the claim ends "unchecked". That is safe (not a wrong verdict), but the deciding part exists (`LAYER_NORM_ATTENTION = False`). A sentence such as "for a claim that something is NOT done, give the part that shows it is off" would need two more runs; not done tonight.
- **The whole gain over lesson 3: 27.2 to 30 of 32, and mismatches found 7.8 to 11-12 of 12.** With v2 the facts and the outline added only about 0.5; with v3 and the fixed facts the gain is mostly in the mismatches, the verdicts that matter for the report.
- **Two harness bugs were found and fixed before these numbers were trusted:** the check harness built the OLD checker (no facts, no outline, a 3-argument query writer), and the first "wired" fix closed its connection at once because the `with` block was not kept (two runs, 26 and 26, are void).

#### 26.4 Step 1 re-checked: what the writer receives — `run_r23.py`, `results/r23.jsonl`

Real searches with the planner queries of F4w and F3, the real merge, ONE real rerank call (Flash-Lite) for each setting, the shipped `build_answer_prompt`, no report. The number is coverage (/39).

| setting | 30K budget | 12K budget |
|---|---|---|
| top 10 per side, as before R23 | 9-10 without findings, 23-34 with them | 9-10 / 16-23 |
| **fill the budget (R23, shipped)** | **34-39 without, 39 with** | 12-17 / 14-22 |
| fill, rerank window 50 instead of 20 | the same | the same or +2 |
| fill, NO rerank (fusion order) | the same | the same or +2 |
| A searched instead of read whole | the same | the same |
| finding lines at 10% of the budget instead of 25% | the same, 12 more parts of B, 50 fewer lines | +2 on one plan, 0 on the other |
| stuffed, findings of F5, 25% (shipped then) | 65 of 82 parts of B, 96 lines | - |
| **stuffed, parts first (048c65d)** | **82 of 82 parts, 59 lines** | - |

- **R23 is the large Step 1 win** (+25 to +29 at 30K). Kept.
- **The rerank window, and rerank itself, change nothing on this pair**, because the 4 to 7 searches together already return 77 to 80 of the 82 parts. That says nothing about a big B. Unchanged; slice 12 must re-run `run_r23.py` on a big pair.
- **At 12K the whole pile costs outline room** (the outline lists every retrieved part), so "top 10" plus findings sometimes covers more (+3). Small and one pair: not changed. Slice 12 should cap the list given to the prompt at a few times what fits.
- **Built from it: parts first on the stuffed path (048c65d).**
- **The writer and SSL (17.23), measured:** `writer_ssl.py` stored the whole `labpilot/` package (826 chunks with vectors, 6.1 MB) into Supabase twice; **826 rows read back both times, 105 and 111 s, no SSL error.** The `executemany` risk did not happen in two real uploads. Not changed; watch it when psycopg or libpq changes.

#### 26.5 The research (step 1b): every idea, its source and its result

| # | idea | source (strength) | arm | result | kept? |
|---|---|---|---|---|---|
| I1 | read the reference in small groups, one call each | 25.2, own measurement (strong for this pair); Dude's claimer (arXiv 2609.03416, a 2026 preprint; its PDF did not render, so only the title and abstract were read) | R24: G9, E9, G12 | wording E in 2 groups of 9 parts: 10.7 of 12 mismatch facts, #11 in 3 of 3 repeats; wording G 7.7 (9.3 in section 25: the noise of a repeat); groups of 12 parts 8.3. #1 (pooling) in no arm | **kept, wording E** (f53f684) |
| I2 | a code-side scan: read B in groups and list what B does | Dude's "dual detection" (preprint, abstract only); SciCoQA arXiv 2601.12910 (a 2026 paper, read: it defines paper-code discrepancies, finds "paper omissions" the hardest kind, and gives the model the whole paper and code in one prompt, with recall 46.7% on real cases for the best model) | S1 scan alone; S2 scan with all of A beside each group | S1: 80-89 items, 11-12 of 19 code facts, 59-70 items that match nothing. S2: 34 items, 12 of 19, 16-18 unmatched | **S2 kept** as `find_missing` (53e1be6); S1 lost (same reach, 2.5 times the noise). In the grid it never raised a score (26.2, point 4) |
| I3 | a whole-file skeleton for the searcher: file tree, then skeletons, then code | Agentless arXiv 2407.01489 (peer-reviewed, strong): the skeleton beat the whole file for choosing what to read (58.3% against 53.7%) | R17: the query writer gets the outline of B | inside the wired arm: about +0.5 of 32 over the same prompt without facts and outline (26.3); noise on this pair | kept (c5e25ed) |
| I4 | "go to definition": when the found code only USES a setting, add the part that SETS it | the code-navigation tools of agents (SWE-agent's `find_file`/`search_file`, Claude Code's grep and read); the projects' own docs, a pattern, not a measurement | `FileFacts.expand` (6782bb9) | E5 had judged three settings "absent" though B sets them; with expand the wired arm finds 9 of 12 mismatches (7.8 before) | kept |
| I5 | static whole-file facts: a function defined and never called | a deterministic fact about the text (strong by construction, once the reader is right: it was not, see 26.3) | R8, `unused_definitions`; ranked with the differences (71047e1); CHECK v3 (3f1a385); the reader fixed (6c43d82) | #6 judged in every new-code run at 30K but F4wb; G30 is a mismatch 3 of 3 in the probe and 2 of 2 in the arms (26.3) | kept |
| I6 | read a small reference WHOLE, search only the big side | SciCoQA reads both whole; our A is 4,300 tokens | `whole_side` (ec16c24) | at 30K the same coverage as searching A (26.4); the gain is that A's sections are never missing (D74 had 10 of 18) | kept, for A up to 10,000 tokens |
| I7 | sample several localisations and use each one separately | Agentless (strong): 4 samples gave 96 fixes against 88 greedy | not built | needs several report calls for one question; the time budget forbids it today | not tried |

#### 26.6 Defects found and fixed tonight (each with a test and a deliberate break, every break caught by its own test)

| commit | defect | how it was seen |
|---|---|---|
| 2a1c036 | the chat was saved on the request's idle connection, which Supabase closed during a long report | an answer lost at the very end of a run |
| 22285a1 | tier 1 at effort "high" ran away (547 s, cut) | E1 |
| 6782bb9 | the finding lines overflowed a 12K budget and the answer was refused | E4 |
| 200851c | a query embed with no answer (read timeout) was not waited for; FileFacts did not survive a dead connection | F4 and F3, lost to the network |
| cb34dbc | **citations did not resolve when there were findings**: the ids were numbered on a reordered list (7 to 9 of 19 to 55, against 123 of 129 before R20) | scoring F4w |
| 048c65d | the findings of a stuffed run cut B (65 of 82 parts); a dropped connection inside the scan stopped the answer | `run_r23.py`, F4 |
| 71047e1 | the never-called fact was the FIRST line cut for room (ranked with "A silent") | F5b |
| eee0a70 | (a change, R21) on the stuffed path the claims and the scan only cost time | E2n against F5, F5b |
| 3f1a385 | (a change, CHECK v3) a never-called fact was answered "absent", not "mismatch" | the wired check arm |
| 6c43d82 | **the never-called reader missed methods inside a class part, and reported `forward` (a PyTorch hook) as never called** | `probe_g30.py` |
| 0642da0 | twelve integration tests pinned rules changed tonight (R21, R18, R23, the short match line) and had never been run against them | the full suite |

#### 26.7 Where the R items of 25.11 stand

| item | state |
|---|---|
| R1-R5, R24 | built (f53f684, 9761758); wording E, groups of about 2,000 tokens, kinds method/result, round-robin join, at most 48 method claims, no question in the instruction |
| R6, R7, R8, R10, R16, R17 | built (a0fcc1b, c5e25ed, 4fe960f, 200851c, 6782bb9, 3f1a385, 6c43d82); measured in 26.3: 30 of 32, 11-12 of 12 mismatches |
| R9, R19, R20, R23, R14 | built (ec16c24, cb34dbc, 048c65d); R23 measured in 26.4 |
| R13 | built as the `find_missing` scan + static facts + A read whole (53e1be6); a separate "usual causes" node was not built; **no gain shown on this pair** |
| R15 | built (9761758) |
| R18 | built: the planner may list only steps that a node runs (53e1be6) |
| **R21** | **built (eee0a70)**: on the stuffed path no claims and no scan |
| R22 | built (2c502d6): the impact column; `scripts/answers/score_answers.py` and `scripts/retrieval/score_topn.py` were read first |
| R11 | slice 14 (Jev). M15 measured Jev at 27-29 of 32 as a checker; tonight's LLM checker 28-29 is the baseline it must beat |
| R12 | slice 12 (ranking claims of a big A) |

#### 26.8 Other measurements of tonight

- **M23 (section 23):** Gemini 3.6 Flash, finally measured: one call over the whole ~90K, recall 0.94 and precision 0.86 in 42 s; parts of 28K, 0.92 / 0.85; parts of 12K, 0.94 / 0.81. Rule C (parts of one fixed size) still holds. **DeepSeek V4 Flash on OrcaRouter answered 429 "free capacity is limited" on every call again**: unmeasurable on the free tier. Results: `results/m23/results.jsonl`.
- **The live smoke test of the three new calls** (`tests/smoke/test_claims_answers.py`): **1 passed in 74 s** (code 3f1a385): the claims tool call, the check tool call and the new-query call all answer live.
- **The full weekly smoke run was dropped on purpose** (it is the liveness check of every tier, about 80 requests, it measures nothing about slice 7, and GitHub runs it every Monday), **but it ran by accident from 23:01 to 23:39 and spent quota before it was stopped; its result was not read or used.** The cause: stopping a background batch killed its Python job, not its shell script, which went on alone (it also ran M23 a second time, hence the doubled rows in `results/m23/results.jsonl`, and the claims smoke test a second time: passed, 85 s). Lesson: stop a batch by its shell AND its Python processes (the venv starts a second Python under the first), and check with a process list.
- **The whole suite** (unit, api and database tests, no `--run-smoke`): **2007 passed, 138 skipped, 1 failed** in 9 min (code 0642da0). The one failure was a database connection that Supabase closed in the middle of a request ("SSL SYSCALL error: EOF") in `test_two_uploads_then_a_question_produces_a_cited_answer`; it passed 2 of 2 alone. The earlier full run of the same night had 12 real failures: integration tests that pinned rules changed tonight (fixed in 0642da0). Unit and api alone: 1834 passed, 5 skipped. `ruff check .` and `ruff format --check .` clean.

#### 26.9 What is decided, and what stays open

- **Decided and built:** everything in 26.6 and 26.7.
- **Decided, not changed:** the rerank window (20), rerank on, A read whole up to 10,000 tokens, the scan kept as a planner step, `PRIOR_SHARE` 0.25 (10% looked no worse at 30K, but its effect on a report was not measured).
- **The claims group size is NOT settled (M27):** groups of 2K and 2.9K are within the noise of each other (the same 2K setting gave 9.3 and 7.7 of 12), and 4K to 8K were never tried on real claims. A real measurement on papers of 28K to 96K is owed in slice 12.
- **Not measured, so not claimed:** a second pair (a big repository as B, and as A); the scan, the rerank window and a cap on the parts list on a big B; Jev inside the graph (slice 14); more repeats of each cell; #14 (vocabulary cap), #17 (`requires_grad` as an optimizer key) and #18 (judged once, by F3w), which need `find_bugs` (slice 9); #10b, which needs the results part of the answer instruction (slice 10, section 31).

#### 26.10 The `find_missing` scan is a DEMO version, and slice 9 must redesign and tune it (D77, the user's call, 2026-10-28)

Found while the changes of 26.x were explained to the user, line by line. It is **accepted for now** and written here so it is not forgotten.

**What the code does today.**
- `api/differences.py` reads B in groups of about `DIFFERENCES_GROUP_TOKENS = 2,000`, at most `SCAN_TOKENS = 40,000` of B in all, `GROUPS_AT_ONCE = 4` calls at the same time.
- If A is at most `A_WHOLE_TOKENS = 10,000`, the WHOLE of A is put beside EVERY group, so A is sent again in every call. With 20 groups that is 200,000 tokens of repeated A. The user's judgment: this is not efficient at all.
- Above 10,000 tokens the scan sees NO A, and cannot say what A is silent about. `CLAIMS_BUDGET = 28,000` (claims, A sent once, in groups of 2,000) is a different limit for a different job, so between 10,000 and 28,000 the claims step reads all of A and the scan reads none. Nothing in the docs said so before.

**What slice 9 must do (none of it is done):**
1. **Change the algorithm.** Do not send all of A with every group. Candidates, to measure and not to assume: send each group only the parts of A closest to it (search A with the group's text); or first make a short list of what A says (the claims already exist) and compare the group with that list; or one call per group of A against a short summary of B.
2. **Tune the numbers:** `A_WHOLE_TOKENS` (10,000), `DIFFERENCES_GROUP_TOKENS` (2,000), `SCAN_TOKENS` (40,000), `GROUPS_AT_ONCE` (4) and `MAX_ITEMS_PER_ANSWER` (40). They are first guesses; the group size of 2,000 came from the claims measurements (25.2) and was not measured for the scan.
3. **Measure on a big pair** (the new pair of slice 12 or a repository as B): the scan never raised the score on `quora_siamese` (26.2, point 4), and the case it exists for, a B too big to read whole, was never measured. Count the cost in tokens and seconds, the items that match a known finding, and the items that match none (S2 gave 16 to 18 of about 34).
4. Re-run the end-to-end baseline of D74 after the change.

This is the same open item as "the scan, the rerank window and a cap on the parts list on a big B" in 26.9. A related note: the claims group size is also unmeasured (M27, section 18.4).

**The "never called" findings of the scan are also a demo, and need to be thought over again in slice 9 (the user's call, 2026-10-28).** `api/differences.py` adds, after the model's items, one `CodeFinding` for every function that `FileFacts.unused` says B defines and never names again. Why it is there: a group of 2,000 tokens cannot know that no call exists in the rest of the file, so the model cannot list "B writes it and does not do it" (the class weight #6 was a false match in every checker arm, 25.5). The problems to think over:
1. The text always says "A does not say" (`A_SILENT`) and the code never looks at A. When A does describe the function, the label is false.
2. The checker already gets the same fact for the claims it checks. The same function can be reported twice, and nobody checked whether the report removes the duplicate.
3. A never-called function is a defect, not a difference from A. `find_bugs` (slice 9) is the natural place; the scan only took it because it was the nearest step that hands B-alone findings to the report (commit 53e1be6).
4. No measurement of the scan with and without these findings exists. The result of 26.5 (I5) mixes the checker and the scan.
5. `_def_line` tests `f"def {name}" in line`, a substring test, so `fit` also matches `def fit_one`; the first line wins. The quote of these findings is not passed through `has_quote`; it is read from the part's own text, except when the part was not scanned (the 40,000-token limit): then the quote is only the name and the evidence is empty.
6. `by_header` is keyed by the header text; two parts with the same header would overwrite each other (headers carry the line range, so this is unlikely, and it was not checked).

#### 26.11 THE CLOSING REVIEW OF SLICE 7 (written 2026-10-28)

*The Working Rules ask for one review after the last lesson of a slice. For slice 7 the work was done in two passes and recorded in two places. This section joins them and says what is still open. It adds no new measurement.*

**The standing question: which real failure is still unprotected?**

| pass | where it is recorded | what it found and did |
|---|---|---|
| 1. The review in a scratch copy of the committed tree (2026-10-24) | 25.10 | D-1: one failed claim search lost the whole answer (3 database tests failed on the old code). D-2: two stray `+` characters in the claims instruction. D-3: no weekly live test of the three new calls. 11 tests were added; 7 deliberate breaks, each caught by its own test |
| 2. The late-night build (2026-10-24) | 26.6 | 11 defects fixed, each with a test and a deliberate break caught by its own test (for example: citations that did not resolve when there were findings, the never-called reader that missed methods and reported a framework hook, the chat saved on an idle connection) |
| 3. The checks that join the new parts | 26.3, 26.4, 26.8 | The check node as it is wired in `ask()` was measured (30 of 32, 11 and 12 of 12 mismatches, no false match). The line from the store to the writer was measured (`run_r23.py`, coverage of 39). A live smoke test of the claims, the check and the new query passed (74 s). The writer stored and read back 826 rows over SSL twice with no error |
| 4. The whole suite | 26.8 | 2007 passed, 138 skipped, 1 failed: a database connection that Supabase closed in the middle of a request, which passed 2 of 2 alone. Unit and api alone: 1834 passed, 5 skipped. `ruff check .` and `ruff format --check .` clean. The unit suite includes the architecture, packaging, docs and script-name tests |
| 5. The decisions written down | 27 | The 22 changes, each with its reason, its numbers, its place in the code and what is still open |

**What is NOT closed, and where it goes:**
- **G20** (a claim that something is NOT done) was closed on 2026-10-28 by one sentence in the check instruction (CHECK v4, 26.12): 31 of 32 in two runs, G20 a confirmed match. It still needs more pairs (27.1).
- **The `find_missing` scan is a demo version** (D77, 26.10): slice 9.
- **Every number and decision rests on one pair** (27.1): slice 13.
- **The group size of the claims** (M27), the three linked size limits (27.1) and the re-run of `run_r23.py` on a big B: slices 12 and 13.
- **Jev** is measured once (25.5) and its code and measurements are kept for slice 14 (D73).
- **The weekly smoke run** was not run for the whole chain after these changes. The three GitHub secrets for the new tiers and keys exist (the user said so on 2026-10-24).
- **Lessons 2 and 3 and most of 26 were written by Claude at the user's request** (an exception to "the user types all product code"). The user may read that code in the same way as the earlier lessons.

**Verdict.** No known failure that loses an answer is left unprotected. Slice 7 can go to `main`, and slice 8 can start from `main` on a new branch (ask the user first).

**The full pass of 2026-10-28 (added; it replaces the "no new check" remark above).** The table above only joined the old passes. This is the real pass of the Working Rules, done on the committed tree plus the CHECK v4 edit.

| step of the rule | result |
|---|---|
| Read the code that joins the new parts | `FileFacts` and the scan share the request connection across threads. This is safe, because the compare route opens it with `autocommit=True`, so one failed query cannot break the others. `FileFacts.expand` recomputes the constant setters of the whole file at every check: 4 ms over 829 parts, so it is fine now; about 0.1 s per check is expected for 24,000 parts, to re-check on a big B (slice 12) |
| Joins that no test crosses | **(1)** `whole_side` (decision 12) was tested only with fakes: no test went through `ask()` over a real store with a small A and a big B (the other big-B tests use an A of 60 parts, too big to be read whole). **(2)** `respond` was tested only for the `evidence` argument, never for the `chunks` list it saves, which the page resolves the citations against (decision 14). **(3)** the cap of 48 method claims was tested with the constant itself (`MAX_CLAIMS + 5`), the self-fulfilling shape this project knows. **(4)** nothing pinned the CHECK v4 sentence. Not added: a citation test from a real store through `ask()` with evidence outside the pile |
| Break one line for each invariant | 18 deliberate breaks of decisions 1, 2, 5, 11, 12, 13, 14, 15, 16, 17, 19, 20, 21, 22 and CHECK v4, each on a kept copy of the file. **15 were caught** by an existing test. **3 were NOT caught: decision 14 (the missing parts put in FRONT of the list), decision 2 (the cap raised to 4800) and the CHECK v4 sentence.** They match gaps (2), (3) and (4). Gap (1) was found by reading, not by a break |
| New tests | **5 tests in 4 files**, written in a scratch copy and NOT yet in the repository: `artifacts/slice7-review/tests2/` (a README and the four whole files). Each was proved to fail on its own break (`harness/run_new_breaks.py`) and passes on the clean code; `ruff` is clean; the four files give 90 passed. The user pastes them in |
| Dead code and scripts | `checks_text` and `code_findings_text` in `api/prompting.py` are used only by tests since `prior_text` replaced them: a candidate to delete (the user types it). `lock_tables` is used by `scripts/setup/setup_checkpoints.py`. The script-name tests pass |
| The whole suite | **2008 passed, 5 skipped, 0 failed** (unit, api and database tests, 10 minutes, `--run-smoke` not used), after the CHECK v4 edit. `ruff check .` and `ruff format --check .` clean |
| Docs | this block, 26.12, section 27 |

**Still open after this pass:** the 5 tests above must be pasted in; the two unused functions; the weekly smoke run was not run; the citation test through `ask()` with evidence outside the pile.

#### 26.12 G20 closed by CHECK v4 (2026-10-28)

*Done at the user's request, as the last open item before slice 8. It is one sentence in `prompts/checks.py` (`CHECK_VERSION` 3 to 4): "A claim can also say that something is NOT done, or is left out. Then a match means a part shows that it is switched off or left out: give that part. If no part shows it, the verdict is absent, never match." The wording names no field of study. Claude made the edit under the same exception as the late night of 2026-10-24.*

**Measured** (`run_m24_arms.py wired+retry`, the same 32 claims, Flash-Lite first, exit AS58212 dataforest, Google 200, a new throwaway schema that was dropped afterwards, nothing else changed between the runs). Before: two runs of the code without the sentence, 30 of 32 each, G20 `unchecked` both times (26.3). After: two runs, **31 of 32 each**, 11 of 12 mismatches found, **20 of 20 matches confirmed**, no false mismatch, no claim `unchecked`. The only wrong claim in both runs is G29, answered `absent`. G20 is now a confirmed match. Results: `artifacts/slice7-review/results/g20_run1.log` and `g20_run2.log` (git-ignored).

**Limits, as always:** one pair, one claim whose fix this is (G20 is in the key), 2 runs, and a gap of 1 of 32 is inside the noise of the other claims. The sentence is aimed at a kind of claim, not at this one, but only more pairs can show that (27.1). Unit and api tests: 1834 passed, 5 skipped. `ruff check .` and `ruff format --check .` are clean. The change is not committed.

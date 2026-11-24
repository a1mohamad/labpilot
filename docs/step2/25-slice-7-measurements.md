# Section 25: slice 7, measurements and closing review

[Docs home](../README.md)

### 25. SLICE 7 — THE MEASUREMENTS AND THE CLOSING REVIEW (M10, M11, M21, M24, M15, D74) — 2026-10-24

*Done in one session after lesson 3, with the user's order "run all the measurements, be very precise". Nothing was written into the repository while it ran (a `merge_per_file.py` run needs a clean tree); all scripts and result files were in the session scratchpad and were copied afterwards, without the file that held the database password, to `artifacts/slice7-review/harness/` and `artifacts/slice7-review/results/` (git-ignored, so NOT in git; the hand-made answer key of 32 claims is `harness/gold.py`, and how to run it all again is in `artifacts/slice7-review/README.txt`). Exit AS58212 dataforest, Frankfurt, Google 200. The throwaway schema `labpilot_m7_5c6b53` was dropped at the end. The repository was not changed by the measurements.*

#### 25.1 Method, and its limits (read before quoting any number)

- **One paper, one answer key.** The key is `A_paper.md` against `B_train.py`: 32 hand-made claims (20 where B matches, 12 where it does not), each with the verdict and the deciding lines of B. It was made by one person for one pair: a fixture may REJECT, never CONFIRM.
- **M10 and M21 coverage is a REGEX SCREEN** (a claim "reaches" a fact if its text holds the fact's words). It is a screen, not a score. M24 and M15 compare real verdicts with the hand-made verdicts, which is a score.
- **Replicates:** Gemini does not repeat itself at temperature 0, so each cell has 2 to 8 runs. A difference of one claim in 32 is noise.
- **The checker's quote guard changes some runs.** The last four M24 rerank runs were pinned to one model (Flash-Lite 3.1); on that model the guard refused two true quotes every time and left those claims `unchecked`. This lowers the two rerank arms by about 1.5 claims.

#### 25.2 M10 — what changes the list of claims (Flash-Lite 3.5, 6 to 8 runs for each cell)

Facts of the key that the claims reach (12 mismatch facts, 20 match facts):

| way of asking | claims | mismatch /12 | match /20 |
|---|---|---|---|
| shipped call, one call over the whole A (stray `+` lines removed) | 12.2 | 3.2 | 6.5 |
| same, with a NARROW question ("clip") | 5.5 | 2.2 | 5.8 |
| same, no question | 10.6 | 2.1 | 11.9 |
| wording E (also rules and steps), cap 15 / cap 20 / no cap | 13.5 / 14.9 / 18.2 | 3.4 / 3.1 / 2.5 | 10.2 / 12.6 / 10.8 |
| wording G (settings and steps only, one value for each claim) | 13.2 | 4.0 | 12.9 |
| walk every part, no question, cap 40 (best single call) | 24.5 | 5.7 | 17.0 |
| **A cut in groups, one call for each group, same wording:** whole A (18 parts, ~4K tokens) in ONE call | 19.5 | **2.8** | 15.8 |
| 2 calls of 9 parts (~2K tokens each) | 43.7 | **9.3** | 19.0 |
| 3 calls of 6 parts | 55.0 | 9.0 | 19.7 |
| 6 calls of 3 parts | 70.0 | 9.3 | 19.7 |
| 18 calls of 1 part | 86.3 | 10.0 | 20.0 |

**The finding:** one call over the whole of A reaches about a quarter of the facts, whatever the wording, the cap or the question. The same wording in two calls of about 2,000 tokens reaches three quarters. The cliff lies between 2K and 4K tokens (nothing between was tried). The cap is NOT the problem (cap 15, 20 and none are within noise); attention over a long input is. A narrow question really does shrink the list (12.2 to 5.5 claims), which is the risk D25 named. **D68's 12K part size came from a proxy (68 constants) and is WRONG for real claims: use about 2K.**

#### 25.3 M21 and M11 — other models, and other kinds of A

M21, 2 runs for each cell, shipped call against two calls of 9 parts. Mismatch facts reached /12, and the share of claims the quote guard dropped:

| model | shipped | dropped | grouped | dropped |
|---|---|---|---|---|
| Flash-Lite 3.5 | 5.0 | 0% | 9.0 | 0% |
| Flash-Lite 3.1 | 4.0 | 27% | 9.0 | 0% |
| Gemma 4 26B | 5.0 | 7% | 11.0 | 0% |
| Ministral 8B | 2.5 | 29% | 10.0 | 10% |
| Mistral Nemo | 3.5 | 36% | 9.5 | 10% |
| Ministral 14B | 3.5 | 10% | 4.5 (30 claims) | 7% |
| GLM-5.3 Flash (Cline) | 5.5 | 3% | 10.5 | 0% |
| DeepSeek V4.1 Flash (LiteRouter) | 6.5 | 0% | 9.0 (1 run) | 0% |

Groups win for every model, including the free Mistral models. Small models lose 29% to 36% of their claims to the shipped quote rule in one call (true quotes with formulas and escapes; the dropped claims were read, none was invented).

M11 (GLM-5.3 Flash, 2 runs): a real paper (Adam, PDF, 8 calls of ~2K) 91 to 133 claims against 15 from one call, default settings reached 6 of 6 against 5 of 6; a Python file used as A (`B_train.py`, 9 calls) 255 to 292 claims against 15; a Go library (`gg`, 7 calls) 184 to 207 claims against 15, mostly paraphrases of docstrings. **Claims per 1,000 tokens: about 7 for prose and about 14 for code**, so a big A needs ranking (slice 12, D69).

#### 25.4 M24 — rerank for each claim, and what the retry loop fixes alone

Check node of the shipped code over the 32 claims (all searched in B). Mean over the runs:

| arm | runs | right /32 | mismatch /12 | match /20 | absent | unchecked | extra calls for 32 claims |
|---|---|---|---|---|---|---|---|
| plain (shipped lesson 2) | 3 | 23.7 (23-24) | 5.0 | 18.7 | 6.7 | 0.3 | none |
| plain + retry (shipped lesson 3) | 4 | 27.2 (26-28) | 7.8 | 19.5 | 2.8 | 0 | +9 searches, +9 checks, +9 query writers |
| rerank | 4 | 25.8 (24-27) | 7.2 | 18.5 | 3.8 | 1.5 | +32 reranks |
| rerank + retry | 4 | 28.8 (28-31) | 10.2 | 18.5 | 0.8 | 1.5 | +37 reranks, +5 searches and checks, +5 writers |

Evidence hit@6 (does one of the 6 parts hold a deciding line): plain 28/32, rerank 31/32. The retry loop alone brings the verdicts (27.2) close to what PERFECT evidence gives an LLM (28 of 32 with Flash-Lite 3.5, M15 oracle). **Decision: no rerank for each claim.** It adds about 2 right verdicts for 32 extra Flash-Lite calls, and on top of the retry about 1.6 for 37 calls. The retry is kept.

What the retry writes: a few words in the code's names, often taken from the checker's note (`CLIP_NORM max_grad_norm`, `label_smoothing 0.1`). Two kinds of poor query were seen: it guesses names that are not in B (`train_split dev_split test_split`), and once it put the value into the query (`CLIP_NORM = 1.0`). Calls are about +28% for the retry.

#### 25.5 M15 — who gives the verdict: an LLM or Jev (the pilot of D73)

Same 32 claims, same evidence for every arm. "Shipped" is the first 6 parts of the plain search; "oracle" holds the deciding parts first (it isolates the verdict from the search). One run each. FALSE-MATCH is the dangerous error (B differs and the arm says it matches).

| arm | shipped evidence | oracle evidence | time for 32 claims | false match |
|---|---|---|---|---|
| Jev, one claim for each call | 27/32 | 29/32 | 8.5 to 10 s | G30 (shipped); G25, G30 (oracle) |
| Jev, 8 claims for each call | 29/32 | 29/32 | 3.2 to 3.5 s | G25, G30 |
| Flash-Lite 3.5, tool call | 23/32 | 28/32 | 93 to 99 s | G30 |
| Flash-Lite 3.1, tool call | 23/32 (1 failed) | 27/32 (2 failed) | 77 to 152 s | G30 |
| Gemma 4 26B, tool call | 15/32 (13 failed) | 17/32 (11 failed) | 106 to 114 s | G28, G30 |

- Jev cost about $0.003 for the 32 claims, and its mean confidence was 0.81 to 0.86. **Confidence is not a safe filter:** Jev was 0.95 sure of a wrong "match" (G25) and of a wrong "mismatch" (G16).
- **The neighbour effect is real:** with the shipped evidence the verdict of 4 claims changed between "one claim for each call" and "eight for each call" (G16, G22, G23, G25). With the oracle evidence none changed. So send a claim alone.
- Gemma 26B fails on the per-minute input room (about 16K for each key and model) when 4 checks run together: it is not a checker.
- Jev gives a verdict and no quote and no part number, so code must pick the part that goes into the `Finding`.
- **`G30` ("a function is defined and never called") is a false MATCH in every arm of every kind.** The checker sees the definition and answers match. This is the class the report most needs.
- Verdict for the pilot: on this one pair Jev is at least as good as the LLM tiers, 10 to 30 times faster, and nearly free. It is NOT proven (one pair, one run for each cell, 1 or 2 claims of difference). Slice 14 stays in the plan.

#### 25.6 D74 — the end-to-end baseline on the SEARCH path (one run, scored by reading)

`ask()` as shipped, the sample pair, the default question, the search path forced as the weekly smoke test does (a budget of 20,000; at the real 30,000 this pair is read whole, so this is a harsh test and not what a user of this pair would see). Tier 1 (GLM-5.3 Flash) planned and wrote the report: 184.9 s, `STOP`, 9,699 characters, 47 of 48 citations resolve. The planner listed `extract_claims`, `find_missing`, `find_bugs` and `extract_outcomes` (only the first exists). **Claims: 10, written by Flash-Lite 3.5 in one call: 6 were results or ablation rows, 3 were architecture, 1 was a setting (weight decay).** The checks flagged weight decay (0.01 against 1e-3, correct), and flagged a result row as a "mistake" because B has `NUM_HEADS = 4` (noise).

Score against the 19 findings of `EXPECTED.md` (impact classes below):

| class | judged | surfaced | absent |
|---|---|---|---|
| carries the story (5) | #6 class weight, #9 threshold, #10b train/val gap | #11 stopwords (named as a possible cause with its 4.1 price, not confirmed) | **#1 pooling projected features: listed as a MATCH** |
| secondary (12) | #8 no test split, #13 cosine feature | #7 warmup (named, "not shown") | #2, #3 (listed as present on both sides), #4, #5, #10, #12, #14, #17, #18 |
| moves nothing (2) | - | - | #15, #16 (correctly ignored) |

Judged 5, surfaced 2, absent 12 (10 of them countable). **Weighted judged score 13 of 39** (story 3, secondary 2, nothing 0). The single-call runs of 2026-08-17 found "13 of 19" with all the code in one prompt and a looser count; that is a different unit and a different test, NOT a like-for-like comparison, and the current app has never been measured on the full pair. **Four faults in the text, not only gaps:** (1) the "matched" list says attention pools "hidden states not projections" (the flagship divergence, #1); (2) it says label smoothing is "present on both sides" and never compares 0.1 with 0.05; (3) it says A "keeps embeddings frozen", but A unfreezes them at epoch 3, so its first and largest cause is partly a misreading; (4) the weight decay mismatch that the checks handed over is not in the report. One run, one tier: a number to beat, not a verdict on the design.

**What reached the report writer (read from the saved prompt afterwards, no quota).** It saw 10 of the 82 parts of B and 10 of the 18 parts of A. Of the 10 countable misses, the code of **7 never reached the writer** (#1, #2, #5, #10, #12, #14, #18) and 3 did and were missed (#3 label smoothing and #17 `requires_grad`, both in the parts it saw, and #4 weight decay, which the check block handed over and the writer dropped). The check block held 10 claims: 2 result rows "mismatch - mistake" (noise), 1 weight decay "mismatch - choice", 4 "absent" (3 result rows and the stopword ablation), 3 architecture "match". **The biggest cause, stopword masking (#11, -4.1 F1), WAS asked about** (the claim "Masking stopwords out of the attention results in an F1 score of 0.810") **and ended "absent" after 3 searches in B** where `_build_stop_mask` exists: the first search used the claim's own words, and the two retry queries were `stopwords attention f1` and then `f1 score change`, which drifted away from the mask. The other causes were never asked about, because the claims were results and architecture, and the causes that A never states (#11 to #14, #17, #18) belong to `find_missing` and `find_bugs`, which are not built (slice 9). The planner wrote 5 queries; their text is not in the log, only their number.

Impact classes used for the score (a proposal for the impact column of `EXPECTED.md`, prices in F1 come only from `EXPECTED.md`; where it gives no price the cell says so):

| # | finding (short) | class | weight | price in F1 |
|---|---|---|---|---|
| 11 | stopwords masked out of attention | story | 3 | -4.1 |
| 6 | positive-class weight defined, never called | story | 3 | -1.9 |
| 1 | pools projected features, not hidden states | story | 3 | -1.4 |
| 9 | threshold tuned on the split it is reported on | story | 3 | about +1.5 (optical) |
| 10b | train 0.9439 against val 0.8226 (gap 12.1, the paper says 2.1) | story | 3 | no price |
| 7, 8, 2, 3, 4, 5, 10, 12, 13, 14, 17, 18 | the secondary findings | secondary | 2 | #7 -0.8; #8 part of the +1.5 of #9; the others no price |
| 15, 16 | rows dropped when empty; three dead layer-norm modules | nothing | 0 | 0.0007% of rows; 0.01% of parameters |

Best weighted score 39 (5 x 3 + 12 x 2). Reporting a "nothing" finding is not an error and earns 0. A "right fix" column (M17) is a separate job.

#### 25.7 Recommendations (what to change, in order of value)

| # | change | where | evidence |
|---|---|---|---|
| R1 | **Cut A into groups of about 2,000 tokens and call `list_claims` once for each group, all together.** Never cut inside a part | `prompts/claims.py`, `api/claims.py`, `agent/extract_claims.py` | 25.2, 25.3: 9.3 against 2.8 to 3.2 of 12 facts, for 8 of 8 models |
| R2 | Do not ask for "at most 15", and do not reject a whole answer for more than 20 claims. Join the groups round-robin, drop claims whose quote fails, and keep at most a number you can check (first guess 40) | `CLAIMS_WANTED`, `MAX_CLAIMS`, `read_claims` | the cap is not the lever; a cap of 20 would throw away a good 44-claim answer |
| R3 | Take the user's question OUT of the claims instruction | `build_claims_prompt` | 12.2 to 5.5 claims with a narrow question |
| R4 | Tell the writer to skip reported results (table rows). They stay as `result` claims for the answer instruction (slice 10 was redesigned on 2026-11-12, section 31) | `CLAIMS` instruction | D74: 6 of 10 claims were results or ablation rows, and their checks were noise or "absent" |
| R5 | Remove the two stray `+` characters at lines 37 and 38 of `prompts/claims.py`; bump `CLAIMS_VERSION` to 3 with R1 to R4 | `prompts/claims.py` | they are in the text the model reads; the new test `test_no_instruction_has_a_line_that_starts_with_a_stray_plus` fails until they are gone |
| R6 | Quote guard: keep exact matching, but when the verdict and the part number are valid and only the quote is not found, keep the verdict and mark the quote unverified, instead of rejecting the answer three times and ending `unchecked`. The extra normalisation tried in the scratchpad (`quote2.py`) recovered most true quotes with no false accept on damaged-quote controls | `agent/check_schema.py`, `agent/_quote.py` | 2 claims `unchecked` in every pinned run; 27% to 36% of claims dropped for small models in one call |
| R7 | **Keep `MAX_RETRIES = 2` and `EVIDENCE_PARTS = 6`. Do NOT add a rerank for each claim.** Tell the query writer never to put a value in the query | `check_one.py`, `prompts/requery.py` | 25.4 |
| R8 | The check instruction: a function or constant that is only DEFINED does not do what the claim says; look for a call or a use. Not measured. Test it on `G30` and on a few new cases before keeping it | `prompts/checks.py` | 25.5: a false match in every arm |
| R9 | The report instruction: every `[mismatch]` of the "already found" block must appear in DIFFERENCES, and a "matched" line needs a quote from B | `prompts/answer.py` (`TWO_FILES`) | D74: weight decay lost; two false matches |
| R10 | Product defects, no measurement needed: the question embed has no wait on a 429 (Mistral `backend_out_of_capacity` seen on 2026-10-24); `search_one` has no retry when the pooled connection dies (`SSL SYSCALL EOF` seen); one retried claim can take 185 s when a tier is slow | `api/searching.py`, `agent/search_one.py` | seen in the harness |
| R11 | Slice 14 stays: Jev for the verdict, one claim for each call, `choice` with three labels, code picks the quote part. Keep the LLM check as the backup | `agent/check_one.py` (the injected `check`) | 25.5 |
| R12 | Slice 12 needs ranking: claims grow with the size (7 or 14 for each 1,000 tokens). Slice 13 must re-run D74 with R1 to R5 in place | - | 25.3 |

**What stays as it is:** `MAX_RETRIES` 2, `EVIDENCE_PARTS` 6, the plain search for the check, the exact-match guard as a base, the injected `check` and `new_query` functions.

#### 25.8 Not measured

Other papers and other languages for R1 (one paper, one model for the size sweep); sizes between 2K and 4K; the effect of R2 to R5 together; Jev with a second pair, repeats, or inside the real graph; Jev with a code-picked quote; a check that reads call sites (R8); the report with R1 to R5 in place; the current app on the FULL pair (read whole), which is the missing control for D74; the weekly smoke run.

#### 25.9 The user's question after D74: does the system find the real causes?

Asked on 2026-10-24: *"our current RAG system has a real issue in finding the real root causes, because it cannot hand them to the report model, do you agree?"* The answer, from the saved D74 run and the other measurements:

- **Right on the symptom.** The causes that carry the story did not all reach the report: of the 5, three were judged, #11 only surfaced and #1 was written down as a match. 7 of the 10 countable misses were never in the writer's prompt, and the biggest cause was asked about, searched 3 times and ended "absent" (25.6).
- **Not the search itself.** When a search gets a good query it finds the part: hit@6 is 28/32 plain and 31/32 with rerank (25.4), and recall@50 was about 0.99 over 20 corpora (Step 1). The break is upstream: what we ask, and what is not built yet.
- **Four causes of the gap** (one run, so their weights are unknown):
  1. The claims are the wrong kind: result rows cannot be found in code, and they used the retries (R1, R4).
  2. Claims come from A only. The causes that A never states (#11 to #14, #17, #18) belong to `find_missing` and `find_bugs` (slice 9, not built). `EXPECTED.md` says of #11 that it "needs two chunks from two classes".
  3. A sentence about results does not look like code: "masking stopwords gives F1 0.810" shares no words with `_build_stop_mask`. The retry writer guesses names from the checker's note, and when the note only says "not found" it has nothing to guess from and drifts (`f1 score change`).
  4. Nothing asks in advance what usually causes a gap like this. The design already has the idea (Retrieval Design, "The knowledge split"): the model first lists the usual causes (class weighting, masking, threshold leakage, seeds, warmup) and each one becomes a search in B's own words. Today only the planner's 5 queries do this job, and their text is not in the log.
- **R13 (a candidate, NOT decided): a cause-finding step.** A node that, from the question, the numbers in A and B and the outline of B, lists the likely causes and searches B for each one in B's vocabulary. It is not a slice in the plan. The user wants it designed together as the next job, after this review. It needs R1, R4 and slice 9 as well.
- **R14: write the planner's queries into the log** (the plan is in the saved chat, but the log keeps only their number).

#### 25.10 The closing review of slice 7 (2026-10-24)

The standing question: which real failure is still unprotected? It was done in a scratch copy of the committed tree (`git archive HEAD`); the repository was not changed by the review. At that moment `main` and `feat/check-claims` held the identical tree (`git diff main feat/check-claims` empty): the user had finished moving the branch to `main` one file per commit with `merge_per_file.py`.

**Read:** the graph wiring, `check_one`, `extract_claims`, `fan_out_claims`, `remember`, both schemas, `api/asking`, `checking`, `claims`, `requery`, `chains`, `searching`, the connection pool, the prompts, and the 30 tests of slice 7. **Baseline before any change:** unit and api 1706 passed, 5 skipped (70 s).

| # | finding | proof | state |
|---|---|---|---|
| D-1 | **A search that fails for ONE claim (the embedder is down, a database connection dies, the pool times out) loses the WHOLE answer.** `check_node` catches only `CheckError`, and the search the claims use is the question's own `search_one`, which raises `EmbeddingUnavailable`, `ArtifactChanged` or a raw `psycopg` error. The claims are a safety net (D39), and `claims_node` already lets the answer go on when the claims step fails. Seen live in the harness on 2026-10-24 (a dropped pooled connection, `SSL SYSCALL EOF`; a Mistral 429 on a question embed) | 3 new database tests FAILED on the unmodified code (embedder down, database drop, pool timeout); the guard test (the question's own search must still stop the answer) passed | a fix was built and tested in the scratch copy; handed over as a patch; NOT in the repo |
| D-2 | Two stray `+` characters at the start of two lines of the `CLAIMS` instruction (lines 37 and 38 of `prompts/claims.py`), in the text the model reads | the new test `test_no_instruction_has_a_line_that_starts_with_a_stray_plus` fails on the repo text and passes once they are removed | patch handed over |
| D-3 | No weekly live test of the three calls slice 7 added (claims through a tool, the check through a tool, the new query). A tier that stops honouring tools would show up as a report with no findings and no error, because a failed claims step is only logged (D65) | the new smoke test `test_claims_a_check_and_a_new_query_work_on_stored_files` PASSED once live (2 minutes, Flash-Lite first) | file handed over |
| smell | `search_one` holds a pooled connection while the question is embedded (`_searched` embeds first); the pool has 8 connections and no timeout setting (psycopg_pool default: 30 s); up to 20 claims with 3 searches each can be in flight. A slow embedder can starve the pool. With D-1 fixed this ends as `unchecked` claims, not a crash | read from the code, NOT measured | R16 |

**Checked and fine:** no dead names in the 16 files of slice 7; no script names a removed function; the layer, error-boundary, public-API and docs-heading tests pass; the saved chat keeps no claims and no findings (an existing database test); the retry loop is bounded (existing tests); `ruff check .` and `ruff format --check .` (the two commands CI runs) are clean on all 372 files of the scratch copy, with the fix and the new tests in place.

**The fix, as tested.** `build_graph` takes an optional `search_claim` (it defaults to `search_one`, so nothing else changes). `_ask_graph` gives it a small wrapper that turns `EmbeddingUnavailable`, `ArtifactChanged` and `psycopg.Error` (`PoolTimeout` is one) into `CheckError`, which the existing `check_node` already turns into an `unchecked` finding. The question's own search is untouched and still raises. Not chosen: a broad `except Exception` inside the node, because it would hide our own bugs (break M3 below catches that).

**New tests: 11, in 5 files.** `tests/integration/test_claims_over_the_store.py` +4 (the three faults and the guard), `tests/api/test_ask_claims.py` +4 (three faults and a bug that must not be hidden), `tests/unit/agent/test_check_one.py` +1, `tests/unit/prompts/test_instructions.py` +1, `tests/smoke/test_claims_answers.py` (new, 1).

**Breaks, one line each, in the scratch copy (every file restored from a kept copy, every anchor asserted):**

| break | what fired |
|---|---|
| M1 database errors no longer caught | the api `database` case, and the integration `database-drop` and `pool` cases |
| M2 the wrapper does nothing | three api cases and three integration cases |
| M3 the wrapper catches every exception | `test_a_bug_in_the_search_is_not_turned_into_an_unchecked_claim`, alone |
| M4 the graph is not given the claim search | the api cases and the integration cases |
| M5 the graph ignores the claim search | `test_the_checks_search_with_the_function_made_for_them_when_one_is_given` and the integration cases |
| M6 the question's own search is also turned into a check error | the api `embedder-down` case and `test_a_search_that_fails_for_the_question_itself_still_stops_the_answer` |
| M7 a `+` put in front of a line of `CHECK` (after the two real ones were removed) | the stray-plus test, alone; with the two real ones removed it passes |

**Two mistakes of mine while writing them, both caught by running the tools the project already has.** A test name 89 characters long (`ruff check`, limit 88), and appended code that `ruff format` re-laid out. Nothing else needed repair.

**Whole suite in the scratch copy with the fix, the repaired text and all new tests:** the whole suite (unit, api and database tests, no `--run-smoke`) gave 1,884 passed, 138 skipped and 1 failed in 20 minutes (2,023 tests collected). The one failure was a database connection that Supabase closed in the middle of a search, in `test_a_chat_on_the_searched_path_is_saved_and_comes_back_as_real_objects` (a test that also failed once before, on 2026-10-21, with another network error); it passed 3 of 3 on a re-run, and it does not touch claims or any changed code. No skip is about the database; the skips are the smoke tests and three others with a stated reason.

**Handed over, NOT in the repository** (the user types the product code and pastes the tests): `artifacts/slice7-review/` (git-ignored) holds the five test files whole, three patches to read (`graph.diff`, `asking.diff`, `claims.diff`), `README.txt`, the impact column proposal, and the measurement harness with its raw results (`harness/`, `results/`). Check `git log` and `git status` to see whether they have been applied yet.

**Added to the table of 25.7:**

| # | change | where | evidence |
|---|---|---|---|
| R13 | A cause-finding step (25.9). NOT decided; to be designed with the user | new node, planner | 25.6, 25.9 |
| R14 | Write the planner's queries into the log | `api/planning.py` | 25.9 |
| R15 | **A failed search for one claim must leave it `unchecked`, not stop the answer** (D-1), with the three patches above | `agent/graph.py`, `api/asking.py` | 25.10 |
| R16 | Release the pooled connection before the question is embedded, or give the pool a timeout and `max_concurrency`; NOT measured | `api/asking.py` (`search_one`), `store/connection.py` | 25.10 |

#### 25.11 The complete list of changes, with corrections (written after an audit of the same night; where it differs from 25.7 or 25.10, THIS section wins)

The user asked whether every idea and correction was in the docs. It was not: two items of 25.7 needed correcting, and eight were only said in the conversation. Everything is below. The session that works on it follows the order of "The order" and does not change two things at once.

**A. Corrections to 25.7 (read these before typing R1)**

- **R1 was measured as ONE exact arm; port exactly it, then change one thing at a time.** The arm is: wording G (`HEADER_G` in `harness/extract.py`) without its last paragraph about the question; the closing line "List every claim this part states, or none if it states none."; no question; the parts cut into groups of about 2,000 tokens and never inside a part; one `list_claims` call for each group, all at the same time; NO total cap. R3 and R4 are inside this arm, so their effects cannot be separated from it. What was separated: wording G in ONE call over the whole of A gave 4.0 of 12 with the question and 2.8 without it, against 3.2 for the shipped wording, and 9.3 for two calls of 9 parts with the same wording: the groups are the lever, the wording is small.
- **R1 does NOT reach the findings that carry the story most.** Of the 12 mismatch facts of the key, the groups reach the nine value and step facts (clip norm, label smoothing, weight decay, unfreeze epoch, warmup, the three splits, the threshold, the seeds, the positive-class weight) and NOT these three (counted over the 16 grouped runs of Flash-Lite 3.5 in `results/m10c.jsonl`, 846 claims):
  - **Pooling of projected features (#1, G31): 0 of 16 runs by the screen of the key.** Read by hand, the claim that matters ("the projection W must not be applied to the vectors that are summed") appears in 2 claims of the 846, and "the projection W exists only to compute the scores" in 1. The generic claim "a multi-head additive attention layer pools the recurrent hidden states" appears in about 11 claims, and it leads to a false MATCH (D74 listed #1 as matched).
  - **The stopword mask (#11, G32):** reached 3 of 3 runs at 1 part for each call, 2 of 3 at 9 parts, 1 of 3 at 3 parts and 0 of 3 at 6 parts. The group size matters for it.
  - **The overfit gap (#10b, G33): 0 in every run.** Wording G throws away result sentences by design. This one needs the results part of the answer instruction (COMPARABLE and the sums; slice 10 was redesigned on 2026-11-12, section 31), not claims.
  - The quote guard is NOT the cause: it dropped 3 of 846 grouped claims.
  - So R1 lifts the value mismatches (#2 to #9) and the next steps must go after #1, #11 and #10b by other means: groups together with wording E (rules, and "what is left out") were never tried; group sizes between 2K and 4K were never tried; and see R13, R24, slice 9 and slice 10.
- **R2: the cap of 40 was never run.** The measured arm had no cap (44 claims at 9 parts for each call, 86 at 1 part). The real limit is cost: every claim is one search and one check, plus the retries (about 28% more calls). 44 claims is about 70 model calls for one question (44 checks, about 12 more checks and 12 query writes for the retries, 2 extraction calls), against 500 a day for each of 3 keys on Flash-Lite 3.5 and the same on 3.1. Choose the cap from the measured cost, then run it. Do not reject a whole answer for too many claims.
- **R4: wording G removes result sentences, and that has a price.** The ablation sentence "masking stopwords out of the attention gives F1 0.810, a change of -4.1" was the only claim about the biggest cause in the D74 run (the single call skipped the method sentence). Wording G drops it. Decide knowingly: keep wording G and get the mask from the method sentence (3 of 3 at 1 part for each call), or keep result sentences that NAME a component and let the writer state the component without the number.

**B. The complete list.** R1 to R16 are as in 25.7 and 25.10 with the corrections above. Added:

| # | change | where | evidence | how to check it |
|---|---|---|---|---|
| R17 | The query writer sees the outline of B (the same `build_map` the planner uses) and must keep the topic words of the claim. Today it guesses names that are not in B and drifts (`stopwords attention f1`, then `f1 score change`, while `_build_stop_mask` exists). Also tell it never to put a value in the query (R7) | `prompts/requery.py` (`REQUERY`, `build_requery_prompt`), `api/requery.py` (`make_query_writer`), `agent/check_one.py` (`NewQuery`) | 25.4, 25.6. This is also the "jargon bridge" that D14 named and no node covers | `harness/run_m24_arms.py`, plain + retry arm: right /32 (27.2 now), and the share of retry queries whose names exist in B (grep them against `B_train.py`) |
| R18 | The planner may list steps that no node runs (`find_bugs`, `find_missing`, `extract_outcomes`). Either list only the built steps, or say in the planner prompt which are not built yet. Add a test that every allowed step has a node in the graph | `agent/plan_check.py` (`STEPS_BY_FILES`), `prompts/planner.py` (`STEP_MEANINGS`) | 25.6: the D74 planner listed three steps nobody runs | the new test; read the plan of one run |
| R19 | The report instruction: every statement about A or about B needs a quote from that file (R9 only covers the matched lines of B). In D74 the report said A "keeps embeddings frozen" while A unfreezes at epoch 3, so its first cause was partly a misreading | `prompts/answer.py` (`TWO_FILES`) | 25.6 fault 3 | D74 re-run read by hand; citations that resolve |
| R20 | **The parts that the claim checks found must reach the report writer.** Today a `Finding` carries one quote and a header, and the writer sees only the 10 parts of the plain pile. The design (21.1 step 9, D42) says the chunks of the claim searches are merged into the pile with duplicates removed and the budget kept. This was never built | `agent/respond.py` or a merge step after `check_one`, `agent/finding.py`, `api/prompting.py` (`checks_text`) | 25.6: 7 of 10 countable misses never reached the writer | D74 re-run: how many of the absent findings now have their code in the prompt; a test that the deciding part of a finding is in the prompt once |
| R21 | When the pair fits and is read whole, the claim checks could read the stuffed parts and skip the embedder and the database search (fewer failure points, nothing wasted). An idea to test, not a decision | `agent/graph.py` (`after_search`, `fan_out_claims`), `agent/check_one.py` | the checks search B even when all of B is already in the prompt | grid arm E2 and E5 below |
| R22 | Put the impact column into `data/samples/quora_siamese/EXPECTED.md` (the proposal is in 25.6 and in `artifacts/slice7-review/impact_column_proposal.md`). **Read `scripts/answers/score_answers.py` and `scripts/retrieval/score_topn.py` first: they read this file and must not break** | `data/samples/quora_siamese/EXPECTED.md` | the score of 25.6 needs it to be repeatable | run both scripts before and after |
| R23 | How many parts the writer sees on the search path. `RERANK_TOP_N = 10`, `VECTOR_TOP_N = 15` and `RERANK_WINDOW = 20` per side were set on retrieval measurements, never on report quality; in D74 the writer saw 10 of 82 parts of B. The "how many to send" question of Step 1 is still open | `api/searching.py` | 25.6 | grid arm: 10 against 20 against 40 per side, search path forced |
| R24 | The group size and the wording of R1 are open: 1, 3 and 9 parts for each call; groups plus wording E; sizes between 2K and 4K. The harness takes the size: `python run_m10c.py MODEL REPS GROUP`. Count the cost in calls and seconds for each size, and read G31, G32 and G33 each time | `harness/run_m10c.py`, `harness/extract.py` | the three story facts of the key | the same score with the key (`harness/gold.py`), read by hand |

Also open and unchanged: R10 (the question embed has no wait on a 429; `search_one` has no retry when the pooled connection dies), R13 (the cause-finding step, to design together), R14 (log the planner's queries), R16 (the pool), R11 (slice 14 keeps Jev), R12 (slice 12 needs ranking). Optional measurements left from 23.8: M19 (claims on real prose, partly answered by M11), M22 (a second corpus), M23 (the Gemini 3.6 and OrcaRouter cells).

**C. The experiment grid for the stuffed approach (the user's plan for the next session).** Each cell is a `harness/run_d74.py` run, scored by reading with the impact column; run each cell twice if quota allows, because the model does not repeat itself. Cost of one run: about 3 to 5 minutes and about 20 to 40 model calls, one of them the report on tier 1.

| cell | path | claims | code state |
|---|---|---|---|
| E0 | search forced (budget 20,000) | on | today (done once: judged 5, surfaced 2, absent 12); repeat once for the noise |
| E1 | stuffed (the default budget of 30,000: the pair is read whole) | on | today, with the patches of 25.10 |
| E2 | stuffed | OFF (plan without `extract_claims`) | what the claim path adds when the model sees all the code |
| E3 | search forced | on | after R1 to R6 |
| E4 | search forced | on | E3 plus R17, R19, R20 and R9 |
| E5 | stuffed | on | after R1 to R6, R9, R19 (and R21 if it is built) |

**D. The order** (each step ends with tests green, a break of each new invariant, `ruff check .` and `ruff format --check .`, and the docs updated in both files):

0. Close slice 7: type the patches of 25.10 (R15, and R5 for the stray `+`), paste the tests, commit the docs (DETAILS.md first).
1. Baselines first: E0 (repeat), E1, E2. Read, score, write the table. This is the stuffed approach and it decides how much the claim path is worth when the model sees everything.
2. Claims (R1 to R5, R24). Measure the group size and the wording with the harness BEFORE building. Building R1 is a fourth lesson of slice 7: ask the user first.
3. Checks: R6 (the quote guard keeps a valid verdict), R8 (defined is not used), R7 and R17 (the query writer), R10 (embed wait, connection retry), R16 (the pool). Check with `run_m24_arms.py` and the hard rows G25, G30, G31, G32.
4. Report: R9 and R19 (instruction), R20 (the parts of the findings reach the writer), R23 (how many parts), R14 (log the planner's queries).
5. Causes: design R13 together (talk first, no code). It must reach #11, #12, #14, #17 and #18, which no claim from A can; relate it to slice 9 (`find_missing`, `find_bugs`) and slice 10 (the results part of the answer instruction, for #10b; see section 31). Decide R18 and R21 here.
6. Re-run E3, E4, E5. R22 (the impact column) before the first scored run. Closing review, docs, continue-prompt.

**E. What the next session must not do.** Do not change two things between two measured runs. Do not trust the regex screen of `gold.py` alone (read the claims, as in 25.11 A). Do not decide anything from one pair and one run: this fixture may reject, it never confirms. Do not build R1 before the user agrees to a fourth lesson.

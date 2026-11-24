# Section 27: the 22 decisions, and the rules for slice 13

[Docs home](../README.md)

### 27. SLICE 7 — THE 22 DECISIONS OF THE LATE NIGHT OF 2026-10-24, WITH THEIR REASONS (written 2026-10-28)

*This section is a reference. It lists the 22 changes that section 26 built (17 commits of `labpilot/` from `c365e9d` to HEAD), one decision each: what the program does now, why, where it is in the code, and what is still open. Every number is copied from sections 25 and 26, where the measurements are. It was written after the user asked Claude to explain all the code line by line in the chat (2026-10-28), and the explanations were NOT copied here: read the code and the functions named below. Later slices should change a decision HERE (add a line "changed in slice N") and not in a new place. Nothing in the repository changed when this section was written.*

**The result at the end of slice 7 (one pair, `quora_siamese`, so a fixture that may reject and never confirm; a gap under about 6 of 39 is noise, 26.1).** Weighted findings the report judges, of 39: D74 baseline 13 (search path, old code); search path after the changes 29 to 31, one repeat 23; stuffed path without claims and scan 30 in 36 s. The claim check over 32 hand-made claims: 27.2 of 32 (lesson 3) to 30 of 32, with 11 and 12 of 12 mismatches found. Details: 26.2, 26.3.

#### Part 1 — claims, checks and the scan of B

| # | decision | why (numbers from 25 and 26) | where | open / to improve |
|---|---|---|---|---|
| 1 | Read A in groups of about 2,000 tokens, one `list_claims` call for each group, all at the same time. A part is never cut | One call over the whole of A reached 2.8 to 3.2 of 12 mismatch facts. Two calls of about 2,000 tokens reached 9.3, for 8 of 8 models (25.2, 25.3). Wording E in groups: 10.7 of 12 (26.5, I1) | `prompts/claims.py` (`CLAIMS_GROUP_TOKENS`, `groups_of`), `api/claims.py` | M27: the group size is not settled (2K and 2.9K are inside the noise). 4K to 8K never tried on real papers |
| 2 | Join the groups round-robin (the best claim of each group, then the second best). At most 48 method claims. A whole answer is not rejected for too many claims | The cap is not the lever: cap 15, 20 and none were within noise (25.2). The real limit is cost: 44 claims is about 70 model calls for one question (25.11) | `agent/claims_schema.py`, `api/claims.py` | choose the cap from the measured cost; the cap of 48 is a first guess |
| 3 | The user's question is NOT in the claims instruction | A narrow question shrank the list from 12.2 to 5.5 claims (25.2) | `prompts/claims.py` (`build_claims_prompt`) | - |
| 4 | Every claim has a kind: `method` or `result`. Only method claims are checked. Result claims are kept for the answer | In D74, 6 of 10 claims were results or ablation rows, and their checks were noise or "absent" (25.6, R4) | `agent/claim.py` (`METHOD`), `agent/fan_out_claims.py` | the answer instruction handles results (section 31; `extract_outcomes` was withdrawn on 2026-11-12) |
| 5 | A search that fails for ONE claim leaves only that claim `unchecked`. The question's own search still stops the answer | One failed claim search lost the whole answer (D-1, 25.10). Three database tests failed on the old code | `api/asking.py` (`search_claim`, `CheckError`), `agent/check_one.py` | - |
| 6 | A verdict whose quote is not found in the part is KEPT: the quote is emptied and marked, and the part is saved as evidence | The strict rule left claims `unchecked` in every pinned run (2 of 32, 25.11 R6) | `agent/check_schema.py` (`read_finding`), `agent/_quote.py` | - |
| 7 | Whole-file facts for the checker: functions defined and never called. CHECK v3: such a fact is a mismatch (kind: mistake). Names a framework calls by itself (`forward`) are left out | `G30` (the class weight, #6) was a false MATCH in every arm of 25.5. After the fixed reader (6c43d82) and CHECK v3: 30 and 30 of 32, 11 and 12 of 12 mismatches, no false match (26.3) | `api/file_facts.py` (`FileFacts`), `prompts/checks.py` | negative claims ("no layer norm is applied", `G20`) were `unchecked`; CHECK v4 (26.12) fixes it on this pair, 31 of 32 in two runs. Only more pairs can show if it is general (27.1) |
| 8 | Go to definition: when the found code only USES a setting, add the part that SETS it | The wired arm found 9 of 12 mismatches, against 7.8 before (26.5, I4) | `FileFacts.expand` | - |
| 9 | The new-query writer sees the outline of B, keeps the topic words of the claim, and puts no number in the query | Retry queries guessed names that are not in B (25.4, R17). The gain inside the wired arm was about +0.5 of 32, noise on this pair (26.5, I3) | `prompts/requery.py`, `api/requery.py` (`make_query_writer`) | - |
| 10 | The `find_missing` step: B is read in groups beside A and the model lists what B does differently or what A never says. Never-called functions are added after, from the whole file | The scan alone reached 12 of 19 code facts (S2) with 16 to 18 items that match nothing out of about 34 (26.5). It never raised the score on this pair (26.2, point 4) | `agent/find_missing.py`, `agent/code_finding.py`, `agent/code_schema.py`, `api/differences.py` | **A DEMO VERSION: redesign and tune it in slice 9 (D77, 26.10).** A is sent whole beside every group |
| 11 | The planner may list only steps a node runs: 0 files none, 1 file `summarize`, 2 files `summarize`, `extract_claims`, `find_missing`. A plan with another step is rejected and the next tier writes a new one | The planner listed `find_bugs` and `extract_outcomes` on every run of 2026-10-24 and nothing ran them (25.6, R18) | `agent/plan_check.py` (`STEPS_BY_FILES`), `prompts/planner.py` (`STEP_MEANINGS`) | add `find_bugs` (slice 9) and `extract_outcomes` (slice 10) to the table when their nodes exist |

#### Part 2 — the report and its reliability

| # | decision | why | where | open / to improve |
|---|---|---|---|---|
| 12 | A small A (up to `A_WHOLE_TOKENS` = 10,000 tokens) is read whole when the pair does not fit and B is searched. Only side A. This is not the stuff node: the stuff node reads BOTH sides, and runs when the pair fits | The writer saw 10 of 18 parts of A in D74 (25.6). At a 30K budget the coverage is the same as searching A (26.4, I6) | `agent/merge.py`, `api/asking.py` (`whole_side`) | `A_WHOLE_TOKENS` (10,000) and `CLAIMS_BUDGET` (28,000) are different limits for different jobs and do not match (26.10) |
| 13 | After the rerank the best parts (10, or 15 when no reranker answered) come first and the rest of the pile follows, so the budget decides how many are sent | Cutting at 10 sent about 9,000 tokens of 30,000. Coverage of 39 at 30K: top 10 gave 9 to 10 without findings, filling the budget 34 to 39 (26.4, R23) | `api/searching.py` (`rank_pile`) | rerank window 50 or no rerank changed nothing on this pair (small B, 77 to 80 of 82 parts come back). Re-run `run_r23.py` on a big pair in slice 12 |
| 14 | The parts that decided a finding reach the writer. Missing ones are added at the END of the parts list, so no citation id shifts. On the search path they also come first for the cut for room | 7 of 10 countable misses never reached the writer in D74 (25.6). Putting parts in front moved the ids and only 8 of 19 citations resolved; after cb34dbc 80% to 98% (26.2) | `agent/respond.py` (`deciding_parts`, `with_parts`), `api/prompting.py` | - |
| 15 | The finding lines (checks and code findings) get at most 25% of the budget, most telling first. The least telling lines are dropped and counted. On the stuffed path the parts are counted first and the lines get the room left | 48 check lines and 33 code lines were more than a 12,000 budget and the answer was refused. On a stuffed run they cut B from 82 to 65 parts; parts first: 82 parts and 59 lines (048c65d). 10% looked the same at 30K (26.4) | `api/prompting.py` (`prior_text`, `PRIOR_SHARE`, `PRIOR_LABEL_TOKENS`) | the effect of 10% on a report was not measured |
| 16 | When everything was read (stuffed path, `totals` is `None`), the graph goes straight to `respond`: no claims, no checks, no scan | Stuffed answer alone 30 of 39 in 36 s (E2n); with claims and scan 26 to 29 in 181 to 244 s (26.2) | `agent/graph.py` (`after_search`), commit eee0a70 | measured on one pair read whole at about 29,000 tokens; larger files read whole were not measured. 25.11 R21 means another idea (checks reading the stuffed parts), not built |
| 17 | The report instruction for two files: every `[mismatch]`, `[B differs]` or `[A silent]` line that can change the result must appear in DIFFERENCES or in one line saying why it is not a cause. "Match" only with a quote from each | D74 dropped the weight decay mismatch and said label smoothing was "present on both sides" (25.6, R9, R19) | `prompts/answer.py` (`TWO_FILES`) | the effect of these two sentences alone was not measured |
| 18 | The log line of the planner prints the text of every query with its side | In D74 the log kept only the number of queries (25.6, R14) | `api/planning.py` | - |
| 19 | A search embeds its query BEFORE it takes a pooled connection, and hands the vector to the search. A query embed that gets 429, 500, 502, 503 or no answer at all waits 2 s, then 5 s (or the provider's wait, at most 10 s) and tries up to 3 times | A Mistral 429 `backend_out_of_capacity` and a 10 s read timeout each lost a whole answer on 2026-10-24 (R10). The pool has 8 connections (R16, read from the code, not measured) | `api/asking.py` (`search_one`), `api/searching.py` (`embed_query`, `_embed_with_waits`, `EMBED_WAITS`) | a cache of query vectors is not planned and was not measured |
| 20 | A search that meets a dead pooled connection runs once more on another one (2 tries, no wait) | `SSL SYSCALL EOF` lost an answer on 2026-10-24 (R10) | `api/asking.py` (`search_one`) | - |
| 21 | The chat is saved and pruned through the pool, not through the request connection. `CodeFinding` is on the list of saved classes | A connection idle during a 7.5-minute report was closed by the server on 2026-10-25 and the answer would have been lost at the save (2a1c036) | `api/asking.py` (`_saving_place`), `api/checkpoints.py` (`open_saver`, `prune`, `SAVED_TYPES`) | - |
| 22 | The Cline tiers (tier 1) think at `"medium"` and not `"high"` | On the stuffed report `"high"` thought 29,182 tokens, took 547 s and was cut at 32,000. `"medium"` thought 2,490 tokens and finished in 78 s; `"low"` 2,084 tokens, 74 s. Both scored like the cut report (22285a1, 26.2) | `llm/registry.py` (`CLINE_REASONING`) | `MISTRAL_REASONING` and `OPENROUTER_REASONING` are still `"high"`; nobody checked them |

**What this section does NOT contain.** The D74 re-run with all changes in place at a big B, the claims group size (M27), Jev inside the graph (slice 14), `find_bugs` (slice 9), the results measurement of slice 10 (section 31) and the ranking of claims of a big A (slice 12) are not done. The open items are in 26.9 and in the last column above.

#### 27.1 FOR SLICE 13 (the user's rule, 2026-10-28): every decision must be shown to work on MANY cases, not on `quora_siamese` alone

**The rule, in the user's words made precise.** Many decisions above are good in general: reading A in small groups, keeping a verdict whose quote is not found, the order of the ids, the share of the budget. But some were found by looking at ONE pair (`quora_siamese`), its answer key (`EXPECTED.md`, the 19 findings) and 32 claims that one person wrote for it. A decision made that way can be right for this pair and wrong or useless for the next one. So slice 13 has TWO jobs, and the second is as important as the first:

1. **Check:** does each decision of section 27 still work on many different pairs?
2. **Generalize:** where a decision only fits our pair, find a solution that covers many cases, and change the decision, the numbers or the algorithm for that. A special case is not a solution.

**The danger, stated plainly.** Every number in section 26 comes from one paper, one code file, one key and about 3 runs for each cell. We read the key while we tuned. That is close to writing the prompt from the answer key, which the project forbids (the comparison template section: the key may be used to SCORE, never to WRITE). A gap under about 6 of 39 is noise (26.1). So a higher score on this pair is a reason to look, not a proof.

**Which decisions I (Claude) think are general, and which may be special.** This is my reading of the code and of 25 and 26. It is NOT a measurement, and slice 13 must settle it.

| group | decisions | why I think so |
|---|---|---|
| General in the idea (the problem is not tied to our pair) | 1 groups, 2 join, 3 no question, 5 failed search, 6 keep verdict, 13 full budget, 14 evidence and ids, 15 share of lines, 18 log, 19 embed first and wait, 20 retry, 21 save through the pool | They fix a mechanism: attention over a long input, one failure that kills an answer, ids that shift, a connection that dies. The infrastructure ones (19, 20, 21) were seen in real runs and do not depend on the files. Even these have a number that came from one pair (2,000 tokens, 48, 25%, 2 s and 5 s) |
| May be special to our pair or to Python and machine learning | 4 method or result, 7 never-called functions and CHECK v3, 8 go to definition, 9 outline for the query writer, 10 the scan, 11 the list of steps, 12 A read whole, 16 answer at once, 17 the report sentences, 22 `"medium"` | 7 was shaped by `G30`, the unused `pos_class_weight`, a finding that is in our key, and its reader looks for Python `def` lines and a list of names a framework calls (`forward`). 4 and 17 follow the faults of the D74 report (results rows, weight decay, label smoothing). 16 and 12 were measured on one pair read nearly whole (about 29,000 tokens, A of about 4,300). 22 is one tier on one prompt. 10 is already marked a demo (D77) |

**What slice 13 must do.**
- **Many pairs.** Build a set that is not one pair: a paper with code, code against code, a big repository as A or B (the new pair of slice 12), a language other than Python (Go was used only for claims, M11), a field other than machine learning, a pair with no divergence, and a pair that does not correspond. Several answer keys, each with the impact column (R22). Write each key BEFORE the runs, and never change a prompt after reading a key.
- **Tune on some, test on others.** Keep a held-out set that nobody reads while tuning. A decision passes only on the held-out pairs.
- **One decision at a time.** Switch each decision off (an ablation) and measure the report. Report the result for EACH pair, not only the mean, with the denominator beside every ratio (the project rule from slice 8).
- **Noise.** Several runs for each cell, at least 5 for the cells that decide (M27). Several tiers, because the chain falls back. Name the corpus and the tier beside every number.
- **Keep, change or remove.** Keep a decision that helps on most pairs and hurts on none. If it helps on only one pair, do not keep it as it is: replace it with a general mechanism, or remove it. Example to examine: decision 7 finds "defined and never called" by reading Python `def` lines. The general problem is "code that B defines or sets and the run never uses". A general solution may be a language-neutral static check, or the `find_bugs` step of slice 9, and not a list of names.
- **Numbers too.** Every constant of section 27 (2,000, 48, 10,000, 6 parts, 2 retries, 25%, 300 characters, 2 s and 5 s, `"medium"`) is a first guess. Sweep each on the many pairs and choose from the sweep, or make it depend on the size of the input.
- **New algorithms are allowed.** If many pairs show that a whole step is weak (the scan is the first suspect, D77), plan a new algorithm for it. The goal is a system that works on repositories we have not seen.

**Where this joins other work.** M6 (a findings score on the search path), M18 (the instructions, on more data), M27 (the group size), M22 (a second corpus), D74 (the small baseline after each slice), the new pair of slice 12, and slice 14 (Jev). Slice 13 should run them on the same set of pairs, so that the results can be compared.

**A second case where this rule was broken (2026-11-12).** The slice 10 plan (`extract_outcomes`, "comparable?", "does it add up?") was built on the one trap of the quora pair. The user caught it: many inputs have no results at all (a repository, a script, LabPilot's own code, a pair outside machine learning), and the answer instruction and the `result` claims already cover most of it. The nodes were withdrawn (D108) and the work was replaced by a measurement first (section 31). **The check before designing a node: does the problem appear in other kinds of pair, and does something already cover it?**

**Clarification of 27.1 (the user, 2026-10-28).** The aim is NOT to drop the decisions. Most of them (smaller groups, the retry on a dead connection, keeping a verdict whose quote is not found, and others) are expected to work on other pairs and to stay. Slice 13 measures to CONFIRM them, and to find the few that do not work. **The numbers are the largest risk:** a number can be the best one for `quora_siamese` and a poor one for other pairs. Each number is a first guess until it is swept on many pairs: the group size (2,000), the cap (48), the share of the budget (25%), the number of parts for a check (6), the retries (2), the waits (2 s and 5 s), the 300-character line, and the size limits below.

**Three size limits that are linked and not settled (to design together in slice 13 and slice 12):**
1. `CLAIMS_BUDGET` = 28,000 tokens: the most of A that the claims step reads. Above it, no claims are made (D65). Slice 12 plans to raise it with a total budget of about 90K tokens for a big A, cut into parts and joined (D68, D69; the 90K is a first guess, M12).
2. `A_WHOLE_TOKENS` = 10,000 tokens: the largest A that is read whole on the search path (decision 12) and put beside every group of B in the scan (decision 10). It is a different number from the 28,000 for the same A, and nothing ties them.
3. The algorithm that reads A whole: it only checks the size of A. Slice 13 should measure on many pairs whether 10,000 is a good limit, whether the two limits should be one, and whether a bigger A should be read in another way (for example only the parts near the question, or a summary) and not be dropped.

#### 27.2 FOR SLICE 13 (the user's rule, 2026-11-10): tune every number that is still a guess

**The rule.** LabPilot has many numbers that decide how much is read, how it is cut, how many calls run and how much goes into a prompt. Most of them are **our first guess**, or were measured on **one pair** (`quora_siamese`) or on the three cases of slice 9. They were never swept to find the best value. A number can be the best one for our pair and a poor one for others (27.1). **Slice 13 tunes them**: for each number, try several values on MANY pairs, on held-out pairs too, with several runs a cell, and choose from the results. Count quality (findings, claims, coverage, faults read by hand), seconds and calls. A number may also become a value that DEPENDS on the input size or the model, if one fixed value cannot fit all cases.

**How to tune.** One number at a time; the others stay fixed. Name the pair, the tier and the denominator beside every result. Numbers that are linked (the three size limits of 27.1, and the rerank window with the top N) are tuned together. Choose by the worst pair, not only by the mean.

**The numbers** (the value today, where it lives, and what is known about it). "Guess" means never measured. "One pair" or "three cases" means measured on that only, so it is still a candidate.

| group | number | today | where | known |
|---|---|---|---|---|
| what is read whole | `A_WHOLE_TOKENS` | 10,000 | `prompts/builder.py` | guess (decision 12, 26.10) |
| | `CLAIMS_BUDGET` | 28,000 | `prompts/claims.py` | guess (D68 was a proxy) |
| | `SCAN_A_TEXT_TOKENS` | 20,000 | `prompts/scan.py` | three cases (29.2) |
| | `SUMMARY_BUDGET` | 12,000 | `prompts/summary.py` | from Gemma's minute limit, not tuned (D46) |
| | `SUMMARY_READ_SECONDS`, `SUMMARY_TOTAL_SECONDS` | 60, 120 | `api/summaries.py` | guess (D110); the time one model and the whole call may take for a summary or a gate |
| | `DIFFERENCES_READ_TOKENS`, `BUGS_SCAN_TOKENS` | 40,000 | `prompts/audit.py`, `prompts/bugs.py` | guess (owed to slice 12, 29.8) |
| prompt budget | `PROMPT_BUDGET` | 30,000 | `prompts/builder.py` | a decision (D61), not tuned |
| | `PROMPT_EXTRAS_TOKENS` | 2,000 | `prompts/builder.py` | guess |
| | `PRIOR_SHARE` | 0.25 | `api/prompting.py` | one pair: 10% looked the same at 30K (26.4) |
| | `PRIOR_LABEL_TOKENS` | 200 | `api/prompting.py` | guess |
| | `OUTLINE_BUDGET` | 4,000 | `prompts/context.py` | guess |
| | `FILE_ROW_TOKENS` | 24 | `prompts/context.py` | measured on our own repository (D61) |
| | `PLANNER_BUDGET` | 12,000 | `prompts/corpus_map.py` | from Gemma's limit; M5 sweeps it |
| | `REPORT_MAX_TOKENS` | 32,000 | `prompts/builder.py` | measured to finish at MEDIUM thinking |
| group sizes | `CLAIMS_GROUP_TOKENS` | 2,000 | `prompts/claims.py` | one paper; 2K and 2.9K are within noise (M27) |
| | `SCAN_GROUP_TOKENS`, `TRACE_GROUP_TOKENS` | 2,000 | `prompts/scan.py`, `prompts/bugs.py` | taken from the claims, not measured for these jobs |
| | `AUDIT_GROUP_TOKENS`, `WHOLE_GROUP_TOKENS` | 24,000 | `prompts/audit.py`, `prompts/bugs.py` | guess (29.8) |
| | `SKEPTIC_TOKENS` | 30,000 | `prompts/bugs.py` | guess |
| counts and caps | `MAX_CLAIMS` (REMOVED 2026-11-24, D140) | 48 | `agent/claims_schema.py` | guess, from the cost (25.11) |
| | `MAX_QUERIES` | 6 | `agent/plan_check.py` | guess (D54, M5) |
| | `AUDIT_BATCH`, `JUDGE_BATCH`, `SKEPTIC_BATCH` | 30, 30, 25 | `prompts/audit.py`, `prompts/review.py`, `prompts/bugs.py` | guess |
| | `AUDIT_VOTES`, `JUDGE_VOTES`, `SKEPTIC_VOTES` | 2 | same files | three cases (29.8: 2 votes kept) |
| | `MAX_OBLIGATIONS`, `MAX_BUGS_PER_ANSWER` | 40 | `agent/checklist_schema.py`, `agent/bug_schema.py` | guess |
| | `CLAIMS_AT_ONCE`, `CALLS_AT_ONCE` | 4 | `api/claims.py`, `api/tool_calls.py` | guess (the provider limits of D70 are not modelled) |
| | `DEFAULT_MAX_REJECTED_ANSWERS` | 3 | `llm/defaults.py` | guess (D50) |
| search and rerank | `SEARCH_LIMIT` | 50 | `store/defaults.py` | slice 8 (20 corpora) |
| | `RERANK_WINDOW` | 20 | `api/searching.py` | for ONE query's pile; a merged pile was not measured (D53); 50 changed nothing on one pair (26.4) |
| | `RERANK_TOP_N`, `VECTOR_TOP_N` | 10, 15 | `rerank/defaults.py`, `api/searching.py` | retrieval measurements, never on report quality (R23) |
| | `SCORE_ALPHA` | 0.85 | `retrieval/fusion.py` | slice 8 (20 corpora) |
| | `SIDE_SHARE` | 0.5 | `retrieval/selector.py` | a rule, never swept |
| | `POOL_SIZE` | 8 | `store/defaults.py` | measured with `select 1` only (D55) |
| text cuts | `LINE_CHARS`, `MERGE_LINE_CHARS` | 300 | `api/finding_lines.py`, `agent/final_merge.py`, `api/difference_review.py` | guess |
| | `LAST_ANSWER_CHARS`, `RECENT_QUESTIONS`, `QUESTION_CHARS` | 2,000, 4, 300 | `prompts/followups.py` | guess (D104 changes this) |
| | `OPENING_CHARS` | 300 | `prompts/_hints.py` | guess (D52) |
| | `MIN_PIECE_CHARS` | 9 | `agent/_quote.py` | guess (D91) |
| waits | `EMBED_WAITS`, `MAX_EMBED_WAIT` | 2 s, 5 s; 10 s | `api/searching.py` | guess (decision 19) |
| | the time limits of D102 | 120 s / 300 s; 40 s / 150 s | `api/asking.py` | guess |

**Out of this list on purpose:** the chunk sizes (`CHUNK_SIZE`, `MAX_CHUNK_TOKENS`, ...), because a change there means re-chunking and re-embedding every stored artifact (decide only with a strong reason); limits a provider sets (Google's per-minute numbers, `MAX_DOCUMENTS`); and the size and safety limits of uploads (`MAX_UPLOAD_BYTES`, `MAX_FILE_BYTES`, ...), which are safety rules and not quality knobs. `INPUT_BUDGET` (20,000, `retrieval/selector.py`) is an old default that nothing uses (17.18): delete it, do not tune it.

**Before slice 13:** when a new number is added in slices 10 to 12, add it to this table the same day.

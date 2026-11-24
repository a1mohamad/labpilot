# Section 29.1 to 29.9: slice 9, differences and bugs

[Docs home](../README.md)

### 29. SLICE 9 — find_missing and find_bugs, measured on three cases before any lesson — 2026-10-31 to 11-01

*The user asked for the two nodes to be designed from measurement, on three different cases and not on `quora_siamese` alone, with the approaches professional tools use, and with low cost and low waiting time. Exit AS58212 dataforest, Frankfurt, Google 200 before each batch. Everything ran in a scratch copy and in `artifacts/slice9-study/` (git-ignored): `RESULTS.md`, `keys.py` (the answer keys, written before the runs), `fb_gold.py` (my labels of the pooled bug suspects), the harness and `results/*.jsonl`. One fixture set may reject, never confirm (27.1): every number below is three cases and 1 to 4 runs a cell.*

#### 29.1 The three cases

| case | A | B | kind |
|---|---|---|---|
| quora | `A_paper.md` (4.3K tokens) | `B_train.py` (19K) | the existing fixture |
| adam | the Adam paper, PDF, arXiv 1412.6980 (16K) | PyTorch `torch/optim/adam.py` at v2.5.1 (12.5K), with 4 bugs put in (X1-X4) | a real paper and real library code |
| otp | RFC 4226 sections 1-7 and RFC 6238 (21K) | `pquerna/otp` v1.4.0, three Go files (6.4K), with 4 bugs put in (Y1-Y4) | a real standard and a real Go repository |

**A correction to the key, made after the first runs and written down in `keys.py`:** the quora paper STATES that attention excludes padding "and nothing else" and gives `r` with four parts, so the stopword mask, the punctuation and `<UNK>` mask and the cosine feature are "B differs" items, not "A silent" ones; the vocabulary cap, the empty-row drop and the layer norms agree with A. In the otp case RFC 4226 allows 7 digits, so the digit coercion is a difference too.

#### 29.2 find_missing: four approaches

| approach | what it does | result |
|---|---|---|
| **S, search only** | every line (or part) of B searched in A by vector and BM25; the least similar are "A silent" | **at or below chance on all three cases.** The most "silent" lines are plumbing (file writing, URL building). Search can tell that A never talks about a line, not whether the line matters. No model call can be saved this way |
| **C, claims** | the list of A's claims beside each 2K group of B | silent items: adam 5/5, otp 3-5/5; 3-7 items a run that A already states, because the claims list is incomplete |
| **D0, today's scan** | all of A beside each group | good on "differs", weak on silent (otp 2/5); 2.4-4.3 times the input tokens; calls of 18-24K tokens overflow Gemma's room |
| **CR, claims + the nearest parts of A** (the combination) | the claims list, the 3 parts of A nearest to the group's parts, kinds "silent" and "differs" with a fact number | **best: silent 9 of 10 (adam and otp), differs about 7 of 9, items A already states 0-2 a run, about 18 s, 5-8K tokens a call** |
| CS, a search check after the call | relabel an item "A may mention this" when search finds a close part of A | the score separates (AUC 0.77-0.82) but every threshold moves a third to a half of the good silent items; not used |

Also measured: one search per GROUP of B is a little weaker than one per part (otp silent 2-3/5 against 4/5); the product finds the nearest A part of every B part with ONE SQL query over the stored vectors, so it costs no embedding call. Merging repeats by topic alone lost an item (adam: "weight decay" was a silent default AND a sign that differs), so the key is the kind plus the topic: 22 items became 13-14 with no key item lost.

#### 29.3 find_bugs: shapes, models, skeptic

- **The model matters most.** Flash-Lite finds 1-2 easy bugs a case whatever the prompt; "list every suspect" did not help it.
- **Three questions, as the professional tools ask** (small units, a focused question each, then a check):
  - **trace**, one call per 2K group with the file's summary: what is it meant to compute, compare it term by term with the standard form, run the first call and edge inputs in your head, check that settings take effect. Gemini 3.6 Flash: adam 3/4 and otp 3/4, including the RFC truncation mask no other arm found.
  - **method and numbers**, over the whole file: data used twice, tuning on the reported data, one seed; read every block of numbers. GLM-5.3: the threshold tuned on validation, no test set, one seed, the 12-point train/validation gap and the unused class weight, in one 37 s call.
  - **concept**, over the whole file with the summary: a choice an expert of the field knows is wrong or unsafe, though the code runs. Added on 2026-11-01 at the user's request, with its own key written first. GLM-5.3 found both quora concept bugs (masking "what", "how", "why"; masking every unknown word) and on otp the short secret and the timing-leak comparison (and MD5 on the per-part run). Nobody found "a code can be used twice" or the AdamW weight-decay pitfall. Flash-Lite found 0-2.
- **The skeptic.** One Flash-Lite call per file with the whole file and all suspects (10-40 s); strong models as skeptics timed out. Its first wording threw away method and numbers bugs as "common practice"; the fixed wording says method, numbers and concept defects are real even when the code runs. One vote was unstable (11 to 16 of 17 real kept over four runs). **Two votes at the same time, and a suspect dropped only when both say false or intended: 16 of 17 real kept in both pairs, 17-21 of 28 false removed.** On the concept suspects it kept 10 of 10.
- **Whole pipelines after the skeptic** (real defects of the 17 in the labelled pool): Flash-Lite hunters 6; GLM 10; Gemini 3.6 trace + GLM method 12; GLM and Gemini 3.6 together 14; 1-5 false left.

#### 29.4 Decisions

| # | decision |
|---|---|
| **D84** | **find_missing is CR.** One call for each group of about 2,000 tokens of B, at most 4 at once, with the WHOLE list of A's claims and the `NEAR_A_PARTS = 3` nearest parts of A, which `store.nearest_parts` reads from the stored vectors in one query. Kinds "silent" and "differs" (with a fact number; `a_says` is that claim's text, or "A states it otherwise"). A is never put beside B whole any more, so the scan has no size limit on A. Repeats are merged by (kind, topic). Two embedders, or a dropped connection, stop the scan and not the answer. `DIFFERENCES_VERSION` 2 |
| **D85** | **The claims list is kept whole.** `join_claims` no longer caps it; `fan_out_claims` checks only the first `MAX_CLAIMS = 48` method claims, the same ones as before, and the scan reads every claim. The scan runs after the claims (it needs them) |
| **D86** | **The never-called findings of the old scan are removed** (26.10, the user's view: an unused function is rarely the cause). `FileFacts` still serves the checker |
| **D87** | **find_bugs reads one file alone**: B when there are two, else the file there is. Three hunter questions (trace per 2K group with the summary; method and numbers, and concept, over the whole file in groups of 24K, concept with the summary), all at once, on the FULL chain (strong models first); suspects with an invented quote are dropped; repeats on one line are merged. Then the skeptic on the cheap chain: `SKEPTIC_VOTES = 2` at once, whole file when it is at most 30K tokens, else the suspects' own parts; a suspect is dropped only when every vote answered and every one says false or intended; one "real" makes it real; a lost or split vote keeps it as "unclear"; no vote keeps it "unchecked". `BUGS_VERSION` 1 |
| **D88** | **find_bugs runs on the stuffed path too**, unlike the checks and the scan (R21): one call over a whole file found about half of what the hunt finds. It is allowed with one file and with two; `PLANNER_VERSION` 4 |
| **D89** | **The bugs reach the answer** as their own block (`[real - logic] ...`); a real high-severity bug ranks with the differences, the rest with the silent lines; the part of a real bug is shown first among the evidence. `Bug` is a saved type and is cleared after each message |

#### 29.5 Not settled

- Three cases only, 1-4 runs a cell, my own labels; slice 13 repeats it on many pairs (27.1).
- The strong models have small daily limits (Gemini 3.6 Flash 20 a day for each key); the hunt costs about one call per 2K of the file plus 2 whole-file calls plus 2 skeptic calls (quora: 9 + 2 + 2). An ensemble of two strong models found 14 of 17 against 10-12 for one: worth measuring again in slice 11 with the chains.
- The concept question misses replay and pitfalls that need outside knowledge of the field; a search of documentation (Step 2.5) may help. **Answered in 29.7: the checklist step finds replay in 3 of 3 runs, AdamW in 1 of 3.**
- find_bugs on a paper (one file that is a paper) was not measured.
- The group size (2,000), `NEAR_A_PARTS` (3), `WHOLE_GROUP_TOKENS` (24,000) and the caps are first values from three cases.

#### 29.6 Built and checked in a scratch copy (2026-11-01)

Both lessons were built in a scratch copy of the working tree, outside the repository, and handed to the user in `artifacts/slice9-lessons/` (git-ignored): `LESSON_1_find_missing.md`, `LESSON_2_find_bugs.md`, `SHARED_FILES.md` (the files both lessons change) and `tests/` (the test files to paste). The user types the product code.

- **Tests:** unit and api 1970 passed, 5 skipped. The whole suite with the database tests: 2150 passed, 139 skipped, 2 failed; one was an old integration test that pinned the old scan prompt (`test_claims_over_the_store.py`, its fake model answers the new shape now, 17 of 17 pass), the other a connection that Supabase closed mid-request (`SSL SYSCALL error: EOF`), which passed alone. `ruff check .` and `ruff format --check .` clean.
- **Deliberate breaks: 22, every one caught**, each on a kept copy of the file (`break_s9.py`): the nearest-part query sorted the wrong way, reading another artifact, two embedders allowed; no cap on the parts of A; the merge ignoring the kind; a "differs" item losing its fact; every claim checked; the scan getting no claims; repeats not merged; one vote throwing a bug out; a real vote not winning; one vote only; no hunt on the stuffed path; A hunted when there are two files; the skeptic always reading the whole file; the method question reading the summary; the bug merge ignoring the source; bugs not cleared; `Bug` not saved; no hunt with one file; the bugs never reaching the prompt; invented quotes kept.

#### 29.7 Concept bugs made findable: a checklist, then an audit (2026-11-01)

*The user's request after 29.6: two concept bugs (a one-time code that can be used again, and the AdamW weight-decay pitfall) were missed by every model and every prompt, and they matter; find out what professionals do, fix the concept finding, and keep the other parts as strong. Same exit, same three cases, same key (`CONCEPT` in `keys.py`, written before the first concept run: c1 and c2 quora, c3 adam, c4 to c7 otp).*

**What professionals do** (read from search results and paper pages; strength: method descriptions, no shared benchmark with ours). Tools that check code against a standard (RFCAudit, VSpector, and an industrial report on protocol code) do not ask "find a wrong idea". They first turn the standard and the known pitfalls into a list of small obligations ("the counter must not be accepted twice"), then check the code against each obligation, one by one. A reviewer who is asked an open question stops at the ideas it thinks of first; a reviewer who must answer every item of a checklist does not skip the item.

**Measured arms** (GLM-5.3 Flash; concept keys found, with the quote placed again where needed):

| arm | what it asks | concept keys found |
|---|---|---|
| CONCEPT question alone (29.3) | "a choice an expert knows is wrong", whole file | c1 c2 c4 c6, or c1 c4 c6 c7: about 4 of 7. Replay (c5) and AdamW (c3) never |
| OBLIG | a checklist from the summary and the headers, then "report only the rules it breaks" | otp c4 c5 c6 c7 once |
| OBLIG2 | the same, but "answer EVERY obligation by its number" | c5 found in 4 of 5 runs; c3 once |
| **OBLIG3** | **two checklists at the same time (the standards, and the known pitfalls of the method), then one audit that answers every obligation** | **otp 4 of 4 in 3 of 3 runs; AdamW in 1 of 3; quora 0 (the CONCEPT question covers c1 and c2)** |

With the CONCEPT question and OBLIG3 together, about 6 of 7 concept keys a run, against about 4 of 7 before. OBLIG3 costs 3 calls a file (two checklists of about 4 s at the same time, then one audit of 11 to 17 s for each 24K group), 14 to 47 s.

**The quote fix.** 19 suspects of these runs had a quote that is not in the part they named. Most were real: the model named the wrong part of the same call, or joined two lines with "...". Searching the other parts, then the first piece of the quote, placed 15 of the 19 again (the AdamW find and the short secret among them).

**The skeptic dropped the new finds.** With the rule of D87 (dropped when both votes say false or intended), the skeptic called the 10-byte secret, MD5 and the missing replay check "intended" (the code does them on purpose) and dropped 4 of the 5 concept keys of an OBLIG3 run. Two fixes were measured on the same pool:
- a skeptic that asks only "does the code break this rule, and does the rule apply?": it kept c4, c6 and c7 (c7 with one vote) and lost c3 and c5. Not chosen;
- **the rule chosen: a concept suspect is dropped only when every vote says "false" (a misreading); "intended" makes it "unclear", shown with the skeptic's reason.** It kept all 5 (c6 "real", the rest "unclear"). The labelled pool of 29.3 has no concept suspect, so its numbers do not move (16 of 17 real kept, 17 to 21 of 28 false removed). The price: about 6 of the 28 concept suspects of that run are weak (what a checkpoint saves, no git hash logged, the digits or the period not checked), and they now reach the answer as "unclear".

**Decisions:**

| # | decision |
|---|---|
| **D90** | **find_bugs gets a checklist step.** Two questions write the checklist an expert uses for this kind of work, at the same time, from the summary and the headers of the parts only (`STANDARDS`: 12 to 20 MUST and MUST NOT obligations; `PITFALLS`: 6 to 12 known pitfalls of the method and their known fixes). The two lists are merged (the same words are one obligation). Then `AUDIT` answers EVERY obligation by its number, for each 24K group: "no" (with the part and the quote), "yes" or "n/a". Each "no" is a suspect of kind concept, with the obligation in its text, and it goes to the same skeptic. The checklists are asked first and the hunts run while they are written; with no checklist there is no audit and the hunts still give their answer. On the full chain. `BUGS_VERSION` 2 |
| **D91** | **A quote is placed where it really is**: the named part first, then any part of the same call, then the first piece of the quote (split at "..." and at line ends, at least 9 characters). A quote that is in no part is still dropped as made up. Used by the hunters and the audit |
| **D92** | **A concept suspect is dropped only when every vote says false**; "intended" makes it "unclear". Every other kind keeps the rule of D87 |

**Built in the scratch copy and checked.** Unit and api: 2004 passed, 5 skipped (34 new tests: the checklist and audit readers, the quote placing, the drop rule, the prompts, the wiring with the fake client). The whole suite with the database tests: 2186 passed, 139 skipped, 0 failed (10 minutes). `ruff check .` and `ruff format --check .` clean. Deliberate breaks: 17, every one caught after one test was added (a "yes" that carries a part and a quote was read as a defect, and no test noticed; `test_a_rule_that_is_met_or_does_not_apply_is_not_a_defect` now does): intended dropping a concept suspect; the kind not looked at; every kind keeping an intended vote; only the named part searched; no piece of a quote tried; a tiny piece used; a "yes" or an "n/a" read as a defect; the obligation missing from the text; an audit that answers nothing accepted; the checklists not merged; the audit run with no checklist; one checklist only; a runaway checklist accepted; the checklist not reading the summary; the audit not seeing the code; an invented quote placed.

**The real product code, live** (the scratch copy's `make_bug_finder`, the full chain for the hunters and the cheap chain for the skeptic, the parts from the harness, no database; `fb_product.py`, `results/fb_product.jsonl`). For comparison, the three questions of 29.3 alone with GLM-5.3 and BEFORE the skeptic reached quora 18 of 21, adam 6 of 11 and otp 11 of 15 on the bug key, and concept c1 c2 / none / c4 c6.

| run | case | seconds | bugs shown | real / unclear | bug key | concept keys |
|---|---|---|---|---|---|---|
| 1 | quora | 711.6 | 47 | 46 / 1 | 18 of 21 | c1 c2 |
| 1 | adam | 49.2 | 12 | 11 / 1 | 11 of 11 (X1-X4) | none |
| 1 | otp | 40.5 | 22 | 17 / 5 | 15 of 15 | c4 c5 c6 c7 |
| 2 | quora | 72.9 | 44 | 42 / 2 | 19 of 21 | c1 c2 |
| 2 | adam | 51.7 | 10 | 9 / 1 | 11 of 11 | c3 |
| 2 | otp | 48.6 | 23 | 23 / 0 | 15 of 15 | c4 c5 c6 c7 |

**Concept keys: 6 of 7 and 7 of 7** (AdamW in run 2), against about 4 of 7 before; the bug key is as strong as before or stronger (adam 11 of 11 against 6 of 11, otp 15 of 15 against 11 of 15, quora 18-19 of 21 against 18). The 711.6 s of quora run 1 was a slow provider moment: the same file took 72.9 s an hour later, and the earlier harness measured the whole-file method call alone at 267 s on that file; the checklist step itself is 3 calls of 14 to 47 s that run while the hunts run. Not measured: how many of the shown bugs are false on these runs (the skeptic called nearly all of them "real"; the precision numbers stay those of the labelled pool, 29.3), and quora shows 44 to 47 bugs, which the answer prompt must rank.

**Still open.** AdamW (c3) is found in 1 of 3 runs only: the models see coupled L2 decay as normal Adam, and the key itself calls it borderline. The weak "unclear" concept lines make the answer longer; the answer prompt ranks them below the real ones. Three cases, my own labels; slice 13 repeats it (27.1).

#### 29.8 Cheaper trace, the smart cut and a 3-vote skeptic (2026-11-02)

*Asked by the user after 29.7: find_bugs costs about 16 calls for one file, and about 14 of them went to the strong models. Exit AS58212 dataforest, Frankfurt, Google 200. Harness `artifacts/slice9-study/trace_mid.py`, `trace_compare.py` and `sk3.py` (git-ignored); results `results/trace_mid.jsonl`, `results/fb_skeptic.jsonl`.*

**1. The trace question on a mid-level model (only trace was changed).** Same prompt, same 2K groups and summary as in 29.3. Scored with the bug key (`FB`, weights: quora 21, adam 11, otp 15, so 47 in all), alone and together with the strong whole-file calls (GLM-5.3: method, concept, checklist audit, from the saved runs). 2 runs a model.

| trace model | with the whole-file calls, run 1 / run 2 (of 47) | gain over the whole-file calls alone (41 / 44) | time a case |
|---|---|---|---|
| Gemini 3.6 Flash (strong, 1 old run) | 46 | +5 (X2, X3) | 92-190 s |
| **Gemini 3.1 Flash-Lite** | **44 / 47** | **+3 both runs** (X3 and q16) | **7-61 s** |
| DeepSeek V4 Flash (LiteRouter) | 43 / 44 | +2, then 0 | 67-341 s |
| Gemma 4 26B | 41 / 44 | 0 | 12-56 s |
| Ministral 14B | 41 / 44 | 0, and 15-27 suspects a run | 11-40 s |

- **The whole-file calls on the strong model find almost every key bug alone.** Trace adds only on adam (X2 and X3, two bugs put in by hand). Flash-Lite 3.1 found X3 in both runs and never X2.
- **Routes that failed, not a verdict on the model:** Qwen3.8 27B on Kilo (404, gone), Qwen3.8 27B on Groq (**a new fact: 1,000 OUTPUT tokens a minute**, "Request too large ... output tokens per minute (OTPM): Limit 1000"), GPT-OSS 120B on Cloudflare and on Groq (empty answers, timeouts), Nemotron 3 Super on Kilo (404).
- **Cost:** on quora the strong calls fall from about 14 of 16 to 5 of 16 (method, concept, the 2 checklists, the audit). Flash-Lite 3.1 has 500 calls a day on each of 3 keys.
- **Limits:** 3 cases, 2 runs, the regex screen of the key, the false suspects were not counted, and on a big file trace makes many more calls, so it may matter more there.

**2. A 3-vote skeptic.** Same `SKEPTIC` prompt on the saved labelled pool (74 suspects: 17 real, 28 false, the rest minor or unclear; whole file, 25 suspects a call). New jurors Flash-Lite 3.1 and Ministral 14B, 2 runs each; the old Flash-Lite 3.5 votes reused. Gemma was not tested: the whole quora file is bigger than its 16K input room.

| rule | real kept (of 17) | false removed (of 28) |
|---|---|---|
| **today: Flash-Lite 3.5 x2, dropped when both say false or intended** | **16** | **17** |
| 3 models (3.5 + 3.1 + Ministral 14B), majority | 14-17 | 15 |
| the same 3, dropped only when all 3 agree | 17 | 4-5 |
| Flash-Lite 3.5 x2 + Flash-Lite 3.1, majority | 16 | 18 |

One vote alone: Flash-Lite 3.5 removed 19 or 24 (and kept 16 or 11 real), Flash-Lite 3.1 14, Ministral 14B only 6. **A panel is only as good as its judges; the best 3-vote panel removed 1 more false bug, which is inside the noise. The 2 votes stay.**

**3. The cut, read from the code (`prompts/_groups.py`, `api/bugs.py`).** The words "whole file" in 29.3 and 29.4 mean groups of `WHOLE_GROUP_TOKENS`: the count of groups is the total divided by 24,000, ROUNDED (so 25K or 35K is one group, 37K two groups of about 18.5K), and the groups have equal shares. A part (a function, a class, a section) is never cut. But the code knew nothing about FILES:
- a group boundary could fall inside a file, so one file was split between two calls (with many tiny files, the one file on each boundary, for example `graph.py`);
- the read limit `BUGS_SCAN_TOKENS` (40,000) took parts until the next one did not fit, so the last file was read in part, and it chose files by their sorted path, not by meaning. LabPilot's own code (161 files, about 180K tokens) would be read for about 22%, with only a log line.

**Decisions:**

| # | decision |
|---|---|
| **D93** | **The trace question goes to a cheap chain led by Gemini 3.1 Flash-Lite** (`for_trace`, `TRACE_FIRST`). The method, concept, checklist and audit calls stay on the full chain. If the 3.1 keys fail, the chain falls back to the rest of the full chain |
| **D94** | **The smart cut: a file is not cut in the middle when it can be avoided.** (1) The big groups follow files: a group boundary that falls inside a file moves to the start or the end of that file, whichever is nearer, when the file fits in one group; a bigger file is cut between its parts, as before. 24,000 is a target, not a hard limit. (2) The read limit takes WHOLE files: a file that does not fit is skipped and the next file is tried; only when nothing was taken and the first file alone is bigger than the limit are its first parts read. The log says how many files were read and skipped. The trace groups (2K) still cut files on purpose, because trace looks inside one function. `groups_of(..., files=...)` and `whole_files` in `prompts/_groups.py` are shared, so the claims groups and the `find_missing` scan can use them later |
| **D95** | **The skeptic keeps 2 votes** (point 2 above) |

**Built and checked in the scratch copy (2026-11-02), handed over in `artifacts/slice9-lessons/` (lesson 2):** `api/chains.py` (`TRACE_FIRST`, `for_trace`), `prompts/_groups.py` (`groups_of(..., files=...)`, `whole_files`), `api/bugs.py` (a fourth argument `trace_client`; whole files up to the read limit; the big groups follow files), `api/asking.py` (`for_trace(client)`). 13 new tests (`test_groups.py` 9, `test_bugs.py` 3, `test_chains.py` 1). Whole suite with the database tests: 2199 passed, 139 skipped, 0 failed; `ruff` clean. 12 deliberate breaks, all caught after one test was fixed: its fixture had its plain cut on a file edge by luck, so breaks that dropped `files=` from the hunt and audit groups survived; the fixture now puts a file on the line.

**Owed to slice 12 (real measurements on a big repository):** the 40,000 read limit and how files are chosen (by the question, the outline and `file_scores`, not by name) and what the user is told ("12 of 161 files read"); the smart cut against the plain cut; the group size of 24,000; trace on Flash-Lite 3.1 on a big file (many more trace calls); merging method and concept into one call; whether the open concept question is still needed beside the audit; a 3-vote panel with a stronger judge.

#### 29.9 The redesign: one `find_differences` node, measured on blind cases — 2026-11-03

*Asked by the user after 29.8: every round had added prompt rules, steps and code; each gained a little on the three tuned cases and generalized poorly (hand labels of 2026-11-02: find_missing 175 lines, 65 right + 12 wrong label + 98 noise; find_bugs 130 lines, 53 real + 40 repeats + 25 minor + 14 false; on the new case ws find_missing about 4 of 10 useful lines). The user also asked to merge `extract_claims` + `check_one` + `find_missing` into one node; a GPT test (154 trials) agreed on one node but not on one request. All work ran in a scratch copy (`ledger.py`, `full.py`, `full3.py`, `base.py`, `diffonly.py` in the session scratchpad; data in `out/arms.jsonl`, `out/calls.jsonl`); summary in `artifacts/slice9-study/RESULTS_2026-11-03_redesign.md` (git-ignored). Every shown line was read by hand; the regex screen only sorted.*

**Research (sources and strength).** RFCAudit (arXiv 2506.00714, read): spec obligations checked one by one against code (conforms / bug / need more context, with retrieval tools); a missing check is just a violated obligation; its self-critic pass moved precision from 36.1% to 81.9% (68 of 83, Claude 3.5 Sonnet, about $5 a repository). SPECA (arXiv 2602.07513, read): MUST statements become a checklist; recall 27.3%. SciCoQA (arXiv 2601.12910, search summaries): the best models find about 47% of real paper-code discrepancies; omissions are the hardest. Cursor Bugbot V1 (third-party write-ups only, weak): several passes, keep what recurs, then a validator. ProtocolGuard: not readable.

**Blind cases.** A helper agent built two sets and wrote the keys BEFORE any run; a set was opened only after the design was frozen. Set 1 `artifacts/slice9-study/cases_holdout/`: b64 (RFC 4648 vs TypeScript), algo (xxHash spec vs Rust), c2c (CPython shlex vs a JavaScript port), clean (RFC 3492 vs Java Punycode, nothing injected). Set 2 `cases_holdout2/`: spec2 (SemVer 2.0.0 vs C), paper2 (Wikipedia variance algorithms vs C# Math.NET), c2c2 (Porter C vs PHP). Keys: `keys_holdout.py`, `keys_holdout2.py` (with TRAPS: correct code that looks odd); `NOTES.md` holds the injected diffs. **Both sets are now SEEN**; the next change needs new blind cases.

**Designs measured.** OLD = the t10 code (find_missing of D84, find_bugs of D87/D90). v1 = AUDIT + SCAN + a short new hunt + JUDGE + MERGE. v2 = v1 with a Flash-Lite judge and the "setting that is off" rule. v3 = AUDIT + SCAN + the OLD bug finder on bounded clients + JUDGE + MERGE.
- AUDIT (A -> B): every method claim of A against the WHOLE of B (B in groups of up to 24K tokens), 30 claims a call, 2 votes; verdict `same` / `differs` / `missing` / `n/a`; "same" in one group of B beats "missing" in another; a fact is flagged when either vote flags it. One sentence matters: a rule can apply in more than one place (where B reads a value and where it writes it).
- SCAN (B -> A): B in groups of 2K, with A's own TEXT beside each group when A is under 20K tokens (else the list of facts); lists what B does differently or what A never says. A scan that asked for both kinds explicitly (SCAN2) was not better.
- JUDGE: one list of findings, 2 Flash-Lite votes at the same time: `real` / `minor` / `false` plus the relation to A (`silent` / `differs` / `same` / `none`); false only when every vote says false; real + false -> `unclear`; only minor -> hidden. Added for v2: a finding about code behind a setting that is off, zero or unused is false or minor.
- MERGE: one call over the short texts and quotes of every finding that is not false; it returns groups of the same point; the best line of a group is kept (audit before hunt before scan).

**Results.**
- AUDIT on the 32 hand-made quora claims (slice 7 gold): 31 and 28 of 32 (Flash-Lite, 2 runs), 29 (strong); 2 calls, 21-173 s. The shipped per-claim check (CHECK v4) gets 31 of 32 with about 40 or more calls.
- The old per-claim check on ws over all 174 claims: 84 match, 89 absent, 1 mismatch in 462 s; the real missing checks were hidden among the 89 "absent". The AUDIT on ws: 8-10 items in 40-80 s, including the missing checks (unmasked client frames accepted, UTF-8 never validated, reserved close codes) and the 126-length and mask `%3` differences.
- Speed per case (good network): OLD find_bugs alone 810-1,760 s on the blind cases (the Cline 402 at tier 1, 600 s read timeouts and dead tiers explain most of it); v2 83-357 s for both jobs; v3 345-655 s.
- Injected bugs found (b64 4, algo 4, c2c 3, spec2 4, paper2 3, c2c2 3): OLD 18 of 21; v1/v2 15 of 21; v3 on spec2, c2c2, algo, b64, paper2 15 of 18 (16 in another paper2 run) against OLD 17 of 18 on the same five. A gap of 1-2 is near the noise (1-2 runs a cell).
- Lines shown (spec2 / algo / b64 / c2c2 / paper2): OLD 35 / 7 / 8 / 6 / 14 (spec2 about 12 repeats); v3 23 / 4 / 6 / 4 / 10, repeats merged away (spec2 14), noise 0-1 a case except paper2 (6). clean control: v1 2 lines (1 doubtful), OLD 5 (2 doubtful).
- The differences node ALONE (audit + scan + Flash-Lite judge + merge, no hunt), 7 blind cases: 46 lines, about 26 of 44 key difference items, almost nothing false (clean: 0 false), about 15 repeats because the Flash-Lite merge missed obvious groups (clean 7 lines for 2 points; paper2 the min/max point 4 times); judge + merge 14-24 s. With the strong merge first, spec2 folded 14 repeats correctly.
- Differences only, old fm against the new audit + scan (regex screen, weighted, 5 cases): old 22 of 58 differs, 1 of 8 silent; new 27 of 58, 4 of 8. In the whole pipeline a difference that the hunt also found is shown as a bug line, so per-node numbers undercount.
- Not found by the new parts: B1 (base64url 62/63 sits in a TABLE of A and the claims step dropped the row), H3 (a rule about many small updates that the spec never states), P1/P2 (subtle formula order and sign; found by the old finder on strong models, P2 only once), J2. Strong models alone (runs 10-13) and a double cheap trace (run 12) did not fix them. The old finder's STANDARDS checklist finds B1 and H3 from the model's own knowledge of the standard.

**Provider and network facts of the same day.** GLM-5.3 Flash on Cline answers HTTP 402 `insufficient_credits` (balance $0.01, total_spent 0): Cline moved it to Cline Pass (`cline-pass/glm-5.3-flash`); Cline's free list is `reflection/beam-free` and `nvidia/nemotron-3.5-lightning-free` (both answer, both in the chain) plus `cline-free/nemotron-3.5-super-vl` and `cline-free/solar-mini4` (403, Cline's own app only). It was moved to `KNOWN_DEAD` on 2026-11-03 (registry + test comment, on `feat/find-missing`, not committed). Also: Gemini 3.6 and 3.5 Flash spend their 20 a day by the afternoon; Ling 3.1 Flash on Kilo is paid (402); OrcaRouter answered 429 `free_rate_limited`; DeepSeek V4.1 Flash stable and MiniMax M3 (+cheap) on LiteRouter answer 403. The exit `193.36.85.173` was refused by Google (400 FAILED_PRECONDITION) for about an hour; v3 was re-run on a good exit (spec2 835 s -> 345 s). A harness lead named models by a wrong id ("deepseek-v4.1-flash" for "deepseek-v4.1-flash:free"), so its "strong" calls had fallen to Flash-Lite: read ids from `CHAIN`.

**Decisions.**

| # | decision |
|---|---|
| **D96** | **One node `find_differences` replaces the check fan-out (`check_one` x 48 with the re-query loop) and the `find_missing` scan.** `extract_claims` stays as the shared preparation (the list of A's facts). |
| **D97** | **Inside the node, two independent requests at the same time: AUDIT (A -> B) and SCAN (B -> A)**, as defined above. One request for both directions is rejected: it lost B's extra behaviour in the GPT test, and SCAN2 was not better. |
| **D98** | **`find_differences` has its own JUDGE (2 Flash-Lite votes, the rules above) and its own MERGE.** The merge leads with a strong model and a short time limit, then falls back to Flash-Lite (improvement 1; the Flash-Lite-only merge missed repeats). |
| **D99** | **`find_bugs` stays a separate node, unrelated to A**: the bug finder of D87/D90 (trace, method, concept, the standards and pitfalls checklists and their audit) with its 2-vote skeptic, on bounded clients. Removing its skeptic was not measured, so it stays. |
| **D100** | **A last cheap merge before `respond`** (one Flash-Lite call over both nodes' short texts) hides a point found by both nodes; it changes no node's own list. |
| **D101** | **Claims write one fact for each row of a table in A** (improvement 2; the base64url row was lost). `CLAIMS_VERSION` goes up. |
| **D102** | **Time limits for every call**: a whole-file call reads at most 120 s within a 300 s budget; a small call 40 s within 150 s, with no retry on the same tier. |
| **D103** | **Effort**: v3 is the normal mode now. The v2 short hunt is the planned FAST mode; its backend switch belongs to slice 11 and the user control to Step 3 (D32). Not built now. |

**Lessons (the user types the product code).** Lesson 1: the prompts and schemas (AUDIT, SCAN, JUDGE, MERGE) and the `Difference` value object with its readers. Lesson 2: `api/differences.py` (audit and scan at the same time, judge, merge) and the node `agent/find_differences.py`. Lesson 3: `find_bugs` itself, which is NOT in the repository yet (the old lesson 2 of 29.6 to 29.8 was never typed; the code is in the t10 copy), with the time limits of D102. Lesson 4: the wiring (graph: `extract_claims` -> `find_differences` and `find_bugs` at the same time -> final merge -> `respond`; the check fan-out and the re-query loop leave the graph; state keys, saved types, the planner's steps, `respond`'s finding lines), the claims table rows (D101). Then the closing review of slice 9.

**Owed to later slices.** Improvement 3: when A is code (c2c2), smaller scan groups or a second scan run (measure in slice 13). Improvement 4: formula-heavy parts to a strong model (slice 11, routing). Improvement 5: an audit answer "I need more context" with a search, for a big B (slice 12). M29: the differences node with the strong-first merge, re-measured on new blind cases. M30: A as code. The fast mode of D103 (slice 11). Re-check the Cline GLM-5.3 route if Cline puts it back on the free list.

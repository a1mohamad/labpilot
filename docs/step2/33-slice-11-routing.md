# Section 33: slice 11, routing

[Docs home](../README.md)

### 33. SLICE 11, LESSON 2: ONE COMPUTED ROUTE FOR EVERY TASK, AND THE TOOLS THAT KEEP IT UP TO DATE — 2026-11-20 and 21

*Lesson 2 was built and measured in the scratch copy `l2` and handed to the user to type (the routes, the wiring, two data tables). The repository does NOT have lesson 2 yet. The measuring tools were moved into the repository at the user's request (`scripts/routing/`), and every older script was moved into a folder for its job. Nothing is committed.*

#### 33.1 The design (D123 to D127)

| # | decision |
|---|---|
| **D123** | **A route is COMPUTED, never written by hand.** `labpilot/llm/routes.py` holds `TASKS` (20 tasks: kind, minimum strength, biggest prompt, the tokens it asks for, calls a question makes, the stop). `labpilot/llm/ratings.py` holds one row for each live tier (family, provider, strength 1-5 from AA v5.0.1, seconds, calls a day, penalty). `labpilot/llm/accuracy.py` holds the bench result of each model family on each task (accuracy, seconds, cases). Both data files are written by scripts (33.4). A new tier needs a row; the routes follow |
| **D124** | **Two steps. FILTER** (`why_not`): too weak for the task; output cap below the answer; prompt plus answer over the window; a per-minute input cap too small (Gemma); scarce (20 a day) and the task reads no file; a many-call task and a tier that takes one call at a time or under 10 a minute; too slow for the stop. **ORDER** by one score: `accuracy - w*log2(1 + seconds/T) + 0.08*quota - 0.03*penalty`. `w` and `T` depend on the kind of task (small 0.05 and 5 s, many 0.04 and 5 s, serial 0.04 and 20 s, hidden 0.02 and 20 s, answer 0.03 and 20 s, the two-file report 0.02 and 30 s), so a little more accuracy never buys a much slower model and a lot more can (the user's trade-off rule). The weights are first guesses. **Balanced 2026-11-21 (after a first try that let LiteRouter climb):** the time of a tier on a task is the bench time of its model FAMILY (`accuracy.py`, so a whole task keeps its real length), scaled by how fast its provider is against the family's other tiers in the speed test (`ratings.py`), held inside 0.5 to 2 times (`PROVIDER_FACTOR`). A tier that takes one call at a time for its whole account (LiteRouter, Requesty) loses `BUSY_PENALTY` = 0.10 in a step that runs beside other steps (claims, scan, audit, the bug hunt, the judges), because they share its one slot; the steps that run alone (rewrite, plan, gate, the three answers) carry the flag `alone` and keep it. Result: a one-at-a-time tier is first in 8 of 20 routes and in 4 of the 14 parallel steps (only where it is clearly the most accurate: method, skeptic, concept, checklist audit), against 15 and 11 before; the mean accuracy of the first tier of the parallel steps fell by about 0.02. Failed calls are counted once (routes never read `valid`; it is inside `penalty`). No pool rule was added. (The provider and model diversity penalty named here was REMOVED on 2026-11-23, D128.) **Three fixes (2026-11-22, after a review):** `plan` is not `alone` any more (when the summaries were not stored at upload they run in its step); in the family median each PROVIDER has one vote (its own tiers are joined first), so three ids of one model on LiteRouter cannot move the others' scale; and the test "at most a third of the parallel steps" was replaced by fixed examples (a close tier that is often busy drops below a free one; a much stronger one still leads). Only `plan` changed in its top 3 (Token Harbor and Routeway in place of two LiteRouter tiers behind Flash-Lite) |
| **D125** | **A result on few cases is pulled toward a guess:** `(n*a + 3*g) / (n + 3)` with `g = 0.15 + 0.12*strength`; a model with no result gets `g`. Four groups, in order: strong tiers; strong tiers whose calls a day feed fewer than 20 questions of the task (backups: Bazaarlink, Cloudflare, Token Harbor on many-call tasks); weak tiers (only a simple task keeps them, at the end); not-trusted tiers. Inside a group the order is the score alone (the penalty of 0.02 or 0.03 for a provider or model already placed was REMOVED on 2026-11-23, D128), and the three keys of one Google model stay together |
| **D128** | **Every task has its own route, and a model is never pushed down for being good on many tasks** (the user's call, 2026-11-23). (1) The route table already differed for every task (20 of 20), but the lesson 2 WIRING shared clients: `audit` also served the judge and the fresh check, and `method` also served the concept, checklist and checklist-audit calls. Now every step gets `for_task(client, its_task)`: `make_find_differences(audit=, scan=, judge_client=, merge=)`, `make_bug_finder(trace=, method=, concept=, checklist=, checklist_audit=, skeptic=)` (each `Hunt` names its `task`), `make_fresh_check(statement=, audit=)`. (2) `DIVERSITY` (0.02 a provider) and `DIVERSITY_MODEL` (0.03 a model) are REMOVED: they pushed DeepSeek down only because it was already high, even on other providers. The ONLY crowd rule left is `BUSY_PENALTY` (0.10): a tier that takes one call at a time for its account (LiteRouter, Requesty) in a step that runs beside other steps, because that is a real limit. Effect on the top 4 of each route: 11 of 20 changed, all by DeepSeek V4.1 Flash routes moving up (for example `respond_chat`, `respond_two`, `skeptic`). In `method`, `skeptic` and `respond_two` the first 3 or 4 tiers are now LiteRouter tiers that share ONE slot; a busy one is skipped at once (D113), so it costs no wait, but the next free tier comes later in the list. Built in the scratch copy l2: 2,379 unit and api tests pass, ruff clean, 9 deliberate breaks each caught (the diversity put back; the judge on the audit client; the concept on the method client; the checklist and the checklist audit on the wrong client; the judge on the scan client, which survived first, so a test was added; the fresh statement on the audit; two tasks on one route). Tests: `test_no_two_tasks_walk_the_same_route`, `test_a_model_placed_many_times_is_not_pushed_down_for_it`, `test_every_finder_step_walks_the_route_of_its_own_task`, `test_every_step_of_the_hunt_walks_its_own_client`, `test_the_audit_the_scan_and_the_judge_each_walk_their_own_client`. Not in the repository yet (part of lesson 2) |
| **D126** | **The answer asks for as many tokens as its kind needs:** chat 8,000, one file 16,000, two files 32,000 (`ANSWER_MAX_TOKENS` in `prompts/builder.py`), so tiers with an 8,192 or 16,384 output cap can write the shorter answers |
| **D127** | Gemini 4 Hydrogen joins on 3 keys (no thinking level sent, strength 5, scarce). Five LiteRouter ids left the free list (V4 Pro stable, V4 Flash 0731 stable, 0731, 0731 cheap, V3.1) and moved to `KNOWN_DEAD`; Hy3 came back. Cohere's chat models are NOT added now (the user's call); they are a candidate for a later slice |

#### 33.2 The bench (lesson 3): what was measured

The product prompts and readers, each model family alone (its own tiers, no fallback), the product retry rule, 19 tasks (merge_strong not benched), the cases and keys of slices 7 to 10 plus new keys written before the runs (`scripts/routing/bench_keys.py`). Round 1 ran about half the cases; round 2 ran the rest for the finalists, with twice the product stop. 1,648 rows (`artifacts/routing-bench/logs/bench.jsonl`). A case refused for quota or lost to the network counts neither way; a case where some calls gave up is left out of accuracy.

- **Many models are equally right on the simple tasks** (gate, fresh, rewrite, chat): speed and quota decide there.
- **DeepSeek V4.1 Flash is the strongest model across the board; Ling 3.1 Flash (Requesty) is a close, fast second.**
- **Concept and checklist are hard for every model** (best about 0.6 to 0.7).
- **LiteRouter cannot serve a step that sends several calls at once** (one call at a time): its calls waited in line until the stop. So LiteRouter only leads tasks of one call, and many-call tasks are led by Flash-Lite and Gemma.
- MiMo V2.6 Flash hangs on the checklist tasks. North Mini Code answered 404 on Kilo (it left Kilo). Cloudflare's daily neurons did not reset at 00:00 UTC on this account (probed 6 times until 03:40 UTC). Bazaarlink blocks the account for minutes after a burst of failed calls ("slow down", Retry-After 230).
- **Cut on purpose:** LiteRouter round 2 ran 17 cases, not 343 (only where its models are real candidates). Hy3, MiniMax M2.5 and Qwen3.8 Flash were measured and are not tiers (weak, or beaten everywhere).

**Limits:** three pairs, a few cases a cell, regex keys read by hand only for the best and the worst answers, one run per cell, speeds that depend on the hour (Token Harbor took 75 s a call in one period and 2 s later). Slice 13 repeats it on many pairs (27.1).

#### 33.3 The routes (first models; every route has 15 to 57 models)

| task | first models |
|---|---|
| gate | Flash-Lite 3.5, DeepSeek V4 Flash (LiteRouter), Nemotron 3.5 Lightning (Kilo), Flash-Lite 3.1 |
| plan | Flash-Lite 3.5, DeepSeek V4.1 Flash 1017 (LiteRouter), MiniMax M3.1 Flash (LiteRouter) |
| claims, scan | Flash-Lite 3.5, Nemotron 3 Ultra (Kilo), then backups |
| trace | Gemma 4 26B, Flash-Lite 3.5, Flash-Lite 3.1 |
| audit | DeepSeek V4.1 Flash 1017 (LiteRouter), Hy4 (OrcaRouter), DeepSeek V4.1 Flash (Token Harbor) |
| method, concept, skeptic, checklist audit | DeepSeek V4.1 Flash (several routes), Ling 3.1 Flash, MiniMax M3.1 Flash, GLM-5.3 Flash |
| one-file answer | Ling 3.1 Flash, Gemini 4 Hydrogen, DeepSeek V4.1 Flash 1017 |
| two-file report | DeepSeek V4.1 Flash 1017, Ling 3.1 Flash, DeepSeek V4.1 Flash (LiteRouter), Gemini 4 Hydrogen |

Checks in the scratch copy: 2,350 unit and api tests, `ruff` clean, 14 deliberate breaks each caught by its own test (two tests were added for the two that survived first: not-trusted tiers dropped, and the answer size not following the number of files). Open: several LiteRouter tiers stand in a row at the top of the hard routes (a busy one is skipped at once, so it costs no time, but more mixing of providers would be safer); the weights of D124 are not swept.

#### 33.4 `scripts/` reorganised, and the routing tools (2026-11-21, the user's request)

All 39 scripts moved from one flat folder into folders by job; imports, the tests that name them, the comments in `labpilot/` and the paths in both docs were changed with them (`scripts/README.md`):

| folder | scripts |
|---|---|
| `setup/` | setup_checkpoints, load_corpus, warm_embeddings |
| `routing/` | NEW: the tools below |
| `models/` | measure_latency, probe_routeway, probe_tools |
| `retrieval/` | aggregate, bench_index, bench_merged, combine_topn, corpora, draft_queries, jev_reranker, local_reranker, query_difficulty, score_content_kinds, score_hybrid, score_real_ingest, score_rerank, score_retrieval, score_topn, sweep_chunking, sweep_fusion, tier_reach, validate_fixture, zoo |
| `answers/` | score_answers, regrade_answers, score_report_tier, measure_claim_sizes, dilution |
| `timing/` | bench_end_to_end, bench_ingest, measure_clocks, verify_clocks, time_one_question, one_model_run, verify_one_model |
| `repo/` | merge_per_file |

Run them as modules from the root: `python -m scripts.setup.setup_checkpoints`. `tests/unit/test_scripts.py` now walks the subfolders. Two older scripts fail on import, as they did before the move: `answers/score_answers.py` names a rerank tier deleted in slice 8, and `timing/one_model_run.py` needs its arguments.

**`scripts/routing/`** (its README has the weekly routine): `free_lists.py` (each gateway's free list against the chain: GONE, BACK, NEW; no quota); `speed_check.py` (availability, speed and trust of every live tier, `--quick` = one call each, the 20-a-day models and the second and third Google keys always quick); `write_ratings.py` (proposes `ratings.py` from the speed logs, the newest log of a tier wins); `collect_data.py` (gathers the labelled cases into `artifacts/routing-bench/data/`); `bench.py` (the accuracy bench of 33.2); `analyze_bench.py` (table, round 2 plan, proposes `accuracy.py`); `compare_routes.py` (how the first 3 models of each task would change). Every script that calls a model checks the exit and probes Google first. Nothing writes into `labpilot/` without `--apply`; nothing moves a tier to `KNOWN_DEAD` by itself. Checked: run with lesson 2 in place, the scripts reproduce the lesson 2 tables number for number (0 of 20 routes change).

**The routine (the user's plan, from advice the user got):** every week `free_lists`, `speed_check --quick`, `write_ratings`, `compare_routes`, review the first 3 models of each task, then `--apply`; the full speed check every two weeks; the accuracy bench when a model, a prompt or a task changes. Later (end of Step 3, section 32) these steps become an Airflow job that opens a pull request, never a commit on `main`. **A guard to add, ask first:** skip Token Harbor tiers when its header `x-th-free-used-pct` is over 90%.

**The first free-list run (2026-11-21):** GONE: North Mini Code on Kilo and OpenRouter, MiniMax M2.7 on LiteRouter (and the five ids of D127). BACK on LiteRouter: Kimi K2.6 cheap, Mistral Large 3, Qwen3 Coder. These were not acted on.

#### 33.5 The bench numbers that cannot be trusted, and the plan for slice 13 (the user's call, 2026-11-22)

*Nothing is built. This is the plan, written at the user's request after reading `accuracy.py`.*

**What is wrong (read from `artifacts/routing-bench/logs/bench.jsonl`, 1,648 rows, 17.5 hours of calls):**
1. **Half the time went to calls that gave no result.** 284 rows failed and took 8.6 of the 17.5 hours. 59 of them waited 200 s or more each and took 7.7 hours alone. Most were `AllFreeTiersExhausted` (176 rows): every tier of the family failed, and the bench waited for each call until its stop (the product stop, doubled in round 2). Families with the most failed rows: MiMo V2.5 53, Ling 3.1 Flash 43, MiMo V2.6 Flash 24, Gemma 4 31B 23, Hy4 20, North Mini Code 16, Gemini 4 Hydrogen 16, Qwen 3.7 Flash 12.
2. **A cell `(0.00, 999.0, n)` is not a measurement.** `999.0` is a placeholder written by `analyze_bench.py` when no case of the cell succeeded (there is no time to report). It means "every call failed", often for network, quota or one-call-at-a-time reasons, not "the model is wrong". Today it still pushes the model down the route.
3. **Too few cases.** 109 of 278 cells rest on 1 case and 160 (58%) on 1 or 2. On 1 case the time and the accuracy are noise. The shrink toward the strength guess (D125) makes those cells 60 to 75% guess, so the hard routes follow the Artificial Analysis scores more than our bench.
4. **Wasted calls on models that are always near the bottom.** Weak or not-trusted families were run on every task although no route will ever use them first.

**The plan (slice 13, before any new number is trusted):**

| # | change |
|---|---|
| B1 | **No waiting for a dead call.** The bench uses the product rule only: no read timeout as a wait, a retry after 1 s and 3 s only for the cases D112 retries, no retry for 400, 403, 404, a daily 429 or a refusal, and every provider's own limits (D113: a busy tier is skipped, never waited for). A call that gives no answer is logged as FAILED at once and the next case starts. The hang stop stays only as a guard against a call that never ends (D115), at the product value and never doubled |
| B2 | **A family that keeps failing is stopped.** After 2 failed cases in a row on one task (no answer at all), the family's remaining cases on that task are skipped and the cell is marked "not measured", not 0.00 |
| B3 | **"Not measured" is not zero.** `analyze_bench.py` writes a cell only from scored cases; a cell where every case failed is left out, so the route uses the strength guess (D125) and the failure count goes into the `penalty` of `ratings.py`. No `999.0` placeholder in `accuracy.py` |
| B4 | **Skip the families that are known to sit at the bottom.** A family whose strength is below the task's minimum, or that is not trusted, or that the current route puts below place 10 with no chance to reach the top 3 (checked with `compare_routes.py`), is not benched on that task |
| B5 | **More cases where it matters.** Every cell of a family that can reach the top 3 of a route gets at least 5 scored cases, spread over several pairs (the new pairs of slice 12 and 13, 27.1), with a rerun of each cell that had 1 or 2 cases today, starting with the zero rows. Report the spread beside each mean and the number of cases |
| B6 | **Time is the median of scored calls only**, and the bench writes how many calls failed beside it |

**What done looks like:** a bench run that spends no hour on failed calls, an `accuracy.py` with no 0.00 / 999.0 rows and no route-leading cell under 5 cases, and the routes recomputed and compared with `compare_routes.py`.

#### 33.6 Streaming, its wait limits and the retry rule: tested and measured — 2026-11-23

*Built and tested in the scratch copy l2 only; the repository has none of it and nothing is committed. Exit AS24940 Hetzner (Nuremberg, Falkenstein). A copy of the l2 code and all the data and tools of this section are in `artifacts/slice11-waits/` (git-ignored: `l2_code.tar.gz`, `logs/`, `tools/`, `e2e/`). **Google was overloaded the whole evening (503 "high demand"), on plain calls as well as streamed ones, so streaming is not the cause; no limit below was taken from Google.***

**Streaming works.** One short streamed call with a tool for each provider, plus a long one (about 25K tokens by our estimate): LiteRouter (5 models), OrcaRouter Hy4, Requesty, Kilo, OpenRouter, Groq, Mistral, Cloudflare, Bazaarlink, Routeway Gemma, Google Flash-Lite 3.5 and 3.1, Gemma 26B and Gemini 3.6 Flash all accept it, and tool calls join correctly. No provider needs streaming off (Cline stays plain on purpose). **Not proven: Gemini 4 Hydrogen (503 on every call) and Token Harbor (free allowance spent until 2026-11-24 22:19 UTC).** Thinking pieces count as "alive" and are left out of the answer. A model that thinks for a long time uses the same `max_tokens` as its answer, so a small limit gives an empty answer (seen on 8 models at 4,000). A streamed OpenAI-shape call mostly loses the token counts (no `stream_options: include_usage`): open.

**Bugs found in l2 and fixed, each with a test:** (1) pieces were decoded as Latin-1 when the provider names no charset (most do not), so `é` and `“` were broken and true quotes would have been dropped; bytes are read and decoded as UTF-8 now. (2) The limits were not kept: the clock restarted after the headers (the first try could wait about 80 s), and it was checked only when a line came (a silent retry waited 30 s and not 12 s); one clock starts at the request and runs by itself (`open_stream`, `_pump`, `events`). (3) A 503 that Google sends in the middle of a 200 stream lost its status. (4) A stream that ends without a finish reason, or with an error after some text, was taken for a whole answer. (5) 23 tests named the non-streamed Google address.

**The measurement (`waits.py`): 497 calls, 3 prompt sizes (about 1K, 8K, 30K tokens), about 27 models, nothing cut before 120 s of silence, output capped at 3,000 tokens; 25 of 332 planned groups were still open at 23:21 and a few of them were dropped by the user.** Away from Google: 149 of 161 first tries good; of 151 working calls 140 had started within 10 s, 144 within 15 s and 146 within 20 s (4 of the 11 late ones are Routeway MiniMax, 69 to 79 s), by size 57 of 61, 41 of 44 and 42 of 46 within 10 s; 149 had no pause of 15 s (the two longer: 18.7 and 74 s). Google in the outage: 32 of 150 first tries, 25 of 106 after 1 s, 13 of 77 after 3 s, so **a retry of an overloaded key is the same dice roll again.** LiteRouter: 36 of 38 good, both failures "Too many concurrent requests". In the stopped arm A run, 33 failed calls were 503s (225 s) and 12 were silent (192 s).

**The replay (`sim.py`, 20,000 walks, seconds until a model starts; calls treated as independent, which is kinder to three keys of one overloaded model than reality):**

| rules | no Google: middle / worst 10% / first model answers | outage, 3 Flash-Lite keys first: middle / worst 10% |
|---|---|---|
| old: 40/12/10 s, two retries | 3.1 / 7.5 / 94% | 45.6 / 75.3 |
| 5 s, no 503 retry | 3.1 / 8.3 / 73% | 13.4 / 19.3 |
| 8 s, no 503 retry | 3.1 / 7.2 / 86% | 15.8 / 23.7 |
| **10 s, no 503 retry, one other retry** | **3.1 / 7.2 / 89%** | **16.7 / 26.2** |
| 15 s, no 503 retry | 3.1 / 7.2 / 92% | 17.6 / 31.1 |
| 10 s, one 503 retry | 3.1 / 7.4 / 90% | 28.4 / 40.1 |
| 10 s + a second model started at 5 s | 3.1 / 6.9 / 85%, 1.31 calls | 13.4 / 18.3 |

| # | decision |
|---|---|
| **D129** | **The wait and retry rules (replace the retry part of D112).** **(UPDATE 2026-11-24, D131: a 429 for a minute is not retried any more, the next tier is asked at once.)** First piece: **10 s**, counted from the request, for every try and size (`FIRST_PIECE_SECONDS`). Silence in the middle: **15 s** (`IDLE_SECONDS`; 12 s was the first choice, but the last calls had pauses of 13.7 and 14.0 s in good answers). A silent model is never retried. **A 503 is not retried: next key or model at once.** Another failure (no answer, a broken stream, 429 for a minute, 500, 502, 504) that came within **10 s** is asked again **once, after 1 s** (`RETRY_DELAYS = (1.0,)`, `FAST_FAILURE_SECONDS`); a provider that asks for more than 3 s is not waited for (`RETRY_WAIT_MAX`). 5 and 6 s were rejected: they drop a working first model in about a quarter of the calls. **The second model started early is NOT built:** on a normal evening it saves almost nothing, costs 31% more calls and the first model answers less often. It is the next idea if an outage evening is still too slow |

**What rests on little:** one evening, one VPN exit, 2 to 18 calls for each model away from Google; the "other failure" retry has 3 cases behind it; both limits and the 503 rule must be checked on a normal Google day, and on real long answers.

**Tests in l2:** unit and api 2,410 passed, 5 skipped; the integration tests (191 passed) ran before D129 and were not run again; `ruff` clean on labpilot, tests and scripts; 22 deliberate breaks (14 streaming, 8 for D129), every one caught (two survived first, so a test was added).

**Arms A, B and C were NOT compared.** Only otp arm A ran, with the old rules: stopped at 300 s (the user's limit) inside `extract_claims`, because Flash-Lite failed call after call. The arms differ only after that step. The harness (`e2e_routes.py`) now stops a run at 300 s, records the calls that are still open and uses a connection pool on its own schema. **Run them on another day, after REAL prompts pass on Flash-Lite** (the tiny "Say ok" probe passed 13 of 18 while real prompts passed about 1 in 8).

**Also open:** Routeway MiniMax (2 of 4, 69 to 79 s) stands high in `plan` and `merge_strong`, and Requesty Nemotron (rate limits) needs another look; the time of whole answers (27 to 90 s for Nemotron Ultra, Hy4 and Cloudflare Qwen, mostly thinking and writing) is now a bigger cost than the waits; the user types streaming and D129 into the repository with lesson 2.

#### 33.7 Routing made fast: the race, the memory of bad providers and the new order — 2026-11-24

*Asked by the user: the first answer on two files must take under 5 minutes, better 4, and bad providers must be skipped. Built and tested in the scratch copy l3 only (made from the repository at `f8762ee`, lesson 2 included, plus the streaming and D129 files). A copy of every changed file is in `artifacts/slice11-waits/l3/`, the bench rows in `bench_r3_to_r6.jsonl`, the harness and every run in `e2e_l3/` (all git-ignored). The repository has none of it and nothing is committed.*

**What was wrong.** (1) The routes of the hard steps were led by slow models (the audit was led by Hy4, 221 s in the bench), and Gemini 3.5 Flash-Lite was barred from them by the strength floor and had never been benched there. (2) Nothing remembered a bad provider: the next call asked a dead or empty tier again. (3) A call that was alive but slow was waited for, alone. (4) DeepSeek wrote the final report with a lot of thinking.

| # | decision |
|---|---|
| **D130** | **A race inside each call** (`llm/_race.py`, also called hedging). `generate` starts one tier. If it has not answered after the task's limit (`HEDGE`: small 6 s, many 12, serial 18, hidden 30, answer 10, report 40), a second tier of ANOTHER account and another model starts beside it, and later a third (`MAX_OPEN` 3). The first good answer wins and the others are cancelled. `_stream.py` has a `Cancel`, so a loser stops reading. The walk starts from the top of the route each time, so a tier that was busy a moment ago is looked at again |
| **D131** | **A shared memory of tier health** (`llm/_health.py`, inside the process only). After a failure a tier rests, and the walk skips it: quota 60 s to 1 hour, gone (401, 402, 404, not on the plan) 10 minutes to 1 hour, overloaded (503) 10 to 30 s, silent or slow 20 to 60 s, any other failure 10 s to 2 minutes. The rest doubles with each failure, and several failures of one tier at the same moment count once. A daily 429 is recognised in the text too (`daily_rest`). The last resort: when nothing else is left, a tier that rests less than 120 s more is tried |
| **D132** | **The order is "quick and nearly as good first".** A tier is QUICK when its measured time is under the task's target (small 15 s, many 40, serial 60, hidden 100, answer 100) and its accuracy is within 0.20 of the best. Quick tiers come first (a quick not-trusted tier before a slow trusted one), then the rest by the score of D124. The floors went down where the bench showed it is safe: claims and scan 2, audit, checklist audit, skeptic, method and concept 3. Each task has a stop for one call (30 to 180 s) and a total budget (40 to 300 s), so no step waits long |
| **D133** | **The final answer asks for LOW thinking** (DeepSeek: 60 to 111 s for a report, against 117 to 121). It is used ONLY for the answer: low thinking made the method question much worse (accuracy 0.95 to 0.57 and 1.0 to 0.27) |

**Also changed:** a per-minute 429 is not retried any more, the next tier is asked at once (this corrects D129); Flash-Lite 3.5 and 3.1 carry 15 requests a minute; `CALLS_AT_ONCE` and `CLAIMS_AT_ONCE` 4 to 6; the bug hunt starts its two long questions before the many small ones; a 503 goes to the next tier, so the old integration test of a 503 retry was rewritten.

**The new bench (rounds 3 to 6, few cases, ONE run a cell, so small gaps are noise).** Gemini 3.5 Flash-Lite: audit 0.95 in 26 s, skeptic 0.80 in 39 s, checklist audit 0.73 in 17 s, but method 0.08 and concept 0.00 (it must never lead those). GLM-5.3 Flash two-file report 0.97 in 78 s, DeepSeek V4.1 Flash 0.93 in 77 s.

**The worst-case runs** (search path forced, bug hunt forced, exit AS24940 Hetzner, one run each; the rule for a run is a stop at 360 s):

| pair | before the fix | with the fix, quotas mostly there | with the fix, daily quotas spent (Flash-Lite key 1, Gemini 3.6, Token Harbor, Cloudflare, Bazaarlink, mostly by our own benches) |
|---|---|---|---|
| otp | stopped at 360 | 234 (no hunt), 275, **219** | 271, 328, 248, 250; one stopped at 360 (a bug in the first health memory, fixed) |
| quora | not reached | 360 (an early version), **259** | 321, 293, 330, 328; one lost to a database connection that Supabase closed |

**How to read it.** With quotas: about 4 minutes. With most daily quotas empty: 4 to 5.5 minutes. **The target "always under 5 minutes" is NOT proven:** 4 of the 8 degraded runs that ended took over 5 minutes, and in several degraded quora runs one bug question (method or concept) or the skeptic got no answer, so the report had fewer findings. Every run is one run on one evening, the code changed between runs, and quality was looked at only for the report.

**Checked in l3:** unit and api 2,488 passed, 5 skipped; `ruff` clean; about 33 deliberate breaks, all caught (the last one, the daily 429 in `openai_compatible.py`, got its test but the break was not run again). The database tests: 191 passed (12 minutes).

**Open.** The two pairs on a fresh quota day (Google resets at midnight Pacific, Token Harbor after 24 Nov 22:19 UTC); the method and concept questions have few good tiers (DeepSeek V4.1 Flash 0.70 and 0.68; next GLM-5.3 Flash 0.54 on method and Gemini 3.6 Flash 0.43 on concept; some zero cells rest on one failed call, so strong models such as Ling and MiniMax M3.1 are not really measured there) and they are the weak point; all time numbers are first guesses and go into the table of 27.2; the weekly smoke run; arms A, B and C are dropped for now (the new order replaced the question); Hydrogen and Token Harbor streaming; the judge reads the whole of B for every finding (an idea: the cited parts for "B does this", all of B for "B leaves out"; to measure).


#### 33.8 Slice 11 is CLOSED: the last work and the closing review — 2026-11-24

*The user typed the routing code of 33.6 and 33.7 (commit `d561d4a`). Then, at the user's request in words, Claude wrote the rest of the product code (an exception to "the user types all product code"), the tests, the closing review and the docs split. Exit AS24940 Hetzner, Nuremberg, Google 200. Nothing of this section is committed.*

**The end of the routing code.** Five files were still missing: `for_task` did not pass the race delay and the time budget of the task (so they were NOT used), `CLAIMS_AT_ONCE` and `CALLS_AT_ONCE` 4 to 6, the order of the hunts, and the bench patches.

| # | decision |
|---|---|
| **D134** | **Token Harbor may be used (the user accepts that its staff may read free chats; this ends D116) and is skipped when MORE than 90% of its weekly allowance is used.** Every reply carries `x-th-free-used-pct` and `x-th-free-resets`. Over 90 the whole account rests until the reset (at most a day at a time, an hour when the time cannot be read), and it is not a last resort either. The rest has its own key in the health memory, because the good answer that brought the header would end a normal rest. `llm/_allowance.py`; the header names are fields of the provider |
| **D135** | **Streamed answers report their tokens:** `stream_options: {"include_usage": true}`. Tried live with one call each on 11 gateways: 9 accept it (LiteRouter, OrcaRouter, Requesty, Routeway, Groq, Kilo, OpenRouter, Bazaarlink, Mistral), and Routeway then sends no numbers. Token Harbor and Cloudflare had no quota left, so it is OFF for them (`stream_usage=False`) until somebody tries it. Google reports its tokens without it |
| **D136** | **No database connection is held while a model answers (R16).** `store.PooledConnection` takes a connection from the pool for each query and gives it back. It has `execute` and `cursor`, so the read functions of the store take it as it is. A query on a connection that died is sent once more; a pool that gives none is `ConnectionFailed` (503). The route uses it when there is a pool; without one (tests) it opens one connection, as before |
| **D137** | **The fast mode of `find_bugs` (the backend part of D103):** `fast` in the request leaves the two checklists and their audit out. They are two steps in a row before the skeptic, so they set the time of the hunt. The words of the short hunt of 29.9 were only in a scratch folder and are lost, so this is the same idea with the prompts we have. A fast result has its own saved key: it never answers a full question, and a saved full result does answer a fast one. The throwaway page has one check box. **NOT measured:** neither the seconds saved nor the defects lost (the checklists find the concept defects such as a code that can be used twice, 29.7). The real control is Step 3 (D32) |
| **D138** | **`llm/registry.py` (2,029 lines) is split: `llm/registry/`, one file for each gateway, and `order.py` with `CHAIN`, `NOT_TRUSTED` and `KNOWN_DEAD`.** Moved by a script; every public value and the whole `CHAIN` were compared and are equal, apart from D134 and D135. `tiers.NAME` works as before. `order.py` and `literouter.py` are over 400 lines because they are only data, and the architecture test names them |
| **D139** | **Gemini 3.8 Flash stays trusted** (the user's decision). It is only the last resort of the two-file report |

**Left for later, on purpose:** better citations, with the check that refuses an answer whose citations cannot be resolved, belong to the END of Step 2 (the user's plan).

**The closing review.** The standing question: which real failure is still unprotected?

- *Joins that no test crossed:* a whole question over a REAL pool with no shared connection. `tests/integration/test_pooled_connection.py` (5 tests: the same rows as a plain connection, a write that is really committed, no connection out while the answer is written, a saved chat, 20 reads at once over 8 connections).
- *A guard that checked only a name:* the page could send `fast: false` for ever; a new page test holds it. It was found because the break survived.
- *A noisy test:* an unhandled thread error came from a fake request that returned `None`. The test was fixed, the code was right.
- *Dead code:* the unused constant `HTTP_INTERNAL_ERROR` was removed. No script names a removed function.
- *Breaks:* 22 deliberate breaks on kept copies. 21 were caught at once and one survived (the page box) and got its test. The break of the daily 429 that 33.7 left open is caught too.
- *Tests run:* unit and api 2,517 passed, 5 skipped; the database tests of the pool, the saved results and the chain (26 passed); `ruff` clean. The full suite was NOT run (the user runs it), nor the weekly smoke run.

**The docs were split the same day:** CLAUDE.md (1.4 MB) and DETAILS.md (1.6 MB) became `docs/`. Every line of both was checked to be on a page, except the old contents list and the introduction of DETAILS.md. `tests/unit/test_docs.py` holds the size of CLAUDE.md, every link and the generated pages.

**Not proven, and open:** see [current status](../status/current.md#open-now).

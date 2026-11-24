# Status history

*Older status notes, newest first. The newest facts are in [current status](current.md).*

[Docs home](../README.md)

## Current Status

**Status of 2026-11-24 (routing made fast): the fix of the slow runs is built, tested (2,488 unit and api tests, 191 database tests) and measured in the scratch copy l3 (files in `artifacts/slice11-waits/l3/`): a race between models inside each call, a memory of bad providers, quick-and-nearly-as-good models first (D130 to D133). The worst case takes about 4 minutes with quotas and 4 to 5.5 minutes with most daily quotas empty; under 5 minutes always is NOT proven. The repository has none of it and nothing is committed. See [section 33.7](../step2/33-slice-11-routing.md#337-routing-made-fast-the-race-the-memory-of-bad-providers-and-the-new-order--2026-11-24).**

**Status of 2026-11-23 (routing, streaming and the wait rules): streaming was tested live on every provider and fixed, and the wait and retry rules were chosen from 497 measured calls (D129: 10 s for the first piece, 15 s of silence, no retry of a 503, one retry after 1 s of another fast failure). All of it is in the scratch copy l2 only (a copy is in `artifacts/slice11-waits/`); the repository has none of it and nothing is committed. Google was overloaded, so arms A, B and C were not compared. See [section 33.6](../step2/33-slice-11-routing.md#336-streaming-its-wait-limits-and-the-retry-rule-tested-and-measured--2026-11-23).**

**Status of 2026-11-21 (routing, lesson 2 and the tools): lesson 2 (one computed route for every task, the bench of every model on every task) is built and measured in a scratch copy and handed to the user to type; the repository does not have it yet. `scripts/` was reorganised into folders by job, and the measuring tools are in `scripts/routing/`. Nothing is committed. See [section 33](../step2/33-slice-11-routing.md#33-slice-11-lesson-2-one-computed-route-for-every-task-and-the-tools-that-keep-it-up-to-date--2026-11-20-and-21).**

**Status of 2026-11-19 (routing, lesson 1 DONE): the user typed lesson 1 on branch `feat/routing` (made from `feat/stored-summaries`): the spreader (rooms, skip a busy tier, no waiting), the retry rule of 1 s and 3 s, the stop of a hung call, and the labels on the tiers. It is checked and tested: 329 tests of `tests/unit/llm` and the four api and script test files that touch it pass, 8 deliberate breaks were all caught, `ruff` is clean. The full suite was NOT run. The routes (`labpilot/llm/routes.py`) and the wiring are lesson 2 and are not in the repository yet. Nothing is committed. See [section 31.22](../step2/31e-spreader.md#3122-routing-lesson-1-typed-checked-and-tested--2026-11-19).**

**Status of 2026-11-16 (the spreader and the routes): the spreader and one route for each of the 20 tasks are built and tested in a scratch copy ([section 31.20](../step2/31e-spreader.md#3120-the-spreader-and-the-routing-chain-built-in-a-scratch-copy-2026-11-16-lesson-1-follows-the-repository-has-none-of-this-code-yet)); the repository has none of that code yet and nothing is committed. The rules (D112 to D116): a tier is asked again after 1 s and after 3 s and then the walk goes to the next tier at once; a busy tier (a full minute room, one call already open, an account that must rest) is skipped and never waited for; every task has its own route with the stop of a hung call; the tiers that may be read by the provider (Token Harbor) are left out by default. NEXT: the user types lesson 1 (the spreader), then lesson 2 (the routes and the wiring); the Gemma models on Google are measured again.**

**Status of 2026-11-16 (the measurement): every model was measured for speed and trust ([section 31.19](../step2/31d-model-measurement.md#3119-the-measurement-of-every-model-speed-trust-long-prompts-and-hidden-limits--2026-11-16)): 71 models, five calls each (100, 200, 500, 4,000 tokens and one long prompt of up to 20,000), no timeout and no output limit of ours. 64 models are trusted by the rule (4 of 5 valid) and 7 are not. The input length changes the speed very little (median 3.8 s at 100 tokens, 5.0 s at 20,000). The hidden limits found: Mistral allows 2 requests a minute for each model (and Nemo is Ministral 8B), Requesty takes one request at a time, Cloudflare GPT-OSS 120B stops at 256 output tokens when no limit is sent, LiteRouter wants 7 s between the starts of two messages, Gemini 3.8 Flash needs 155 to 579 s, and one Token Harbor call hung for 40 minutes. Everything is in `artifacts/slice11-measure/results.jsonl`. The registry was NOT changed and the spreader copy is still in the scratch folder. NEXT: the user decides the chain changes of 31.19, then the routing design.**

**Status of 2026-11-16 (later): TOKEN HARBOR IS IN THE CHAIN (section 31.17). Its four `:free` models (DeepSeek V4.1 Flash, DeepSeek V4 Flash, MiMo V2.6 Flash, MiMo V2.5) answered 20 of 20 calls in 2.8 to 7.3 s. Its own FAQ gives 60 requests a minute and 1,800 an hour per account, no limit on concurrent requests, and a value-based free allowance on a rolling 7 days whose size is not published. `CHAIN` has 112 tiers. These four are for small jobs only, because staff may read free-route conversations and the providers may train on them. The key variable is `TOKEN_HARBOR_API_KEY`. Nothing is committed.**

**Status of 2026-11-16: the first job of the rest of slice 11 (the chain cleanup) is done and the ROUTING GUIDE is written ([section 31.18](../step2/31c-routing-guide.md#3118-the-routing-guide-tasks-limits-of-every-provider-and-what-can-serve-what--2026-11-16-the-basis-of-the-routing-design-of-slice-11)): the 18 tasks with difficulty and call counts, the limits of every provider, and what each provider can serve. Nine LiteRouter tiers and two more (Beam on Cline, Ling on Kilo) are in `KNOWN_DEAD` (36 names), Gemini 3.7 and 3.5 Flash left the chain (Google redirects them), a new category `NOT_TRUSTED` (9 tiers since 2026-11-17: the three Google Gemma 4 31B tiers, the four OrcaRouter ones and both Muse Glimmer routes) sits at the end of the chain, and Hy4 preview (OrcaRouter) joined after a 5-of-5 test; `CHAIN` has 112 tiers (108 until Token Harbor joined, 2026-11-16). Nothing is committed on `feat/stored-summaries`. NEXT: design the routing table from 31.17 and 31.18, starting with the room spreader (D70).**

**Status of 2026-11-15: D110 (the first job of slice 11) is BUILT, measured and mutation-checked ([section 31.16](../step2/31b-slice-10-built.md#3116-d110-is-built-the-summaries-and-the-gate-verdict-are-stored--2026-11-15)). The two summaries are made when a file is uploaded and stored in `saved_results`, and the gate verdict is made at the first question that has both files and stored too. A question about a stored pair now makes 2 model calls instead of 5. The gate stays AFTER the planner (the plan is read by `halted()`). The branch is `feat/stored-summaries`; nothing is committed. The rest of slice 11 (routing, the chain cleanup, the fast chain for a chat question) is NOT started. The real database had no `saved_results` table until `create_schema` was run on 2026-11-15, so D104 never saved anything there before.**

**Status of 2026-11-14: slices 0 to 10 of Step 2 are DONE (slice 10 closed: sections 31.11 to 31.15). Slice 10 was REDESIGNED on 2026-11-12 ([section 31](../step2/31a-slice-10-design.md#31-slice-10-redesigned--2026-11-12)): there is NO `extract_outcomes` node and NO comparability node (D108); instead the timer (S1, 08d16b4), the COMPARABLE sentence, the ask-the-user pause (D109, B), and ONE planner change with four choices (D107): `ask`, `about`, `files` and `fresh`, used by the graph (a chat question and a one-file question run less; `fresh` adds one new check of B, D111). Lessons 1 to 5 are typed by the user and the tests are in the repository; the full suite on the repository was NOT reported by the user when this was written (the scratch build gave 2279 passed, 0 failed), so run `python -m pytest tests -q` once. Nothing of slice 10 is committed yet. C of D109 (ask while the agent works) stays in Step 3; D110 (summaries and the gate verdict stored) was built at the start of slice 11 on 2026-11-15 (31.16). **Next: the rest of slice 11 (routing).**

**Phase: STEP 2 IS IN PROGRESS — status of 2026-10-24. STEP 0 AND STEP 1 ARE COMPLETE AND
CLOSED.** Step 1 was nine slices (1, 1b, 2, 3, 4, 5, 6, 7 and 8), all done, and slice 8 ran
three times (v1, v2, v3). Step 2 is planned as FOURTEEN slices (0 to 13, rewritten on 2026-10-14, see section 21; a fifteenth, slice 14 "Jev for decisions", was added on 2026-10-23, see D73 in 23.2): **slices 0 (does
LangGraph fit), 1 (the latency ranking) and 2 (the skeleton and chat memory) are done, and slice 3
(`summarize` for A and B at the same time) is DONE: lessons 1 to 3 on 2026-10-15 to 17 (17.16, 17.17) and the D45 task, a check of the whole app and the split of `api/services.py`, on 2026-10-18 (17.18). Slice 4, the planner, is DONE: lesson 1 (function calling) on 2026-10-18 (17.19), lessons 2 to 5 and the map with signatures and first sentences on 2026-10-18/19 (17.20), and a closing review of slices 3 and 4 on 2026-10-19 (17.21). Slice 5, run the plan, is DONE: lesson 1 (`Send`, a fan-out whose size is decided while the program runs) on 2026-10-19 (17.22), lessons 2 and 3 (one search for each query, the merge, the pool, `respond` and the summaries) on 2026-10-20 and 21, the move to `search_one` only (D57) and its closing review on 2026-10-21 (17.23). The planner and the summarizer are wired into `ask()` now; M5 and M16 are owed (slice 13). Slice 6, follow-ups and `respond` for 0, 1 and 2 files, is DONE: lesson 1 (the follow-up rewrite and the last answer) on 2026-10-21, lesson 2 (one prompt function, three instructions, the budget of 30,000, the exact outline charge, the API and the page) on 2026-10-22, and its closing review (17.24). The instructions measured in slice 6 are a SMALL sample and M18 re-measures them in slice 13. Slice 7 (claims, check, retry) is IN PROGRESS: lesson 1 (`extract_claims`, with a quote for every claim) was built and tested in a temp copy on 2026-10-22 and typed by the user; the design work, the research and the size test of that day are in section 23. Lesson 2 (one check for each claim, the findings in the report) is DONE on 2026-10-24 (24.1, 1834 tests green). Lesson 3 (the bounded retry loop, D4) is DONE on 2026-10-24: a plain `for` loop inside the check node, typed by the user, all tests green (24.2). A talk about evaluation loops produced D74 to D76 (24.3, 24.4). The measurements of the end of slice 7 and its closing review ran on 2026-10-24 (section 25): reading A in groups of about 2,000 tokens beats one call (9.3 against 2.8 to 3.2 of 12 facts), no rerank for each claim, Jev is a promising checker but not proven, the end-to-end baseline on the search path is weak (judged 5, surfaced 2, absent 12 of 19, and 7 of the 10 countable misses never reached the report writer), and the review found a real defect (one failed claim search loses the whole answer) whose tested patch is NOT in the repository yet.** **Late the same night every change of 25.11 was built and measured by Claude at the user's request ([section 26](../step2/26-slice-7-built.md#26-slice-7--every-change-of-2511-built-and-measured-and-step-1-re-checked--2026-10-24-late-night)): the search path 29-31 of 39 against 13-16, the stuffed answer 30 in 36 s, the claim check 30 of 32; 20 commits on `feat/check-claims`, local, not pushed.** The user writes the graph code lesson by lesson, so
`labpilot/agent/` holds the real graph (`build_graph`: plan and two summaries together, measure, stuff or
one search for each query then merge, respond, remember). `ask()` runs it, and with a `thread_id` the chat is saved in Postgres. Read
[Where Step 2 stands](step2-progress.md#where-step-2-stands--updated-2026-10-21) below and
[STEP 2 — the plan](../step2/00-plan.md#step-2--the-plan-recorded-2026-09-22) before anything else. The plan
OVERTURNS older text in two places: no findings score has ever been measured on the search
path (C3), and the planner cannot use `build_context` (C5; the planner's map is now built,
section 12).

**1834 passed, 137 skipped — measured 2026-10-24 by the user, full suite without `--run-smoke`, BEFORE lesson 3 (ruff was not run for this number). After lesson 3 the user reported the full suite green and did not write the count down; Claude measured unit and api alone on 2026-10-24: 1705 passed, 5 skipped, and `ruff check` and `ruff format --check` clean** **Closing review of slice 7, 2026-10-24, in a scratch copy of the committed tree: unit and api 1706 passed and 5 skipped before any change; the whole suite (unit, api and database tests, no `--run-smoke`) gave 1,884 passed, 138 skipped and 1 failed in 20 minutes (2,023 tests collected). The one failure was a database connection that Supabase closed in the middle of a search, in `test_a_chat_on_the_searched_path_is_saved_and_comes_back_as_real_objects` (a test that also failed once before, on 2026-10-21, with another network error); it passed 3 of 3 on a re-run, and it does not touch claims or any changed code. No skip is about the database; the skips are the smoke tests and three others with a stated reason.** (run `pytest` for the current
count; a number written here goes stale on the next commit). The RAG system ingests a
file, a `.zip` or a git URL; stores it in pgvector; and answers a question by
stuffing when the pair fits and by search + fusion + gate + rerank when it does
not. Every constant in that sentence was measured — see
[STEP 1 IS CLOSED](#-step-1-is-closed--2026-09-19-all-nine-slices-measured-and-shipped)
for the numbers and the four defects measuring found.

**How this file is organised (2026-10-08).** This is the COMPACT version that is loaded every
session. [DETAILS.md](../archive/README.md) is the full, unabridged text it was cut from: the long Step 0
and Step 1 narratives, the old START HERE blocks and the dated session notes, word for word.
Every heading of the old file still exists here, so an old link still lands; where a section
was compacted it ends with a line saying which part of DETAILS.md holds the full story. Code
comments cite sections of this file by number (for example "14.3", "10c", "11.9"); those
numbers are kept.

**ONE THING LANDED AFTER STEP 1 CLOSED: `typesafe/jev-1.13` IS CHAIN 3's
SECOND MODEL** — **on `main`, and `feat/jev-probe` is byte-identical to it**
(`git diff --stat main feat/jev-probe` is empty, checked 2026-09-22). This block
read *"not merged"* for three days after it was; the gateway sweep, Qwen,
DeepSeek and the GLM-5.2 move are all on `main` too.
A **decision model, not an LLM** — it returns typed probabilities and cannot
write a word. Measured on two corpora it beats every rerank tier except
flash-lite, and beats flash-lite on `geo`, the unsaturated one. It is the
**first non-Google tier** in a chain that was eight-of-eleven Google, and the
**first PAID tier in any chain here** ($0.042/M input, and the balance does not
report it for a minute). It costs the 512MB budget **0.6 KB** and adds no
dependency and no env var. Read
[Jev, the decision model](../llm/jev.md#jev--the-decision-model-and-the-first-paid-tier-2026-09-19)
before touching `api/reranking.py`, and note that it does **not** help the
generation-time problem below — it cannot generate.

> ### ✅ THE GOOGLE EMBED BATCH DEFECT IS FIXED — 2026-09-27, proven LIVE
>
> Branch `fix/google-embed-batch`, three commits. **Google refused two things,
> and both are now handled:** a batch too BIG (96 texts, ~47,869 tokens against
> a 30,000/minute bucket) and a minute too FULL (a second 40-text batch inside
> the same minute). The first fix alone only moved the failure to batch 2.
>
> ```
> max_batch_size   a PROVIDER field: 96 Mistral, 40 Google. embed_batches clamps
> Pace             limits a provider ENFORCES - not Rate, which Mistral runs 11x
>                  past. Only Google has one: 30,000 tokens + 100 TEXTS a minute
> pacing.reserve   one 62s window PER POOL (key + model), at 90% headroom; waits
>                  before a request that would overflow it. Shared across calls,
>                  so side B does not start inside side A's full minute
> 429 / 503        a WAIT, never a size: 20s, then 60s (or Retry-After), the SAME
>                  batch again. Past that the error names the DAILY budget
> EmbeddingError   carries status + retry_after - branch on the field, not text
> batches         cut by tokens so TWO fit a minute, not one
> ```
>
> **Live, exit `185.254.96.11` AS58212 dataforest, Google 200:** 160 real
> chunks on `gemini-embedding-001`, 4 batches of 40, **zero refusals**, the
> pacer holding batch 3 for ~50s. Took 1.29 min against 1.78 promised. These
> chunks were small, so the 100-TEXTS limit bound; **the token path is proven
> only in simulation** - `tests/unit/embed/test_google_pacing.py` runs the
> shipped `GoogleEmbedder` against a fake Google enforcing the measured rule,
> including one that counts 25% more tokens than `chars/3`.
>
> **815 passed, 5 skipped** unit + api; 216 passed integration + api. **11
> mutations, all fire** - one (a window forgotten per call) survived first
> because its test ended side A on an EMPTY minute; the premise is now asserted.
> `scripts/setup/warm_embeddings.py` now uses this too - its private copy of the
> batching and pacing was deleted on 2026-09-28.

> ### ⚠⚠⚠ STEP 2's FIRST PROBLEM IS GENERATION TIME — 400 SECONDS, MEASURED
>
> One answer took **401s**, another **497s**, and generation was **98.2%** of
> it. The slow model is the BEST model: tier 1 `glm-5.3-flash` is Toolathlon
> #1 of 42, and `gemini-3.5-flash-lite` answers in 16.4s while losing 5 of 19
> findings. Thinking is NOT the lever — tier 1's reasoning is already capped
> at 17-60 tokens.
>
> **The levers are shorter per-node output, PARALLEL nodes, and routing.**
> Step 2 also owes the first LATENCY ranking of the chain — 23 tiers ordered
> by quality and quota, never once by speed — and it must handle EVERY tier,
> because the chain falls back and any tier can serve any node.
>
> **Read [the Step 2 time block](../agent/design.md#agent-design--step-2-recorded-2026-08-11)
> before designing a single node.**

> ### ✅ STEP 1 IS CLOSED — 2026-09-19. ALL NINE SLICES, MEASURED AND SHIPPED
>
> **The RAG system is complete and every number in it was measured rather than
> chosen.** `docs/slice8v3/DECISIONS.md` is the deliverable — 29 decisions,
> FOURTEEN of them now in `labpilot/` rather than in a document. `RESUME.md` is
> the working log, `FINDINGS.md` (H0–H19) the evidence. v1 and v2 are KEPT and
> stay valid for what they measured.
>
> #### THE SHIPPED SYSTEM, end to end
>
> ```
> POST /artifacts   file | .zip | git URL  ->  sources -> ingest -> embed -> pgvector
> POST /compare     {a, b, question}       ->  ask()
>
> ask()   measure both sides          one round trip, no rows move
>         fits PROMPT_BUDGET?  yes -> READ EVERYTHING BACK. no embed/search/rerank
>                              no  -> embed the question with EACH side's OWN model
>                                     search per side          SEARCH_LIMIT  50
>                                     + BM25, fused            SCORE_ALPHA   0.85
>                                     the skip gate            SKIP_MARGIN   None
>                                     rerank per side, never merged
>                                       the tier reads         RERANK_WINDOW 20
>                                       and we keep            RERANK_TOP_N  10
>                                       a tier declined ->     VECTOR_TOP_N  15
>                                     select, equal share      SIDE_SHARE    0.5
>                                     outline ladder           OUTLINE_BUDGET 4,000
>                                     build_prompt             PROMPT_BUDGET 30,000 (26,000 until 2026-10-22)
>                                     generate                 REPORT_MAX_TOKENS 32,000
> ```
>
> **23 generator tiers · 8 embedders in `MIGRATION` · 11 assembled rerank
> tiers · exact search, no index** *(as of 2026-09-19; later: 56 generator
> tiers and 13 rerank tiers, read `CHAIN` and `api/reranking.py`)*. `test_the_three_top_n_numbers_keep_their_order`
> pins the one relationship that is arithmetic rather than a knob:
> `RERANK_TOP_N <= RERANK_WINDOW <= SEARCH_LIMIT` and `RERANK_TOP_N <=
> VECTOR_TOP_N <= SEARCH_LIMIT`.
>
> #### WHAT THE THREE RUNS MEASURED — the whole of slice 8 in one table
>
> | | v1, 3 corpora | v2, 13 corpora | **v3, 20 corpora / 423 queries** |
> |---|---|---|---|
> | **embedder** | codestral stays | confirmed | **confirmed — and NOT on recall.** No model wins everywhere, averages within 0.013. **Google counts one TEXT as one request**, so it embeds 1,000 chunks a day, not 96,000, and cannot ingest a repository at all |
> | **fusion** | slice 5 OVERTURNED — every wRRF setting improved `r@50` on geo, best +0.067 | ON below `r@50` ~0.95 | **ALWAYS ON.** The v2 rule is not implementable — `r@50` needs ground truth and a user's repo has none, ever. Always-on `score a=0.85`: **gains ≥1 query on 5 corpora, loses ≥1 on NONE** |
> | **reranking** | SHIPS, +75% of headroom on geo | 9 real gains, 1 real loss | **SHIPS.** `bge-reranker-base` DELETED — worse than not reranking on three corpora, two languages, three domains |
> | **chain 3's order** | — | rests on ONE corpus | **Cohere ABOVE Voyage.** Cohere is the only reranker measured that has never hurt a corpus, and it rescues `gson` — flash-lite's worst case — by 5.8 queries |
> | **the routing signal** | does not reproduce | **DEAD** — every question kind positive | stays dead |
> | **the gate** | best tau never reranks | within noise | **`SKIP_MARGIN = None` confirmed, third corpus** |
> | **the window** | — | — | **`SEARCH_LIMIT = 50`.** Turns over between 50 and 100: `r@1` 0.711 -> 0.511 while `r@10` 0.822 -> 0.911 |
> | **`VECTOR_TOP_N`** | 25 | "should be 10" | **15** (and the 30 that shipped first was a UNIT ERROR) |
> | **exact vs HNSW** | exact | exact | **exact, CLOSED.** 2.9 / 6.1 / 11.3 ms at 335 / 729 / 1,387 rows on the real instance, against a 350 ms round trip and a 52,700 ms report |
>
> #### THE END-TO-END CLOCK — measured at last, and it is the Step 2 problem
>
> ```
> INGEST    ~26s per 100 chunks. The ESTIMATE was 1.4-2.4x optimistic and the
>           page showed it; +0.030s per chunk of overhead lands it within +-14%
>
> ANSWER    STUFF  paper + model_architecture.py   27 chunks   119.0s
>           STUFF  paper + 01-tokenizer.ipynb      29 chunks   401.5s
>           SEARCH paper + B_train.py              20 chunks   496.7s
>
>           retrieval is 8.8s of that 496.7s.  GENERATION IS 98.2%
> ```
>
> **Two findings that reframe the whole slice.** Retrieval is FREE, so every
> knob above is a QUALITY decision and any argued on latency was argued on a
> false premise. And **STUFF is not the cheap path** — it saves ~9 seconds of a
> two-to-eight-minute answer, while two STUFF runs of the same model on the same
> machine differ from each other by **282 seconds**. Generation time does not
> follow the path and barely follows prompt size.
>
> #### FOUR DEFECTS FOUND BY MEASURING, none on anyone's list
>
> thinking burn scored as a result (`papers` "answered 0 of 20" was the model
> running out of output tokens mid-sentence, and `ask()` discarded
> `finish_reason`) · the rerank chain missing its second Google account ·
> a 500 never retried · and `VECTOR_TOP_N` declared TWICE in one module, the
> second shadowing the first.
>
> **THE FIVE-WAY RULE IS NOW SIX-WAY.** *"400 / 500 / empty / timeout → next
> tier"* is FALSE for Gemma and it is measured: **gemma-4-31b answers 500 on two
> calls of three and 200 on the third.** That rule was discarding the largest
> quota in the project over a fault that clears in three seconds.
>
> #### WHAT IS DELIBERATELY LEFT OPEN
>
> | | why |
> |---|---|
> | **GENERATION TIME** | the whole clock, and unsolved. **Step 2 owns it** — see the Step 2 block above |
> | content-kind filtering | parked for a final pass |
> | merged vs per-side rerank | per-side ships on the structural-coverage argument, not on evidence |
> | how many chunks to SEND | a GENERATION property; `recall@N` is monotone and cannot have an optimum |
> | a fourth language | 20 corpora beats 13, and is still one zoo |
> | `scripts/answers/score_answers.py` retry loop | re-asks a spent quota five times; burned five hours on 2026-09-19 |

> ### ⚠ SLICE 8 WAS RE-RUN TWICE. READ `docs/slice8v2/` BEFORE ANY NUMBER BELOW
>
> **`docs/slice8/` is the FIRST run — three corpora, two of them already used.**
> **`docs/slice8v2/` is THIRTEEN corpora, nine languages and formats, 286
> queries, and it CORRECTS the first run in several places.** Start at
> `docs/slice8v2/RESUME.md`, then `DECISIONS.md`, then `FINDINGS.md`.
>
> **The third session, 2026-09-17, began by finding the MEASUREMENT INSTRUMENT
> BROKEN.** `PairScores` synthesised a score from a LISTWISE reranker's ORDER —
> `len(order) − place` — and cached it per pair, so every call produced the same
> numbers 50…1 and two calls for one query collided. **Five of thirteen rerank
> corpora and all three merged benchmarks were void.** It does NOT reach
> production: nothing in `labpilot/` outside `rerank/contracts.py` reads
> `.scores`. See `docs/slice8v2/FINDINGS.md` **G14**.
>
> **What the third session settled, and what it overturned:**
>
> | | |
> |---|---|
> | **how many chunks to SEND** | **20**, and N is a **COUNT**, not a coverage share — cv 0.41 against ~1.0 over a 15× range of corpus sizes. **CORRECTED**: the experiment picked its chunks by VECTOR SEARCH ALONE - `chosen()` uses `dense_orders` and no reranker touches it - so it measures the DEGRADED path directly: **`VECTOR_TOP_N` should be 10 per side, not 25**. `RERANK_TOP_N` is NOT measured by it. Reranked chunks are better ordered, so their optimum is at most 20 and may be lower - an argument, not a number |
> | **the skip gate** | **`SKIP_MARGIN` stays `None`.** The v2 run's `0.05` is OVERTURNED: the best GLOBAL tau is worth **+2.4 queries out of 286**, and the best per-corpus tau is never the same twice |
> | **merged vs per-side reranking** | **PER SIDE, confirmed.** Merged starves a side entirely on **43 of 57** queries — where the broken instrument had reported **0 of 20** |
> | **fusion** | switch the keyword channel **ON below `r@50` ≈ 0.95 and OFF above** — every recall gain lands on the three corpora below it, and every corpus at or above is exactly +0.000. And the method is **SCORE FUSION**, not wRRF, whose entire MRR range sits inside one-query resolution |
> | **the routing signal** | **DEAD.** Weighted over 286 queries every question kind is POSITIVE. `structure` — slice 6's −0.534, which became a design principle — is **+0.169**, and its worst case was **one query** scored −0.500 |
> | **reranking** | still ships, restated against each fixture's RESOLUTION: **9 REAL gains, 1 REAL loss, 3 nothing measurable**. "Helped 10, hurt 3" overstated both sides |
> | **chain 3's order** | **rests on ONE corpus.** On three more, Cohere beats flash-lite 2–1 and has never hurt a corpus, while flash-lite hurts on 3 of 13. Their means are +6.0q and +6.1q — indistinguishable. Flash-lite belongs first for **budget** (1,000/day against 1,000/month), not for quality, and **Cohere does not belong at tier 7** |
> | **the splitter decides the rerank tier** | a language with no AST splitter gives chunks ~2× larger, so one rerank call is ~2× the tokens. At `SEARCH_LIMIT = 50` **Voyage serves 0 of 13 corpora and both Gemma tiers serve 4 of 13**; at a window of 30 Gemma serves **all 13** — 28,800 calls a day against Flash-Lite's 1,000. `scripts/retrieval/tier_reach.py` |
>
> **THE ONE METHODOLOGICAL RULE THIS SESSION EARNED, because the same error
> produced three different wrong conclusions:**
>
> > **Print the DENOMINATOR beside every ratio, and judge a delta against what
> > the fixture can RESOLVE, not against zero.** One query is 0.042 MRR on the
> > 12-query `docx` and 0.011 on the 45-query `geo`.
>
> ```
> top-N      USED at N=5 over <3 answerable questions  ->  "the best N is 5"
> reranking  an MRR delta on 13 queries beside one on 45  ->  "helped 10, hurt 3"
> routing    a per-kind delta with ONE query in the kind  ->  structure = -0.534
> ```
>
> **✅ FIXED 2026-09-27 - see the Google embed block at the top of Current Status.**
>

> **History of that pair of defects (both RESOLVED 2026-09-27).** Slice 8 recorded two
> production defects here. (1) `MAX_BATCH_SIZE = 96` was a **Mistral** constant with a global
> name, so a 96-text Google batch (~32,800 tokens against a 30,000/minute ceiling) was
> refused on the **first batch**; `embed_batches()` halved only on a refusal naming *tokens*,
> which Google's does not. Decision A8 had shipped `SMALL_CORPUS_CHUNKS = 500`, routing every
> small corpus to Google first, so the shipped routing could not finish an ingest. (2)
> `embedding_minutes()` counted HTTP calls where Google counts TEXTS, reporting ~118 minutes
> for a 10,000-chunk Google ingest against a truth of **ten days**. The fix first existed only
> in `scripts/setup/warm_embeddings.py`, which hid the product's defect. Both are now fixed in the
> product (the text budget by `daily_text_budget`, the batch by `max_batch_size` plus pacing —
> see the Google embed block above), and the script's private copy was deleted on 2026-09-28.


### Older status notes

The dated session notes (2026-08-11 to 2026-09-28), the old "START HERE" layers (the slice 4, slice 7 and
slice 8 eras, with their now-obsolete "next task" lines) and the "where the code stands at the end of session 3"
list were moved word for word into [DETAILS.md](../archive/README.md) (section "Current Status"). Everything in them that
still matters is in the sections below or in the Step 2 plan.

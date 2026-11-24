# Full text: Current Status

[Docs home](../../README.md)

## Current Status

**Status of 2026-11-24 (routing made fast): the fix of the slow runs is built, tested (2,488 unit and api tests, 191 database tests) and measured in the scratch copy l3 (files in `artifacts/slice11-waits/l3/`): a race between models inside each call, a memory of bad providers, quick-and-nearly-as-good models first (D130 to D133). The worst case takes about 4 minutes with quotas and 4 to 5.5 minutes with most daily quotas empty; under 5 minutes always is NOT proven. The repository has none of it and nothing is committed. See [section 33.7](../../step2/33-slice-11-routing.md#337-routing-made-fast-the-race-the-memory-of-bad-providers-and-the-new-order--2026-11-24).**

**Status of 2026-11-23 (routing, streaming and the wait rules): streaming was tested live on every provider and fixed, and the wait and retry rules were chosen from 497 measured calls (D129: 10 s for the first piece, 15 s of silence, no retry of a 503, one retry after 1 s of another fast failure). All of it is in the scratch copy l2 only (a copy is in `artifacts/slice11-waits/`); the repository has none of it and nothing is committed. Google was overloaded, so arms A, B and C were not compared. See [section 33.6](../../step2/33-slice-11-routing.md#336-streaming-its-wait-limits-and-the-retry-rule-tested-and-measured--2026-11-23).**

**Status of 2026-11-21 (routing, lesson 2 and the tools): lesson 2 (one computed route for every task, the bench of every model on every task) is built and measured in a scratch copy and handed to the user to type; the repository does not have it yet. `scripts/` was reorganised into folders by job, and the measuring tools are in `scripts/routing/`. Nothing is committed. See [section 33](../../step2/33-slice-11-routing.md#33-slice-11-lesson-2-one-computed-route-for-every-task-and-the-tools-that-keep-it-up-to-date--2026-11-20-and-21).**

**Status of 2026-11-19 (routing, lesson 1 DONE): the user typed lesson 1 on branch `feat/routing` (made from `feat/stored-summaries`): the spreader (rooms, skip a busy tier, no waiting), the retry rule of 1 s and 3 s, the stop of a hung call, and the labels on the tiers. It is checked and tested: 329 tests of `tests/unit/llm` and the four api and script test files that touch it pass, 8 deliberate breaks were all caught, `ruff` is clean. The full suite was NOT run. The routes (`labpilot/llm/routes.py`) and the wiring are lesson 2 and are not in the repository yet. Nothing is committed. See [section 31.22](../../step2/31e-spreader.md#3122-routing-lesson-1-typed-checked-and-tested--2026-11-19).**

**Status of 2026-11-16 (the spreader and the routes): the spreader and one route for each of the 20 tasks are built and tested in a scratch copy ([section 31.20](../../step2/31e-spreader.md#3120-the-spreader-and-the-routing-chain-built-in-a-scratch-copy-2026-11-16-lesson-1-follows-the-repository-has-none-of-this-code-yet)); the repository has none of that code yet and nothing is committed. The rules (D112 to D116): a tier is asked again after 1 s and after 3 s and then the walk goes to the next tier at once; a busy tier (a full minute room, one call already open, an account that must rest) is skipped and never waited for; every task has its own route with the stop of a hung call; the tiers that may be read by the provider (Token Harbor) are left out by default. NEXT: the user types lesson 1 (the spreader), then lesson 2 (the routes and the wiring); the Gemma models on Google are measured again.**

**Status of 2026-11-16 (the measurement): every model was measured for speed and trust ([section 31.19](../../step2/31d-model-measurement.md#3119-the-measurement-of-every-model-speed-trust-long-prompts-and-hidden-limits--2026-11-16)): 71 models, five calls each (100, 200, 500, 4,000 tokens and one long prompt of up to 20,000), no timeout and no output limit of ours. 64 models are trusted by the rule (4 of 5 valid) and 7 are not. The input length changes the speed very little (median 3.8 s at 100 tokens, 5.0 s at 20,000). The hidden limits found: Mistral allows 2 requests a minute for each model (and Nemo is Ministral 8B), Requesty takes one request at a time, Cloudflare GPT-OSS 120B stops at 256 output tokens when no limit is sent, LiteRouter wants 7 s between the starts of two messages, Gemini 3.8 Flash needs 155 to 579 s, and one Token Harbor call hung for 40 minutes. Everything is in `artifacts/slice11-measure/results.jsonl`. The registry was NOT changed and the spreader copy is still in the scratch folder. NEXT: the user decides the chain changes of 31.19, then the routing design.**

**Status of 2026-11-16 (later): TOKEN HARBOR IS IN THE CHAIN (section 31.17). Its four `:free` models (DeepSeek V4.1 Flash, DeepSeek V4 Flash, MiMo V2.6 Flash, MiMo V2.5) answered 20 of 20 calls in 2.8 to 7.3 s. Its own FAQ gives 60 requests a minute and 1,800 an hour per account, no limit on concurrent requests, and a value-based free allowance on a rolling 7 days whose size is not published. `CHAIN` has 112 tiers. These four are for small jobs only, because staff may read free-route conversations and the providers may train on them. The key variable is `TOKEN_HARBOR_API_KEY`. Nothing is committed.**

**Status of 2026-11-16: the first job of the rest of slice 11 (the chain cleanup) is done and the ROUTING GUIDE is written ([section 31.18](../../step2/31c-routing-guide.md#3118-the-routing-guide-tasks-limits-of-every-provider-and-what-can-serve-what--2026-11-16-the-basis-of-the-routing-design-of-slice-11)): the 18 tasks with difficulty and call counts, the limits of every provider, and what each provider can serve. Nine LiteRouter tiers and two more (Beam on Cline, Ling on Kilo) are in `KNOWN_DEAD` (36 names), Gemini 3.7 and 3.5 Flash left the chain (Google redirects them), a new category `NOT_TRUSTED` (9 tiers since 2026-11-17: the three Google Gemma 4 31B tiers, the four OrcaRouter ones and both Muse Glimmer routes) sits at the end of the chain, and Hy4 preview (OrcaRouter) joined after a 5-of-5 test; `CHAIN` has 112 tiers (108 until Token Harbor joined, 2026-11-16). Nothing is committed on `feat/stored-summaries`. NEXT: design the routing table from 31.17 and 31.18, starting with the room spreader (D70).**

**Status of 2026-11-15: D110 (the first job of slice 11) is BUILT, measured and mutation-checked ([section 31.16](../../step2/31b-slice-10-built.md#3116-d110-is-built-the-summaries-and-the-gate-verdict-are-stored--2026-11-15)). The two summaries are made when a file is uploaded and stored in `saved_results`, and the gate verdict is made at the first question that has both files and stored too. A question about a stored pair now makes 2 model calls instead of 5. The gate stays AFTER the planner (the plan is read by `halted()`). The branch is `feat/stored-summaries`; nothing is committed. The rest of slice 11 (routing, the chain cleanup, the fast chain for a chat question) is NOT started. The real database had no `saved_results` table until `create_schema` was run on 2026-11-15, so D104 never saved anything there before.**

**Status of 2026-11-14: slices 0 to 10 of Step 2 are DONE (slice 10 closed: sections 31.11 to 31.15). Slice 10 was REDESIGNED on 2026-11-12 ([section 31](../../step2/31a-slice-10-design.md#31-slice-10-redesigned--2026-11-12)): there is NO `extract_outcomes` node and NO comparability node (D108); instead the timer (S1, 08d16b4), the COMPARABLE sentence, the ask-the-user pause (D109, B), and ONE planner change with four choices (D107): `ask`, `about`, `files` and `fresh`, used by the graph (a chat question and a one-file question run less; `fresh` adds one new check of B, D111). Lessons 1 to 5 are typed by the user and the tests are in the repository; the full suite on the repository was NOT reported by the user when this was written (the scratch build gave 2279 passed, 0 failed), so run `python -m pytest tests -q` once. Nothing of slice 10 is committed yet. C of D109 (ask while the agent works) stays in Step 3; D110 (summaries and the gate verdict stored) was built at the start of slice 11 on 2026-11-15 (31.16). **Next: the rest of slice 11 (routing).**

**Phase: STEP 2 HAS STARTED — 2026-09-22. STEP 1 IS COMPLETE AND CLOSED; ALL
NINE SLICES — 1, 1b, 2, 3, 4, 5, 6, 7 AND 8 — ARE DONE, AND SLICE 8 RAN THREE
TIMES (v1, v2, v3). STEP 2 IS NOW PLANNED AS FOURTEEN SLICES (0 TO 13, REWRITTEN 2026-10-14, SEE SECTION 21); SLICES 0, 1 AND 2 ARE DONE:
read [STEP 2 — the plan](../../step2/00-plan.md#step-2--the-plan-recorded-2026-09-22) before anything
else, because it OVERTURNS this file in two places — no findings score has ever
been measured on the search path, and the planner cannot use `build_context`.**

**UPDATE 2026-10-19: slices 3 and 4 are DONE.** Slice 3 (`summarize` for A and B at the same time, and the split of `api/services.py`) is in 17.16 to 17.18. Slice 4 (the planner: function calling, the planner node, the check in code, tool calls in the LLM layer, the real planner, and a map with signatures) is in 17.19 and 17.20, and the closing review of slices 3 and 4 is in 17.21. The planner and the summarizer are not wired into `ask()` yet (slice 5). The next job is slice 5, run the plan. **Slice 5 is IN PROGRESS: lesson 1 (`Send`, a fan-out whose size is decided while the program runs) is DONE on 2026-10-19 (17.22), on the branch `feat/plan-to-run` (made by the user from `main` at `0ac80d4`, commit `00cb059`, the toy file of lesson 1). Lessons 2 and 3 are next.**

**936 passed, 87 skipped (82 smoke + 5 environment), ruff clean - measured
2026-09-28, just before the three fixes in
[section 12.6](../../step2/12-planner-map.md#126-three-small-debts-closed--2026-09-28).** The RAG system ingests a
file, a `.zip` or a git URL; stores it in pgvector; and answers a question by
stuffing when the pair fits and by search + fusion + gate + rerank when it does
not. Every constant in that sentence was measured — see
[STEP 1 IS CLOSED](../../status/history.md#-step-1-is-closed--2026-09-19-all-nine-slices-measured-and-shipped)
for the numbers and the four defects measuring found.

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
[Jev, the decision model](../../llm/jev.md#jev--the-decision-model-and-the-first-paid-tier-2026-09-19)
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
> **Read [the Step 2 time block](../../agent/design.md#agent-design--step-2-recorded-2026-08-11)
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
> tiers · exact search, no index.** `test_the_three_top_n_numbers_keep_their_order`
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
> **⚠ AND THE TWO PRODUCTION DEFECTS ARE STILL UNFIXED — one now breaks a
> SHIPPED decision.** `MAX_BATCH_SIZE = 96` is a **Mistral** constant with a
> global name, so a 96-text Google batch is ~32,800 tokens against a
> 30,000/minute ceiling and is refused on the **first batch** — while
> `embed_batches()` halves only on a refusal naming *tokens*, which Google's
> does not. **Decision A8 shipped `SMALL_CORPUS_CHUNKS = 500`, routing every
> small corpus to Google first, so the shipped routing cannot finish an
> ingest.** And `embedding_minutes()` counts HTTP calls where Google counts
> TEXTS, reporting ~118 minutes for a 10,000-chunk Google ingest against a
> truth of **ten days**. The fix already exists — **in
> `scripts/setup/warm_embeddings.py`**, which batches by tokens and paces by texts,
> so the instrument's private workaround hides the product's defect.

**SLICE 8 WAS MEASURED 2026-09-16 and it overturned TWO of this file's own
headlines. Read [SLICE 8 — MEASURED](../../step1/measurements.md#slice-8--measured-2026-09-16-step-1-is-complete),
`docs/slice8/RESULTS.md` and `docs/slice8/FINDINGS.md`.**
**A THIRD FIXTURE was built first and is why the run was worth doing:
`golang/geo` at `b200a11` — Go, computational geometry, 729 chunks, 45
interleaved queries, and the FIRST corpus where vector `r@50` is not
saturated (0.867). Both older corpora are Python and one of them is full.**
**FUSION: slice 5 is OVERTURNED. Every one of 30+ wRRF settings improved
`r@50` on geo (best +0.067); slice 5's "not one setting improved it" was a
statement about two SATURATED corpora. The keyword channel switches ON.**
**RERANKING SHIPS, led by `gemini-3.5-flash-lite`: MRR 0.526 -> 0.759 on geo
(+75% of headroom) and 0.646 -> 0.791 on requests. `bge-reranker-base` is
DELETED — worse than not reranking on three corpora.**
**SLICE 6's "ROUTING SIGNAL" DOES NOT REPRODUCE. It was a fingerprint of
`bge`, not a law: with flash-lite there is NOT ONE negative category on
either corpus, and `structure` went from -0.534 to +0.201.**
**EXACT SEARCH STANDS, and the question is CLOSED. Server-side exact is
2.9 / 6.1 / 11.3 ms at 335 / 729 / 1,387 rows on the REAL Supabase instance —
against a 350 ms network round trip and a 52,700 ms report.**
**✅ BOTH FIXED since - the text budget by `daily_text_budget`, the batch by
`max_batch_size` + pacing on 2026-09-27.**
**⚠ TWO PRODUCTION DEFECTS FOUND, both unfixed. `MAX_BATCH_SIZE = 96` is a
MISTRAL constant with a global name, so every Google embedder fails on its
FIRST batch; and GOOGLE COUNTS ONE TEXT AS ONE REQUEST, so it can embed
1,000 CHUNKS a day, not 96,000 — which disqualifies it for any real
repository whatever its recall.**
**`codestral-embed` STAYS PRIMARY, and not because it wins: no embedder wins
on all three corpora and the averages are within 0.013. It stays because it
is the only strong one that can actually ingest 10,000 chunks.**
**PIECES 1-3 SHIPPED 2026-09-14 on `feat/selector`: the rebuilt embedding-time estimator, `ingest_artifact()`, and `POST /api/v1/artifacts`. PIECE 4 - THE ASK PATH - IS NEXT, and every decision it needs is already taken in [section 10](../../step1/ask-path.md#10-the-ask-path--decided-2026-09-14-before-piece-4-was-written).**
**SLICE 6 IS FINISHED 2026-09-11. `labpilot/rerank/` is the seventh package: four cross-encoder
tiers proven live, an LLM reranker that takes a CALLABLE so the package still never imports `llm/`,
the margin gate in `retrieval/`, and a chain that ends in `skip` instead of an exception.**
**CHAIN 3'S ORDER IS MEASURED NOW, not argued from quota shape - the four LLM tiers lead it and
beat every purpose-built cross-encoder. Two tiers were DROPPED for measuring below vector alone.**
**SLICE 6 IS BUILT, MEASURED AND DELIBERATELY NOT SWITCHED ON, 2026-09-11. `labpilot/rerank/` is
the seventh package and the fifth adapter: three cross-encoders proven live, a chain that ends in
`skip` instead of an exception, and the margin gate in `retrieval/`. Nothing calls any of it -
which is what "off" means, exactly as slice 5's keyword channel is off.**
**THE MEASUREMENT SAID SOMETHING NOBODY PLANNED FOR: with `bge-reranker-base`, RETRIEVAL GETS
WORSE. Four runs, two corpora, two embedders - r@10 0.933 -> 0.711 and MRR 0.646 -> 0.476 on the
45-query corpus. Headroom captured: -100%, -infinity, -500%, -86%. The best skip-gate threshold is
the one that NEVER reranks, on 3 of 4 runs. See
[slice 6 DONE](../../step1/reranking.md#slice-6--done-2026-09-11-built-measured-and-not-switched-on).**
**AND THEN IT FLIPPED. A BETTER RERANKER HELPS, CLEARLY. Same corpus, same 30-document window,
same instrument - only the model changed: `rerank-3-lite` took r@1 from 0.412 to 0.588 (+43%
relative) and MRR from 0.608 to 0.725, where `bge-reranker-base` took them DOWN to 0.353 and 0.520.
The spread between two rerankers is THREE TIMES the headroom this slice was chasing.**
**NINE RERANKER CONFIGURATIONS SCORED, and CONFIG MATTERS AS MUCH AS MODEL: flash-lite TUNED 0.799
· gemma-4-31b TUNED 0.732 · Voyage 0.725 · flash-lite UNTUNED 0.706 · Cohere 0.669 · VECTOR ALONE
0.608 · bge 0.520 · local MiniLM 0.472 · ministral-3b 0.440.**
**TWO OF THOSE ROWS ARE THE SAME MODEL, 0.093 MRR APART - a bigger gap than between flash-lite and
Cohere's purpose-built cross-encoder. Two settings did it, both measured: `thinking=None` (MEDIUM
costs 3x the latency and 930 tokens for an IDENTICAL answer) and a JSON responseSchema (gemma
45.5s -> 14.4s, and the reply stops being prose wrapped around an answer). `GeminiProvider` now has
`generation_config`, the Gemini twin of `extra_body`, which Step 2's claim extraction also needs.**
**THE TWO BEST RERANKERS ARE NOT IN CHAIN 3 AT ALL, and its last tier is worse than not reranking.**
**A strong LLM beats two of three purpose-built cross-encoders; a 3B LLM loses to all of them; two
old cross-encoders lose to not reranking at all. Cross-encoder vs LLM, local vs API, free vs paid -
every one of those lines has winners and losers on BOTH sides. Only "is the model good at reading
code" separates them.**
**`gemini-3.5-flash-lite` IS THE SURPRISE AND IS NOT IN THE CHAIN: 500/day, no 50-document ceiling
(the exact thing that disqualifies Voyage), and it beats Cohere's purpose-built cross-encoder.**
**GEMMA WAS WRONG TWICE AND BOTH WERE MINE. "Cannot follow the format" was MY PARSER reading its
prose reasoning instead of its final answer. "Too slow at 95s" was a MISSING JSON SCHEMA - with one
it is 14.4s and scores 0.732, second best of everything measured, on the largest quota in the
project. The user refused both conclusions and was right both times.**
**The live trade for slice 8 is no longer quality, it is LATENCY AGAINST BUDGET: flash-lite is best
AND fastest on 500/day; gemma is second and 11x slower on 14,400/day. `verify` needs one call per
claim, so ~30 claims is 40s against 7 minutes. QUOTA IS NOT THE ONLY BUDGET.**
**THAT TAKES AWAY THE CHEAP ANSWER TO STEP 2's COST PROBLEM. The local model is the ONLY reranker
that batches - no rate limit, no call count, every pair in one forward pass, which is exactly what
`verify` needs at one call per claim - and it is also one of the two that make retrieval worse. A
NEWER local model (bge-reranker-v2-m3, the Qwen3 rerankers) is the open move, and was not tried.**
**SO "DOES RERANKING HELP" IS NOT A QUESTION ABOUT RERANKING. It is a question about one model, and
the candidate chain order recorded in the slice 6 theory - local, Cloudflare, Voyage, Cohere - would
have put the one model measured to HURT retrieval at the front. Chain 3's order is now a QUALITY
question with evidence behind it, and Cohere, the current primary, is still unmeasured.**
**The gain lands exactly where theory says it must: r@10 does not move at all and r@50 cannot, so
all of it is ORDERING INSIDE THE WINDOW. A run showing r@10 improve would mean a broken measurement.**
**THE GATE INVERTS TOO: with a bad reranker the best threshold never reranks; with a good one,
"always rerank" is within noise of the best row. `SKIP_MARGIN` stays None for the second reason.**
**MEASUREMENT 2 WAS MIS-SPECIFIED AND NO RUN COULD HAVE FIXED IT: `recall@N` only rises with N, so
retrieval can find where MORE stops helping and NEVER where FEWER starts. The stopping point is a
GENERATION property. What the frontier did settle for free: vector-alone goes flat at ~15 on
requests and ~5 on quora, so N in {20, 50} is ELIMINATED and generation only has to choose among
{3, 5, 10, 15}. And it is TWO numbers - RERANK_TOP_N and VECTOR_TOP_N - because the two paths have
different recall curves.**
**⚠ THE FLIP RESTS ON ONE CORPUS - the SATURATED one. The `requests` run was STOPPED at 8 of 45 to
protect Voyage's ONE-TIME 200M grant (an hour of wall clock at 3 RPM). Those 8 are all `constant`
queries, because `queries.json` is grouped by category - so they confirm the ROUTING finding a
second time and say nothing about the overall picture. SLICE 8 owes the full run, with Cohere.**
**A FIXTURE ORDERED BY CATEGORY CANNOT BE TRUNCATED: the first k queries are a category study
wearing a corpus study's clothes.**
**THE FINDING THAT OUTLIVES THE NEGATIVE RESULT: reranking WINS on `constant` questions (+0.186 MRR,
beating both vector 0.354 and BM25 0.423 at 0.540) and COLLAPSES on `structure` (0.926 -> 0.392) -
the SAME split slice 5 measured for BM25. A cross-encoder and a keyword ranker are both LOCAL
relevance models; a whole-chunk embedding answers a different question. That is a ROUTING signal,
and it is now the third independent measurement pointing the same way.**
**ONCE A RERANKER RUNS, THE EMBEDDER ALMOST STOPS MATTERING: reranked scores were identical to three
decimals across codestral and google. So slice 8's rule "rank embedders on recall@10" holds ONLY
while reranking is off; with it on, rank on recall@50 alone.**
**MEASUREMENT 4: slice 5's `wRRF` gain REPRODUCES (MRR 0.662 vs vector's 0.646) and then VANISHES
under reranking (r@10 +0.000). Fusion and reranking cannot be decided separately.**
**THE r@1 / MRR CONFUSION IS SETTLED: `0.645` was the MRR. True r@1 is 0.412-0.533, so the top slot
is wrong about half the time - a bigger gap than this file claimed.**
**TWO VOYAGE FACTS IN THIS FILE WERE WRONG, both fixed from its own dashboard. A card-free
account gets 3 RPM and 10K TPM, not "4M TPM / 2,000 RPM" - that was the BILLED tier. And the
free 200M-token grant covers "Voyage series 3 models", so the `rerank-2.5-lite` this file chose
on 2026-08-11 was never covered by it. THE REGISTRY NOW USES `rerank-3-lite`, proven live.**
**The 10K TPM is per-minute and counts a call WHOLE, so a 50-document call (~16,900 tokens) is
REFUSED however long you wait - 40 refused, 30 passes. Voyage cannot serve SEARCH_LIMIT at all
on a free account: the Groq shape, alive but unreachable for the real request size.**
**`scripts/retrieval/score_rerank.py` repeats the whole measurement and VALIDATES ITSELF: it proves the
cross-encoder is pointwise (drift < 1e-6) before trusting its per-pair cache, and reports that r@50
did not move. 654 passed, 32 skipped, 1 xfailed. 14 of 14 mutations real, 12 firing alone.**
**The reranker CANNOT batch across queries: no provider's `query` field takes more than one string,
and `s(q,d)` does not factorise. Embedding CAN batch and already does (96/request). So `N` claims
cost `N` rerank calls — and the only way to batch is to RUN THE MODEL YOURSELF, which is what makes
the local ONNX model structurally different from every API tier, not merely cheaper.**
**THE CHAIN 3 ORDER STAYS (the user's call). A candidate order with evidence is recorded for slice 8.**
**STEP 2 DESIGN CHANGED 2026-09-09: the code-vs-code CHECKLIST IS MACHINE-LEARNING VOCABULARY and
breaks this file's own "LabPilot is not MLPilot" rule. Queries are to be GENERATED by a cheap tier
from a FIXED, VERSIONED instruction with the checklist as a hint - and the generated queries MUST be
logged beside the report, because the chain falls back and a different model writes different
queries. It must be MEASURED against `EXPECTED.md`, not assumed. See
[the fixed checklist is domain-locked](../../retrieval/design.md#the-fixed-checklist-is-domain-locked--corrected-2026-09-09).**
**FAN-OUT is now complete: six sub-queries, ONE merged pile, ONE rerank against the ORIGINAL
question - and it applies to `answer_question`, NOT to `verify`, where N claims need N verdicts.**
**Two counting errors in this file are corrected: `r = 5` was the `verify` BATCHING number, not the
retrieval count (the real form is `r = N + 1`, `N` unknown until Step 2); and a rerank call is
~12,450 tokens, not 25,000, which roughly DOUBLES Voyage's and Cloudflare's real capacity.**
**Cohere bills per CALL up to 100 documents and we send 50 — half of every paid call is wasted.**
**SLICE 5 DECISION, 2026-09-07: VECTOR SEARCH SHIPS ALONE. No keyword channel on the query path.**
**Measured on TWO corpora x TWO embedders, 62 frozen queries, 82 fusion settings: the pipeline
retrieves 50 and reranks, so recall@50 is what gates what the model can see — and vector alone
is already at 123 of 124. NOT ONE fusion setting improved it on any run. The two fixtures
DISAGREED (RRF +15% MRR on quora, -13% on requests), which is why one fixture could not decide.
BM25 by hand beats both Postgres rankers and still loses to vector. wRRF with a SMALL k and a
SMALL weight is a NAMED CANDIDATE for slice 8 and may replace vector there. See
[slice 5 measured](../../step1/keyword-search.md#slice-5-measured--2026-09-07-vector-ships-wrrf-is-a-named-candidate).**
**SLICE 5 IS BUILT AND CLOSED, 2026-09-08: the tsvector column, `store/keyword.py` and
`retrieval/fusion.py` all exist, OFF BY DEFAULT — nothing calls them, which is what off means.
**Probing the real database before writing found THREE silent defects in the query the benchmark
used: a lexeme holding `:` CRASHED it, a URL token silently reinstated the AND that scored
0 of 17, and re-stemming an already-stemmed lexeme missed matches. `quote_literal` and
`'simple'` are the fixes. Keyword search costs ~1,022 bytes/chunk, +12% of a 1536-dim row.
See [slice 5 DONE](../../step1/keyword-search.md#slice-5--done-2026-09-08).**
**`data/samples/requests_http/queries.json` is the SECOND fixture — 45 queries over psf/requests
at `dae7ef6`, labelled by `asks` and `wording`. The corpus is NOT committed; fetch it.
`scripts/retrieval/score_hybrid.py` repeats the whole measurement and spends no generation quota;
`--sweep-bm25` varies the two BM25 knobs the original sweep never touched, and score
fusion, CombMNZ and ADAPTIVE were restored to it 2026-09-07 after being lost.**
**A query file now needs a `file` field: a repository has 19 files and line 186 is in most of them.**
**SLICE 4 SHIPPED EXACT SEARCH — the user's decision, 2026-09-05, with one named condition.**
**At the REAL target of 1k-10k chunks per artifact, exact is 7-34ms against a ~50s report, is
recall 1.00 BY DEFINITION, and costs 2.5x less storage. HNSW is faster and was measured on five
real repositories, but speed is not what we are short of. SLICE 8 RE-MEASURES IT on real
artifacts, and TIME is the only thing that can overturn it — not recall, not storage. See
[the final decision](../../step1/vector-store.md#the-final-decision--exact-search-ships-2026-09-05).**
**Step 1 is NINE slices: 1 · 1b · 2 … 8. Slice 4 (pgvector) is COMPLETE and MERGED into `main`.**
**The table, the WRITE PATH and EXACT SEARCH exist, proven against the real Supabase project.**
**`store/` is the sixth package: contracts · errors · defaults · schema.sql · connection · writer · search · keyword.**
**763 passed, 48 skipped, 1 xfailed, ruff clean — measured 2026-09-14, on `feat/selector`.**
**ALL 46 SKIPS ARE SMOKE (41) PLUS 5 ENVIRONMENT ONES. NOT ONE `database` TEST SKIPPED,**
**so the 54 store tests really ran. A `database` test is green-by-absence, so the skip**
**reasons must be READ (`pytest -q -rs`) before the count is believed.**
**⚠ THE ERROR BOUNDARY IS HALF CLOSED. Pieces 2-3 mapped `EmbeddingError` -> 503
`EmbeddingUnavailable`, and `NotConfigured` / `ConnectionFailed` -> 503
`StorageUnavailable` (503, never 404 — the database being down is OUR failure, not a
missing upload). `UnknownArtifact` and `ModelMismatch` are STILL named in
`ALLOWED_TO_ESCAPE`, because `search()` has no caller yet. PIECE 4 gives it one and
must take them off that list — see [the closing review](../../step1/vector-store.md#the-slice-4-closing-review--2026-09-05).**
**The FLAKY SUITE IS FIXED — THREE causes, all in the test fixture, none in `store/`:
a pooler reset threw away `set search_path` silently · a pooled connection was held per module ·
and every run shared ONE schema name, so two runs at once deleted each other's tables.
Verified with CONCURRENT runs, which is the case the first "20 green runs" never touched. See
[the flaky suite](../../step1/vector-store.md#the-flaky-suite-and-the-three-causes-behind-it--2026-09-0405).**
**HNSW IS NOT REJECTED, IT IS ON THE SHELF WITH ITS NUMBERS: `ef_search = 100`, 30-110x
faster at recall 1.00, measured on 81,493 really-embedded chunks from five real repositories.
`halfvec` and a partition-per-artifact are the shape to build IF slice 8 says exact is too slow.
SLICE 8's JOB GREW: embedder ranking + reranker ranking + **exact vs HNSW on real artifacts**.**
**~~OPEN DEFECT: `MAX_BATCH_SIZE = 96` exceeds Mistral's PER-REQUEST token limit~~ FIXED
2026-09-05 — `embed.embed_batches()` halves and re-sends on a refusal that names tokens,
and remembers the smaller size. Proven on the exact dask batch that failed: `embed()` alone
is refused, `embed_batches()` returns all 96 vectors in two requests.**
**~~⚠ THE SUPABASE INSTANCE WAS TAKEN DOWN 2026-09-05~~ IT IS BACK — verified 2026-09-13:
all 54 `database` tests RAN and passed, none skipped. The cause stands as a warning, not as a
live state: a 30k-row HNSW build with `maintenance_work_mem=512MB` killed it. Never size a
benchmark to the machine you wish you had — run that class of work on a LOCAL container.**
**Notebooks, PDF, Word and 58 code suffixes all ingest; every bad variant is refused, not stored.**
**The `mutation-test` skill EXISTS and FIRED — `.claude/skills/mutation-test/SKILL.md`.**
**⚠ CHECK THE EXIT ISP BEFORE ANY LLM WORK — see [the network precondition](../../rules/sources-and-network.md#network-precondition--check-the-exit-isp-before-any-llm-work).**
**Slice 4 calls NO model, so the ISP probe is NOT needed for it. A database is not a model.**
**`DATABASE_URL` now exists in `.env` — SESSION POOLER, port 5432. Direct connection is IPv6-only and DEAD from here.**
**Read [slice 4, the theory](../../step1/vector-store.md#slice-4--the-theory-recorded-2026-09-03) then
[slice 4, what is built](../../step1/vector-store.md#slice-4-first-half--done-2026-09-04-the-table-and-the-write-path).**
**CLINE IS THE EIGHTH PLATFORM AND NOW LEADS CHAIN 1 — `z-ai/glm-5.3-flash`, tier 1,
FREE and consuming ZERO CREDITS, proven against a paid control that deducted instantly.
`labpilot/llm/cline.py` unwraps Cline's `{"data": ...}` envelope; everything else is
reused. 22 tiers now. See
[Cline, the eighth platform](../../llm/gateways.md#cline--the-eighth-platform-and-the-free-tier-that-costs-no-credits-2026-09-13).**
**⚠ ITS QUOTA IS PUBLISHED NOWHERE AND IT SENDS NO RATE-LIMIT HEADERS, so the five-way
rule cannot tell busy from spent there and will retire the pool on the first 429. It is
the only tier in the project flying blind.**
**`reasoning.effort` is LOAD-BEARING on that tier, and it works BACKWARDS: without it the
model burns its budget thinking and Cline answers HTTP 500 `empty response content` —
2 of 5 runs succeeded without it, 5 of 5 with it. An explicit effort CAPS reasoning here.**
**Only 2 of Cline's 6 free models answer the API at all; the other four return 403
"only available via Cline product surfaces". `api/v1/models` is a 100% mirror of
OpenRouter's 445-model catalogue — measured, zero difference.**
**The Chain 1 table was REGENERATED from `CHAIN` — it had been left at the fifteen-tier
shape and was already missing every `(key 2)` twin from 2026-09-11.**
**LAGUNA S 2.1 IS TIER 9, placed on FOUR benchmarks and not one — the user refused a
single-benchmark decision and it moved the answer: on Terminal-Bench alone Gemini 3.6
Flash beats it, on SWE-Bench Pro the reverse, and the two cancel. It beats Nemotron 3
Ultra 2-0 and Flash-Lite 2-0, loses to GLM-5.2 1-2, so it lands exactly between tiers 8
and 10. 23 tiers now.**
**AND TIER 1 IS VINDICATED: `GLM-5.3 Flash` is #1 OF 42 ON TOOLATHLON and 0.843 on
Terminal-Bench. This file called its placement "a budget decision, not measured" — that
was too cautious.**
**⚠ FOUR of Cline's six free models answer 403 on EVERY call, and the chain treats 403 as
"next tier" — so a blocked model in CHAIN still produces a report while burning a request
per call, exactly how Gemma stayed broken for weeks. Now pinned by a test.**
**GLM-5.2 IS STILL DEAD but the refusal CHANGED: 403 `tier_not_allowed` code 1910, not the
old 429 with `limit: 0`. Cleaner for us — not retryable, never touches `dead_pools`.**
**⚠ THE BRANCH LINE BELOW WAS STALE AND IS CORRECTED: pieces 1-3 live on `main`,
re-committed piece by piece (~34 commits), NOT on `feat/selector`. That branch holds
an OLDER SQUASHED variant (`de3fef3`, `d8cf62e`) that `main` does not contain - the
same dead-branch shape as `feat/reranking` after slice 6. Do not resume there.**
**SECTION 11 RECORDS NINE OUTPUT-BUDGET DECISIONS taken 2026-09-14, four of them the
user's, two overturning claims this file already made - `max_tokens` vs
`max_output_tokens` is a GRID whose missing operator is `min()`; check 1 of
`_check_fits` rests on an assumption MEASURED FALSE on Mistral (200, not an error);
a thinking preset must restrict the CHAIN, not only the numbers; a scarce tier
belongs in an expensive chain and NEVER a cheap one; and reserving the strongest
tier for the report is an ASSUMPTION that session 10 already measured against. See
[the output budget](../../step1/ask-path.md#11-the-output-budget--nine-decisions-taken-2026-09-14).**
**`GEMMA_4_26B` IS NOW IN `llm/registry.py`. It was named in `LLM_RERANK_ORDER`,
measured second best of everything slice 6 scored, and existed ONLY inside
`tests/smoke/`, so no production code could build it. Limits read from
`GET /v1beta/models`: 262,144 in / 32,768 out, identical to the 31B. NOT in `CHAIN` -
whether it is a good GENERATOR is a separate question with no evidence yet.**
**SLICE 7 BUILD STEPS 1, 2 AND 3 ARE SHIPPED — `store/reader.py`, the outline
LADDER, and a selector that privileges NEITHER SIDE. 787 passed, 48 skipped,
1 xfailed, ruff clean. 11 mutations, 10 real. See
[section 14](../../step1/ask-path.md#14-slice-7-build-steps-1-3-are-shipped--2026-09-14).**
**TWO RECORDED DECISIONS WERE OVERTURNED BY THE USER: "fill A before B" is dead
(it leaves A UNCAPPED, so a large reference starves B to zero — section 13.2),
and the pre-rerank cut is now PER TIER rather than a global 25, because the cut
discarded exactly the queries reranking is best at while protecting a tier no
longer at the front of the chain (section 14.3).**
**`reserve()` HAD A 24,899-TOKEN OVER-ESTIMATE hiding behind the per-chunk
outline — it charged an id label for every chunk in the corpus, letting 4 of
8,333 chunks through instead of 266.**
**SLICE 7 IS CLOSED — 2026-09-15, after a review pass. SEVEN build steps, not
six: the REPOSITORY DOOR landed too, so `POST /artifacts` takes a file, a `.zip`
or a git URL, and `POST /compare` takes IDS. 843 passed, 4 skipped, 0 xfailed
across unit/api/integration, ruff clean. SMOKE STILL NOT RUN.**
**ONLY SLICE 8 — A MEASUREMENT — REMAINS IN THE WHOLE OF STEP 1. The page was
rebuilt for the two doors on 2026-09-15 and is no longer broken; the TypeScript
rewrite stays a STEP 3 job, deliberately.**
**THE REVIEW PASS FOUND THREE REAL DEFECTS, and the first is the worst: THE TEST
SUITE WAS SPENDING LIVE RERANK QUOTA ON EVERY RUN — four Gemini tiers and then
Cohere, whose free tier is 1,000 calls a MONTH and is the rerank primary. It hid
because `_best` takes its chain as a DEFAULT ARGUMENT captured at import time, so
monkeypatching the module attribute never reached it. Spending quota makes a
suite slower, never redder. See
[the review pass](../../step1/ask-path.md#16-slice-7-is-closed--the-review-pass-2026-09-15).**
**THE API ALSO LIED ABOUT COVERAGE: on the search path it reported `25 of 25` for
a 120-chunk corpus, because `Comparison` never carried the totals `ask()` had
already computed for the PROMPT. Fixed; the prompt and the response now agree.**
**THE USER FOUND TWO DEFECTS BY READING THE CODE, not by any test: `ModelMismatch`
left as unreachable when a re-ingest between measure() and search() makes it real
(now a 409), and the rerank chain BUILT BUT NEVER BOUND, so the ask path would
have used only the cross-encoders and never the four tiers that beat them.**
**Branch `feat/ask-path`, off `main`, clean and PUSHED — 21 commits ahead.
Last updated 2026-09-15 (twenty-fifth session).**
**⚠ A SESSION REWIND REVERTED TWO TEST FILES ON DISK at the start of this
session. Git still held the right versions; `git checkout --` restored them and
the count went UP, not back. If files look wrong after a rewind, check git before
rewriting anything.**
**⚠ SLICE 6 IS ON `main`, NOT ON A BRANCH. It was re-committed piece by piece (~40 commits),
not merged, so the hashes differ from `feat/reranking`. `main` is level with `origin/main`.**
**`feat/reranking` IS NOW BEHIND `main` AND IS DEAD — its only content difference is an OLDER
`tests/unit/llm/test_llm_layer.py`, which hardcodes three key names instead of deriving them
from `CHAIN` and has no second-account test. Do not resume work on it.**
**Session 19 wrote NO source: it taught slice 6 and verified the reranker budget from the
providers' own docs. 595 passed, 28 skipped, 1 xfailed, confirmed at the start of it.**
**SLICE 5 IS MEASURED AND DECIDED; the three pieces of code are NOT written yet —
see START HERE. Branch `feat/hybrid-search`, level with `main`.**

> ### START HERE IN A NEW SESSION
>
>
> > ## STEP 2 IS PLANNED, AND NOTHING IS BUILT — 2026-09-22
> >
> > **Read [STEP 2 — the plan](../../step2/00-plan.md#step-2--the-plan-recorded-2026-09-22) first.**
> > Twelve findings with their strength, nine decisions, five corrections,
> > eight slices, eight measurements owed and seven code debts. Branch
> > `docs/step2-plan`. **DO NOT COMMIT TO `main`.**
> >
> > **The four things that change what you would otherwise do:**
> >
> > ```
> > D1  PLAN-AND-EXECUTE is the MAIN shape (92% vs 85% completion, half the
> >     cost, the pattern for report generation with parallel steps), with
> >     exactly ONE bounded ReAct loop inside it (D4). Both are in the design
> > D2  THE PLANNER WRITES THE QUERIES from the user's question. They are NOT
> >     fixed, and extract_claims is one node it may choose, not the door
> > D3  REVISED BY D13: FUNCTION CALLING first, structured JSON text as the
> >     fallback - and ONLY for nodes whose output code reads. Prose nodes
> >     return plain text. See section 19.3
> > D7  agent/ is CORE, so it may not import llm/, store/, embed/ or rerank/.
> >     Nodes take INJECTED CALLABLES, exactly as LLMReranker does
> > ```
> >
> > **And two things in this file are now wrong:**
> >
> > ```
> > C3  NO FINDINGS SCORE HAS EVER BEEN MEASURED ON THE SEARCH PATH. 13 of 19
> >     was chunks sent: 96 of 96, and every partial run is dated 08-14 to
> >     08-16 - before pgvector existed. Step 2 has no baseline yet
> > C5  the outline the planner needs DOES NOT EXIST. build_context builds it
> >     from chunks already in hand, and the planner runs BEFORE retrieval
> > ```
> >
> > **SLICE 0 IS CLOSED - 2026-09-23. LANGGRAPH SHIPS.** ~55MB imported, no
> > torch, and the whole container measures **74 MiB under a 928-chunk repo
> > ingest** against CLAUDE.md's estimate of 290-370MB. **That estimate was 6x
> > wrong**, which also re-opens the local-reranker exclusion. **M3 is closed
> > too**: function calling works on 23 of the 24 tiers that answered.
> >
> > **Read [section 10](../../step2/10-slice-0-memory.md#10-slice-0-is-closed-and-the-memory-budget-was-6x-wrong--2026-09-23)**
> > for the numbers, the `git` defect, five measured gateway platforms, and
> > D14-D16.
> >
> > **Slice 1 IS MEASURED (2026-09-29/30) - read
> > [section 15](../../step2/15-slice-1-latency.md#15-slice-1-is-measured--every-tier-ranked-by-speed-2026-09-30)
> > and `docs/step2/slice1/RESULTS.md`.** The report-length probe was run too
> > (2026-09-30, [section 15.5](../../step2/15-slice-1-latency.md#155-report-length-measured-2026-09-30)): tier 1
> > wrote ~3,800 tokens in 120s AND in 24s, so the 400-500s reports of
> > 2026-09-19 are NOT reproduced and nobody knows yet why they were slow.
> > **Next is slice 2** (the skeleton - and it must ship a CHECKPOINTER and a
> > `thread_id`, per D15, or the product cannot have a second turn).
> > **2026-10-06: the decisions about chat memory, where to save it, and old
> > artifacts are in [section 17](../../step2/17a-chat-memory.md#17-chat-memory-storage-and-cleanup--decided-2026-10-06)
> > - read it before slice 2.** Artifacts are NEVER deleted today, and all chats
> > share one 500 MB.
> > **2026-10-07: SLICE 2, LESSON 1 OF 4 WAS DONE (lesson 2 followed, see the 2026-10-08 line below).** Read
> > [section 17.9](../../step2/17b-slice-2.md#179-where-we-stopped--slice-2-lesson-1-is-done-2026-10-07)
> > first: it says what the user already knows, which three answers were wrong,
> > and what lesson 2 must teach.
> > **2026-10-09: LESSONS 2 AND 3 ARE DONE. Resume at lesson 4.** Read
> > [section 17.10](../../step2/17b-slice-2.md#1710-lesson-2-was-taught-2026-10-08) (lesson 2: what the user knows,
> > both check questions answered), [section 17.11](../../step2/17b-slice-2.md#1711-lesson-3-was-taught-2026-10-08)
> > (lesson 3: what the user knows, the rule for reading a key) and
> > [section 19](../../step2/19-design-decisions.md#19-design-decisions-of-2026-10-08--made-while-teaching-slice-2-lesson-2)
> > (D29-D34 and clarifications: ReAct + plan-and-execute, where function calling is
> > used, the planner, one final node `respond`, the Effort and Strength controls, two
> > web search kinds).
> >
> > **2026-10-11: LESSON 4, PART 1 OF 3 IS DONE (TAUGHT AND RUN), AND D35 WAS DECIDED.** Read
> > [section 17.12](../../step2/17b-slice-2.md#1712-lesson-4-was-started-2026-10-11) first (what was taught, what the
> > user did not understand, the D19 check, D35) and
> > [section 20](../../step2/20-free-model-sweep.md#20-the-free-model-list-moves--the-sweep-of-2026-10-11) (the availability
> > sweep, the Gemini redirect, LiteRouter, and the chain of 73 tiers). The part 1 script
> > is committed (`5cb6388` on `main`, `4fb6b48` on `feat/agent-nodes`). As of 2026-10-12
> > `main` and `origin/main` are the same commit (`5cb6388`), `main` is the checked-out
> > branch, and the branch of lesson 4 is `feat/agent-nodes` (`4fb6b48`, also on origin).
> >
> > **2026-10-12: LESSON 4, PART 2 IS DONE.** Read
> > [section 17.13](../../step2/17b-slice-2.md#1713-lesson-4-part-2-was-done-2026-10-12) first: the conditional edge, the
> > real graph in `labpilot/agent/graph.py` that `ask()` now runs, the 5 decisions, the 12 new tests,
> > the 8 deliberate breaks, and the two rules the user set (they type ALL product code, and a step is
> > given WHOLE in one message). The full suite is 1113 passed and 115 skipped. The work is committed on
> > `feat/agent-nodes` (`74fb3b6`, `b1f4ba3`, pushed), three commits ahead of `main`. Next is part 3.
> >
> > **2026-10-14: LESSON 4, PART 3 IS DONE AND SLICE 2 IS CLOSED.** Read [section 17.14](../../step2/17b-slice-2.md#1714-lesson-4-part-3-was-done-and-slice-2-is-closed--2026-10-13-and-2026-10-14) first: the Postgres chat
> > saver, `thread_id` in the request and the reply, `durability="exit"`, the prune after each message, the closing
> > review (five real gaps in the prune query, a page that could forget the chat id, an unpinned package) and the 11
> > tests it added. The full suite without `--run-smoke` is 1151 passed and 115 skipped. Decisions D36 to D38. Everything was
> > replayed onto `main`, one file per commit. **Slice 3 is next.**
> >
> > **2026-10-14 (LATER, AFTER SLICE 2 WAS CLOSED): THE TABLES ARE LOCKED AND THE LESSON SCRIPTS MOVED.** Read
> > [section 17.15](../../step2/17b-slice-2.md#1715-after-slice-2-closed-the-lock-on-the-tables-and-the-examples-folder--2026-10-14): the
> > chat tables and the artifact tables got row level security (Supabase's web API sees nothing in them, and the
> > app is not affected), and the five lesson scripts moved from `scripts/` to `examples/langgraph/`. Six commits
> > on `main`, `d0492d4` to `6a32137`. `feat/agent-nodes` is now `b72955a`; it holds the lock as ONE commit, and
> > it also holds a docs commit that `main` does NOT have: `63a0381`, the reminder that better citations are owed
> > at the end of Step 2.
> >
> > **2026-10-14 (LATER STILL): THE FINAL STEP 2 DESIGN IS AGREED AND THE SLICE LIST WAS REWRITTEN (FOURTEEN
> > SLICES, 0 TO 13).** Read [section 21](../../step2/21-final-design.md#21-the-final-design-and-the-new-slice-list--agreed-2026-10-14) first:
> > the 10-step flow (the planner's queries are the front door, claims are a safety net, `find_missing` and
> > `find_bugs` cover problems in B alone, a merge step removes duplicate chunks), decisions D39 to D44, the map
> > from every planned node to its slice, and the size gate for big repositories. The new slice table is in
> > [section 4](../../step2/00-plan.md#4-the-slices--fourteen-since-2026-10-14-nine-before). **Slice 3 (`summarize` and parallel
> > nodes) is next.** Nothing in it is built.
> >
> > **2026-09-29: ROUTEWAY IS IN THE CHAIN — 54 TIERS, MERGED: `main`,
> > `origin/main` and `feat/routeway` are the same commit (checked with git
> > 2026-09-29; this line said "not merged" for a day after it was).** DeepSeek
> > V4 Flash and six Gemma 4 26B A4B community finetunes,
> > probed live first. Its free routes have HARD context caps (42,000 and
> > 62,000, over prompt PLUS output), so DeepSeek cannot serve a report. MiniMax
> > and Muse Glimmer were measured and left out. Read
> > [section 13](../../step2/13-routeway.md#13-routeway--probed-live-2026-09-29-and-what-the-limits-decided).
> >
> > **2026-09-29: JEV HAS A FREE ROUTE, THROUGH NETLIFY, LIVE.** OpenRouter
> carries our Jev calls on an unpaid balance ($0 credits), so a Netlify proxy
> now sits right behind it as rerank tier 4. See
> [section 12.7](../../step2/12-planner-map.md#127-jev-has-a-free-second-route-through-netlify--2026-09-29-live).
>
> **2026-09-28: THE PLANNER'S MAP IS BUILT (C5 is closed in code) and
> > `PLANNER_BUDGET` is 12,000, not 8,000.** Seven LiteRouter/OrcaRouter tiers
> > and a `KNOWN_DEAD` tail rule landed with it. **The suite was re-run
> > 2026-09-29 and is green: 941 passed, 96 skipped, ruff clean.** Every
> > GitHub secret the smoke workflow maps now exists. Read
> > [section 12](../../step2/12-planner-map.md#12-the-planner-map-is-built-and-its-budget-was-corrected--2026-09-28).
>
> > **2026-09-29: THE WEEKLY SMOKE RUN HAD BEEN RED FOR FOUR MONDAYS.** About
> > half of its 41 failures were not dead providers - a missing Voyage mapping,
> > missing Kilo and Requesty secrets, Google's own 503s, a spent Mistral quota
> > and a dead-tier list that had drifted from the registry. Fixed, and
> > committed by the user on 2026-09-29 (small commits, pushed); NOT YET RUN ON
> > GITHUB. Read
> > [section 14](../../step2/14-smoke-run.md#14-the-weekly-smoke-run-was-red-for-a-month--2026-09-29).
>
> > ## ✅ STEP 1 IS DONE — 2026-09-19. STEP 2, THE AGENT, IS NEXT
> >
> > **STATE, verified rather than remembered.** Slice 8 v3 landed on `main`;
> > the closing test pass is on **`feat/step1-closed`**. Suite
> > **871 passed, 4 skipped, 0 xfailed**, ruff clean both ways. Ask git for any
> > count rather than trusting a number here - it goes stale on the next commit
> > (`git rev-list --count main..feat/step1-closed`). **DO NOT COMMIT TO
> > `main`** - only the user does that, or when they say "merge and commit".
> >
> > **READ THE STEP 2 TIME BLOCK BEFORE DESIGNING A SINGLE NODE.** Generation
> > is 98.2% of a 497-second answer and it is the blocking problem of the whole
> > next step. Everything else below is history.
> >
> > **The four things the closing pass added, each mutation-verified:**
> >
> > ```
> > smoke        the weekly run drove the pipeline slice 7 REPLACED. It now
> >              drives ask() over a real corpus in Postgres, and the frozen
> >              baseline was cut from 4 generation calls to 1
> > unit         web/app.js reads fields off our replies and NOTHING checked
> >              the names - the drift that broke the page for a week
> > api          the skip gate was wired and nothing proved it, which is how
> >              the rerank chain and fusion both went unwired before
> > integration  fusion was proven in halves: bm25 on a real db, the wiring on
> >              stubs, and never the seam between them
> > ```
> >
> > **What the OLD block below describes is slice 7, kept for its reasoning.**
> >
> > ```
> > SLICE 8   a MEASUREMENT, not a build   - nine numbers, listed below
> > ```
> >
> > **THE PAGE IS FIXED, 2026-09-15.** It had posted two FILES to `/compare`
> > since that endpoint took ids, so it had been broken since slice 7. Each
> > slot now uploads on its own to `POST /artifacts` and keeps the id; the
> > question box sends `{a, b, question}` as JSON. It also shows what the API
> > already returned and the old page ignored: chunk count, embedder, the
> > embed-time estimate with `slow` as a warning, the artifact id, a git URL
> > field, and `sent/total` per side - so a searched side reads
> > `B: 25/1094 chunks searched` rather than `25/25`.
> >
> > **Still plain HTML, JS and CSS, ON PURPOSE. NO TypeScript, no build step.**
> > That is Step 3, and the state a typed app would model - sessions, chat
> > history, SSE progress, the 0/1/2-artifact modes - is Step 2 work that does
> > not exist yet. Typing state before it settles is the rewrite-twice trap
> > this file named when the page was first written.
> >
> > **It also got a visual pass the same day** - a brand mark, a gradient
> > wash, cards that REACT (accent border while reading, green with a check
> > mark when stored, red when refused), a real drop zone, semantic pills,
> > animated waiting dots, and a light palette that had never once been looked
> > at. Still one stylesheet, one script and inline SVG.
> >
> > **Two bugs the visual pass exposed, both found by LOOKING, not reading.**
> > `#status { display: flex }` BEAT the `[hidden]` attribute, so the loading
> > dots sat on the page before anything was asked - a display rule always
> > wins, and `[hidden]` is now forced off globally. And the two cards sat a
> > few pixels out of line because one hint wraps and the other does not.
> >
> > Driven end to end against a THROWAWAY STUB, so no embedder or model quota
> > was spent and no rows were written to the real database. Checked in dark
> > and light, at desktop and 375px.
> >
> > **⚠ THE BROWSER PANE'S SCREENSHOTS WENT STALE MID-SESSION** - `End`
> > changed nothing and the image showed a layout matching no real state. It
> > was caught only because the DOM disagreed with the picture: `/compare`
> > had returned 200 and `result.hidden` was false while the screenshot showed
> > no report. **Trust a DOM read over a screenshot**; closing the tab and
> > reopening fixed it.
> >
> > ### What slice 7 shipped, all six steps plus a seventh
> >
> > ```
> > 1  store/      measure + read back                            DONE
> > 2  prompts/    outline by FILE, as a LADDER                    DONE
> > 3  retrieval/  equal share + leftover (NOT A before B)         DONE
> > 4  api/        ask(): the ladder                               DONE
> > 5  api/        the rerank chain, assembled at the entry layer  DONE
> > 6  api/        /compare takes IDS, not files                   DONE
> > 7  api/        THE REPOSITORY DOOR - a file, a .zip, or a git URL   DONE
> > ```
> >
> > **Step 7 was never in the plan and is not recorded in sections 14-15.** It
> > landed in `a1415ca`: `POST /artifacts` now takes `file` **or** `url`,
> > `services.ingest_source()` stores a whole repository as ONE artifact, and
> > the old `MAX_ARCHIVE_BYTES` xfail became a real test when the limit moved
> > 50MB -> 10MB. That is why the suite has no xfail left.
> >
> > ### The review pass found THREE real defects — see [section 16](../../step1/ask-path.md#16-slice-7-is-closed--the-review-pass-2026-09-15)
> >
> > | # | defect | fixed? |
> > |---|---|---|
> > | 1 | **the test suite spent LIVE rerank quota on every run** - four Gemini tiers, then Cohere, whose free tier is 1,000 calls a MONTH | ✅ `tests/conftest.py` keeps the chain empty outside smoke |
> > | 2 | **the API reported `25 of 25` for a 120-chunk corpus** - the prompt told the truth and the response did not | ✅ `Comparison.totals` |
> > | 3 | **a dead line in `ingest_source`** - `replace(chunk, artifact_id=...)` changes nothing, because nothing reads `Chunk.artifact_id` | ✅ **removed 2026-09-28** |
> >
> > **Defect 1 is the one to remember.** It hid behind a Python detail: `_best`
> > takes its chain as a DEFAULT ARGUMENT, evaluated once at import time, so
> > monkeypatching the module attribute never reached it. A path that looked
> > stubbed was not, and **spending quota makes a suite slower, never redder**.
> >
> > ### NEXT IS SLICE 8, and it is a MEASUREMENT
> >
> > Its job list is NINE: embedder ranking · reranker ranking · exact vs HNSW
> > on real artifacts · end-to-end TIME · merged vs per-side reranking ·
> > `SEARCH_LIMIT` and `VECTOR_TOP_N` swept jointly · where the cut goes ·
> > whether the per-tier rerank window beats a global one · and whether
> > `explain_divergence` really needs the strongest tier, which section 11.9
> > says was already measured OUT as a cause of coverage.
> >
> > **Every number it sweeps is now a NAMED CONSTANT**, so a sweep changes one
> > number instead of a design:
> >
> > ```
> > SEARCH_LIMIT 50 · VECTOR_TOP_N 25 · RERANK_TOP_N 10 · SIDE_SHARE 0.5
> > OUTLINE_BUDGET 4,000 · per-tier max_documents · BM25_K1 · BM25_B
> > ```
> >
> > **SMOKE HAS NEVER BEEN RUN ON THIS BRANCH**, and it is the one thing this
> > session did not do. Check the exit ISP first - see
> > [the network precondition](../../rules/sources-and-network.md#network-precondition--check-the-exit-isp-before-any-llm-work).
> > `tests/smoke/test_pipeline_answers.py` still exercises the OLD pipeline
> > (`chunk_file` + `select` + `build_prompt`), never `ask()`, so the weekly
> > run does not touch what we now ship. Fixing that needs a database and
> > embedder quota, which is slice 8's end-to-end measurement anyway.
> >
> > ### Three traps that still bite, all already written down
> >
> > **The two number spaces.** `search()` returns `SearchHit.chunk_index`, an
> > ID in the corpus. `rerank()` returns POSITIONS into the list it was handed.
> > `hits[p]` is right; looking up chunk `p` cites the wrong file and line with
> > full confidence. Two test files number their ids from 100 so the confusion
> > is provable rather than plausible.
> >
> > **`skip()` truncates to whatever `top_n` it is handed**, so the cut must
> > happen AFTER the call and `rank()` must be asked for everything. Both
> > halves are pinned now; the second half was unguarded until 2026-09-15.
> >
> > **A fixture numbered from zero, or holding one chunk, cannot fail.** A
> > one-chunk file cannot tell a correct `start_line` from a lost one, and ids
> > starting at 0 cannot tell an id from a position. Both were found by
> > mutation, not by reading.
> > ## ✅ SLICE 4 IS DONE — do not restart it
> >
> > The table, the write path and **exact search** all exist and are proven
> > against the real database, and the index question is settled with numbers.
> > Read [the store](../../step1/vector-store.md#slice-4-first-half--done-2026-09-04-the-table-and-the-write-path),
> > [exact search](../../step1/vector-store.md#slice-4-step-2--done-2026-09-05-exact-search) and
> > [the final decision](../../step1/vector-store.md#the-final-decision--exact-search-ships-2026-09-05).
> > **Exact search ships; HNSW is on the shelf with its numbers**, and only
> > TIME measured on real artifacts at slice 8 can overturn that — not recall,
> > not storage.
>
> > ## ⚠ ONE DEBT SLICE 4 OWES BEFORE IT CLOSES
> >
> > ~~**1. CI never runs the database tests.**~~ **CLOSED 2026-09-04.** CI now
> > runs a **`pgvector/pgvector:pg17` service container**, not the real
> > project, and **no secret is needed** — so it works on forks too. A secret
> > was the obvious fix and is the wrong one: CI runs on every push, and two
> > concurrent jobs sharing one database would both
> > `drop schema labpilot_test cascade`, which is exactly
> > [the flake](../../step1/vector-store.md#the-flaky-suite-and-the-three-causes-behind-it--2026-09-0405)
> > reintroduced by concurrency. Verified locally against a real container:
> > **533 passed in ~15s**, against ~40s over the VPN to Supabase.
> > `test_ci_really_runs_the_database_tests` fails the build if the workflow
> > ever loses `DATABASE_URL` or the pgvector service — because a `database`
> > test **skips itself** when the variable is absent, so the suite goes green
> > while running none of them.
> >
> > **2. `services.py` still does not write anything.** `write_artifact` is
> > reachable only from tests. The `Chunk` + vector -> `ChunkRecord`
> > translation belongs in `api/services.py`, because entry is the only layer
> > allowed to import both `ingest/` and `store/`. That is slice 7 work, and
> > until then the store is scaffolding with a scheduled consumer.
>
> **The walking skeleton walks.** A real HTTP request now goes upload → chunk →
> select → prompt → `LLMClient` → an answer with its citations resolved back to
> real file and line numbers. Every box in the Step 0 diagram is touched.
>
> **⚠ FIRST, CHECK THIS — the exit ISP, before any call that spends an LLM or
> touches Google.** The work runs through a VPN, so the exit IP changes between
> sessions and Google refuses some exits. **Do not assume; probe.** The rule and
> the two commands are in
> [the network precondition](../../rules/sources-and-network.md#network-precondition--check-the-exit-isp-before-any-llm-work).
>
> **The 2026-08-20 Google outage is OVER, and it has now held across three
> different exits.** Measured 2026-08-27 on `185.254.96.11`, **AS58212
> dataforest GmbH**; measured again 2026-08-30 on `185.209.196.176`,
> **AS39351 31173 Services AB**, both Frankfurt.
> `gemini-3.5-flash-lite:generateContent` → **200** on both days, and
> `gemini-embedding-001` → **200, dim 3072**. So all six Google generator tiers
> and the Google embedder are reachable.
>
> **And read this correction before repeating the old diagnosis.** The failing
> exit on 2026-08-20 was also `dataforest GmbH`, and that same ISP answers 200
> today — while a *third* ISP also answers 200. **So the ISP name is a hint,
> not a verdict.** Probe the endpoint; never conclude from the ISP alone.
>
> ~~**One code follow-up is owed**~~ **— DONE 2026-08-30, commit `7b4c1db`.**
> `gemini-embedding-001` no longer carries `xfail(strict=False)`; it is a plain
> parametrized case like the other four. Verified three ways: the live smoke run
> is **5 passed**, a **mutation** (pointing Google at a dead model) turns it
> **red** where the old marker reported a silent green `xfailed`, and the full
> suite plus both ruff commands stay clean.
>
> **Next task: `.pdf`, then `.docx`, then other code languages.** Two of slice
> 3's four jobs are DONE. The **`.ipynb` loader** — see
> [slice 3, first half](../../step1/document-formats.md#slice-3-first-half---done-2026-08-29-a-notebook-becomes-cells),
> where a real notebook went from 94 chunks of escaped JSON to **91 real cells
> and 38% fewer tokens**. And the **bytes refactor**, which every remaining
> format depends on — see
> [loaders take bytes — DONE](../../step1/document-formats.md#loaders-take-bytes--done-2026-08-30).
>
> **`.pdf` is now PLANNED and the blocking decision is made. Read
> [the PDF theory](../../step1/document-formats.md#slice-3-second-half--pdf-the-theory-recorded-2026-08-30)
> before writing a line of it** — it is the mechanism, the math, and the two
> failures that are silent. The signature question is no longer merely settled,
> it is **BUILT** — see
> **[loaders take bytes — DONE](../../step1/document-formats.md#loaders-take-bytes--done-2026-08-30)**.
> `LOADERS` is `Callable[[bytes], str]`, `chunk_bytes` replaced `chunk_text`,
> and `load_text` is the default and the project's only decoder. **`.pdf` is now
> one new module plus one dict entry, and no door question returns.**
>
> **`.pdf` brings the one genuinely new idea in slice 3: lossy loading.** Every
> input so far has been exact — a `.py` read as text *is* the file. PDF is not:
> columns interleave, equations become noise, headers often vanish. For the
> first time a loader can **succeed and still return garbage**, with nothing
> raising. A **scanned** PDF has no text layer at all and must be refused, not
> silently returned empty. `MAX_UPLOAD_BYTES` (1MB) must also rise, or most real
> papers are refused before they are read.
>
> **One thing is still owed before any PDF number is trusted: a real paper.**
> Everything recorded about columns, `/ToUnicode` and scanned pages was proven
> on a PDF we *wrote ourselves* with the standard library. That proves the
> **mechanism**; it does not prove the **library**. Get a genuine two-column
> arXiv paper before choosing any threshold.
>
> ~~**The cap bug is still open**~~ **— FIXED 2026-09-05, and the timing was the
> whole point. See
> [the chunk cap fix](../../step1/vector-store.md#the-chunk-cap-fix--2026-09-05-the-last-cheap-moment).**
> The cap is now reserved for the header *before* splitting, `split_recursive`
> takes a budget, and **0 of 4,889 chunks** across the whole repository exceed
> it. Recall did not move.
>
> **The suffix rule is now a test.** `test_every_format_we_can_read_is_also_a_format_we_can_fetch`
> fails the build if a suffix reaches `LOADERS`/`SPLITTERS` without
> `READABLE_SUFFIXES`, or the reverse.
>
> **The audit's three defects are closed** — see
> [how each was closed](../../step1/sources.md#the-three-defects-and-how-each-was-closed--2026-08-28).
> Two were fixed; the third is pinned by a second `xfail(strict=True)`, because
> choosing its number is slice 7's decision, not slice 2's.
>
> **Read that second table before slice 6 — and note that Google now leads it.**
> `gemini-embedding-001` was scored on 2026-08-27 and is the **only model with
> perfect recall@5** (1.000, against codestral's 0.941). It also ranks `D2`
> **3rd where codestral ranks it 41st**, which was our worst known miss and the
> motivating case for hybrid search. Its budget is now known too: **1,000/day
> each for `gemini-embedding-001` and `gemini-embedding-2`**, on a pool separate
> from the Flash generators — but only **30K tokens/minute**, which is tighter
> than codestral's 50K, so it is *slower to ingest* while being *better at
> recall*. `embed-v4.0` keeps the best MRR and is **backup only**, because its
> quota is the reranker's. Under a rerank pipeline **recall@10 matters more than
> recall@5**, which is the number the current `MIGRATION` order rests on.
>
> **The pgvector gate is PASSED — measured 2026-08-28 on the real project.** An
> `hnsw` index on the expression `(v::halfvec(3072))` builds, **a query really
> uses it** (`Index Scan`, 64.7 ms against a seq scan's 326.0 ms at 2,000 rows),
> and half precision cost **0 of 10** in ranking overlap. Storage is 2× a
> 1536-dim model: 42 MB + 16 MB per 2,000 chunks, so ~8 corpora fit the free
> 500 MB. **Slice 4 must assert the query PLAN, not the result** — writing the
> `ORDER BY` the natural way silently falls back to a full scan.
>
> **`MIGRATION` is deliberately NOT reordered yet.** Two of Google's three
> questions remain — is it fast enough to ingest (30K TPM, the routing rule), and
> does it rank best on more than one fixture (slice 8). See
> [slice 8 decides the embedder and the reranker](../../step1/plan.md#slice-8-decides-the-embedder-and-the-reranker--recorded-2026-08-28).
>
> **One real bug is open and belongs to slice 3:** `MAX_CHUNK_TOKENS` is
> enforced on `chunk.text`, but what is embedded and reranked is
> `chunk.embed_text` — text **plus header**. 3 of 78 chunks already exceed the
> cap, which also breaks the Cohere rerank billing arithmetic.
>
> **Then slice 2 — read a repository**, which exists because **today's fixture
> fits the prompt budget**: retrieval cannot be proven until a corpus is too
> large to stuff. Slice 2 is also what finally measures the routing threshold
> in [open question 2](../../llm/embedder-chain.md#three-open-questions--answer-them-at-step-1-with-measurements).
>
> **`queries.json` is now the instrument for the whole of Step 1.** 17 graded
> queries over `B_train.py`, ground truth stored as **line numbers** so it
> survives any change to chunking. Re-score with it after every retrieval
> change — it costs no generation quota.
>
> **Step 1 is planned as eight slices**, and the plan is written down: read
> [Step 1 — the plan](../../step1/plan.md#step-1--the-plan-recorded-2026-08-20) before anything
> else. Retrieval is the first of
> [the four gaps](../../rules/teaching-and-communication.md#the-four-gaps-are-the-whole-point--teach-them-hardest-of-all),
> so it gets the full teaching treatment and it should be slow on purpose.
>
> **Two things the plan settled that are easy to miss.** Today's fixture
> **fits** the prompt budget, so retrieval cannot be measured until a
> repository is ingestible — that is why slice 2 exists. And `.ipynb` is
> currently **accepted and silently mangled**, which is why slice 3 exists.
>
> **Three things are already decided and must be read before writing any code:**
> [Retrieval design](../../retrieval/design.md#retrieval-design--recorded-2026-08-13) (the user's question
> is never the search query) ·
> [Chain 2](../../llm/embedder-chain.md#chain-2--embedder-migration-not-fallback) (the embedder is a
> migration, never a fallback) ·
> [the three open questions](../../llm/embedder-chain.md#three-open-questions--answer-them-at-step-1-with-measurements)
> (settle `codestral-embed` vs `mistral-embed` by measurement first — if
> `mistral-embed` wins, two of the three questions disappear).
>
> **Two Step 1 debts recorded elsewhere, easy to miss:** `select()` must fill
> **⚠ OVERTURNED 2026-09-14 — see [the selector](../../step1/ask-path.md#13-the-selector-and-the-scenario-matrix-behind-it--decided-2026-09-14). The selector shares the leftover instead: A before B leaves A UNCAPPED, so a large reference starves B entirely, and it biases every code-vs-code comparison by upload order. When A fits, the two rules give the identical answer.**
> 
> **A before B** (dropping part of A loses a statement we never learn exists),
> and the outline must list **files, not chunks** — 2,000 chunks would cost
> ~40,000 tokens, larger than the whole budget.
>
> **Two things are still owed and are cheap. Do them when convenient, not
> first:** **(1)** one request on `gemini-3.6-flash` with the lean `REPORT`,
> merged with the saved `3.5-flash` run — their blind spots are **disjoint**, so
> the union should reach ~17 of 19, see
> [Multi-pass](../../step0/prompt-experiments.md#multi-pass-vary-the-model-not-the-seed-measured-2026-08-17).
> **(2)** the impact column in `EXPECTED.md`, which costs no requests.
>
> **Code state:** **505 passed, 28 skipped, 2 xfailed, ruff clean.**
> `labpilot/api/` serves `POST /api/v1/compare` plus `/` and `/health`, built by
> a `create_app()` factory with a lifespan, routers, services, a typed error
> vocabulary and two ASGI middleware — see
> [the API layout](../../step0/slice-5-and-the-api.md#the-api-layout--restructured-2026-08-17). A static page is
> mounted at `/ui` and `docker/Dockerfile` exists but has **never been built** —
> see [the page and the container](../../step0/slice-5-and-the-api.md#the-page-and-the-container--2026-08-17).
> `instructions.py` holds five templates: `FULL` and `CORE` (scored baselines,
> untouched) and the lean `REPORT`, `SCAN`, `COMPARE`.
> Still **no database, no agent, no UI, no deployment, no fine-tuning dataset**.
>
> **Honest progress: Step 0 = 100%. The whole project ≈ 16%.**

> **2026-08-17, session 11 — slice 5 shipped, Step 0 closed, and the API was
> then restructured.**
> `labpilot/api/` serves `POST /api/v1/compare`: two uploads and a question in,
> the answer plus the model that produced it, the tiers that failed, the chunk
> counts per side, and **every citation resolved to a real file and line** out.
> It shipped as one `app.py` and was **split the same day** into a `create_app()`
> factory, a lifespan, routers, services, a typed error vocabulary and two ASGI
> middleware — the shape read from the user's own `sms-spam` and
> `Lung Disease Detection` projects, plus five things that go past them. See
> [the API layout](../../step0/slice-5-and-the-api.md#the-api-layout--restructured-2026-08-17).
> **A real run over uvicorn found what no test could:** the app never called
> `load_dotenv`, so every tier failed on a missing key and the endpoint answered
> 503 — indistinguishable from a total outage. The lifespan now refuses to boot
> when no tier has a key.
> **Mutation testing caught two of my own tests being self-fulfilling**, both
> deriving their payload size from the constant under test. See
> [the test that could not fail](../../step0/slice-5-and-the-api.md#the-test-that-could-not-fail--2026-08-17).
> Two dependencies were added: **`python-multipart` is runtime**, not dev.

> **2026-08-17, session 10 — no source changed, and it was the most productive
> session so far: the coverage root cause was found by experiment.**
> Three probes, three requests. **Session 9's conclusion was wrong** — the walks
> were *printed*, not *executed*, and nobody read them. Removing side A entirely
> and asking *"what could go wrong?"* recovered **five findings that seventeen
> comparison runs had never found once**, including the one at B-77, the very
> last chunk. Position, context and model strength are all eliminated as causes.
> Read [The root cause](../../step0/prompt-experiments.md#the-root-cause-found-2026-08-17-session-10),
> [the instruction bugs](../../step0/prompt-experiments.md#the-instruction-bugs-found-by-experiment-2026-08-17),
> [thinking burn](../../step0/prompt-experiments.md#thinking-burn-high-is-not-better-measured-2026-08-17) and
> [the prompt design rules](../../step0/prompt-experiments.md#prompt-design-rules-earned-2026-08-17).
> **The 11/18 measure is retired** — two of the eighteen change the result by
> nothing, so `EXPECTED.md` needs an impact column.

> **2026-08-17, session 9 — the chain was rebuilt on real quota numbers, and the
> coverage question was finally answered.**
> **The prompt fixes failed** — 11/18 before, 11/18 after, against a prediction of
> 15–16. See [the measurement](../../step0/prompt-experiments.md#the-prompt-fixes-were-measured-and-they-failed--2026-08-17).
> **Google's "~1,500 RPD" was wrong**: every Flash model is **20/day**, Flash-Lite
> is 500, Gemma is 14,400 — see
> [the real numbers](../../llm/quotas-and-pools.md#the-real-free-tier-numbers--measured-2026-08-16-and-they-overturned-a-lot).
> **`quota_pool` separates the bucket from the API key**, recovering ~40
> requests/day. **`max_input_tokens` turns a limit into a schedule** — Gemma and
> Groq are refused locally now and light up by themselves once retrieval shrinks
> the prompt. **The chain is 15 tiers ordered purely on measured score.**
> Two Step 2 designs were recorded at the user's request:
> [model routing](../../agent/design.md#model-routing--a-chain-per-task-not-a-model-per-task) and
> [thinking presets](../../agent/design.md#thinking-level--a-user-preset-never-a-per-model-switch).
> Smoke tests now **parametrize over `CHAIN`**, so a new tier cannot be forgotten.

> **2026-08-16, session 8 — no prompt work: the LLM layer was repaired and
> re-organised.** GLM-5.2 died on Mistral, and the way it died exposed a bug that
> was quietly costing tier 1 on every call. Four things landed:
> **the chain now tells five kinds of failure apart** (was three) —
> see How the chain decides ·
> **the chain is ten tiers**, led by `gemini-3.7-flash`, with two Mistral
> **reasoning** models nobody had noticed —
> see [Chain 1](../../llm/chains.md#chain-1--generator-true-fallback) ·
> **`_extract_message` handles the reasoning content shape**, which is a list of
> blocks, not a string — see
> [The reasoning content shape](../../llm/failure-rules-and-limits.md#the-reasoning-content-shape--found-2026-08-16) ·
> **the adjacency invariant was retired** and replaced by three better ones —
> see [Why the adjacency rule was retired](../../llm/quotas-and-pools.md#why-the-adjacency-rule-was-retired--2026-08-16).
> **198 unit tests, 9 of 10 tiers proven live, ruff clean.**
> **Next is unchanged: measure the four prompt fixes against the stuffed 11/18
> baseline** — now on `gemini-3.7-flash`, so record the model with the score.

> **2026-08-14, session 6 (later) — slice 4's code is written.**
> `labpilot/prompts/` now holds `_ids`, `context`, `instructions`, `builder` and
> `citations`; `GeminiProvider` gained `thinking`, `OpenAICompatibleProvider`
> gained `extra_body`, and both stay unset until a live request proves each
> host's shape. See [What slice 4 built](../../prompts/comparison-template.md#what-slice-4-built--labpilotprompts)
> and the four sections after it.
> **168 unit tests, 10 smoke tests, ruff clean.** `test_pipeline.py` and the smoke
> test were rewritten; the smoke test now runs three times — `FULL`, `CORE` and
> `CORE` stuffed — and records how many citations resolve.
> **Every tier now asks for maximum reasoning** — Gemini via `thinkingLevel`,
> Mistral via `reasoning_effort`, OpenRouter via `reasoning.effort`, Cloudflare
> via a best guess. Tiers 2, 5 and 7 are unproven and may answer 422; the chain
> records that and moves on, which is how we learn.

> **2026-08-14, session 7 — the measurements were run, and they say the prompt
> is the bottleneck.** Five runs are saved in `artifacts/`. `CORE` finished and
> resolved 93% of its citations; `FULL` never finished at either budget; stuffing
> all 96 chunks reached **11 of 18 findings** against the bare prompt's 10.
> Scoring the answers row by row produced the finding that matters:
> **every finding the model wrote has an A citation, and every miss has no anchor
> in A.** The prompt never asks the model to walk B. See
> [Why coverage is stuck](../../prompts/comparison-template.md#why-coverage-is-stuck--diagnosed-2026-08-14) and
> [The four prompt fixes](../../prompts/comparison-template.md#the-four-prompt-fixes--built-2026-08-14-not-yet-measured).
> **Next: apply the four fixes and re-measure against the 11/18 stuffed
> baseline.** Code state unchanged.

> **2026-08-14, session 6 — no code: slice 4's output template was designed.**
> Recorded in [The Comparison Template](../../prompts/comparison-template.md#the-comparison-template--designed-2026-08-14).
> The design was rewritten **twice** after the user rejected it: first for being
> written from `EXPECTED.md` (training on the test set), then for assuming the
> domain is machine learning and the code is Python. LabPilot is not MLPilot. The
> version that survived is domain- and language-neutral and passes a mechanical
> leakage test. Headline decisions: roles **A/B** instead of paper/code, with a
> two-way mode for code-vs-code · every finding classified on **four axes**
> (kind · box · evidence basis · impact) · **five boxes** where any divergence can
> live · a **14-section** output where §3, §6 and §9 must be written before the
> explanation · **`NONE` is a legal answer** or the model invents one · send the
> **full chunk-header outline** including dropped chunks. Two capabilities the
> library was missing turned up: `extract_outcomes` (withdrawn 2026-11-12, section 31) and `propose_fix`.
> **Next: write the actual instruction text, then measure against the 10/18
> baseline.** Code state unchanged: 130 unit tests, 8 smoke, ruff clean.

> **2026-08-14, session 5 (end) — SLICE 3 IS DONE. The whole chain ran and a
> real model answered.** `labpilot/ingest/` (the chunker, permanent),
> `labpilot/retrieval/` (the dumb selector, throwaway) and
> `labpilot/prompts/` (`build_context`) all exist. A smoke test runs
> files → chunks → selection → `LLMClient` and saves the answer.
> **130 unit tests, 8 smoke tests, ruff clean. Both branches level.**
> The first real answer scored **10 of 18 findings, zero hallucinations, but
> half its line citations were wrong and its final conclusion was false** — see
> [The first real answer](../../step0/slices-1-to-4.md#the-first-real-answer--measured-2026-08-14).
> **Next: slice 4, the prompt.** Start at
> [Where to pick up](../../step0/prompt-experiments.md#where-to-pick-up--slice-4s-coverage-problem).
>
> **Progress, honestly measured: Step 0 ≈ 70%. The whole project ≈ 10%.**
> Steps 1–4 have not started: no database, no agent, no UI, no deployment, no
> fine-tuning dataset. The *design* is much further ahead than the code, which
> lowers risk but ships nothing. CLAUDE.md's own warning — *"one month may be
> optimistic"* — is now confirmed by measurement.

> **2026-08-14, session 5 (later) — the chunker is built and measured.**
> `labpilot/ingest/` ships seven modules; `estimate_tokens` moved out of
> `labpilot/llm/_text.py` to `labpilot/tokens.py` now that two packages read it.
> **110 unit tests, ruff clean.** Three design decisions were changed *by
> measurement* rather than by argument — see
> [What the chunker actually shipped](../../retrieval/chunking.md#what-the-chunker-actually-shipped--2026-08-14).
> **Only the dumb selector is left in slice 3.**

> **2026-08-14, session 5 — slice 3 was unblocked.** `data/samples/` is no
> longer empty: the `quora_siamese` pair was built from the user's own Quora
> Question Pairs research notebooks, sized at ~20,400 tokens so that stuffing is
> impossible, and carrying 18 real divergences plus a full answer key. See
> [The sample pair](../../reference/sample-pair.md#the-sample-pair--quora_siamese-built-2026-08-14).
> `data/samples/` was excluded from ruff and pre-commit in the same commit, and
> work moved off `main` onto `feat/retrieval` per the branch-per-slice rule.
> **No `labpilot/` source changed. The chunker is next.**

> **2026-08-13, session 4 — no code, by design: the RAG gap was taught and the
> retrieval design was decided.** Lessons 1 (what RAG is) and 2 (chunking) were
> delivered, and the decisions they produced are recorded in two new sections,
> [Retrieval Design](../../retrieval/design.md#retrieval-design--recorded-2026-08-13) and
> [Chunking](../../retrieval/chunking.md#chunking--decided-2026-08-13-built-in-slice-3). The headline
> decisions: **the user's question is never the search query** — **NARROWED
> 2026-09-22, see [Step 2](../../step2/00-plan.md#step-2--the-plan-recorded-2026-09-22) C4: true for the
> default prompt, which carries no content at all, and FALSE for a specific
> question, where rewriting is measured to hurt**; query source is a
> field on each capability; code-vs-code uses a fixed checklist instead of paper
> claims; one similarity matrix serves `verify`, `find_missing` *and* the gate;
> `find_bugs` is a scan, not a search; small artifacts are stuffed, not
> retrieved. Chunking is pinned at `s ≈ 500`, `o ≈ 50`, hard cap 510, split on
> AST/headers/cells, with a `side` field that must not be forgotten. The
> fine-tuning dataset plan was **corrected** — examples must be built by running
> the retriever (RAFT), or the model learns to expect complete context.
> Code state is unchanged: 73 unit tests, 7 smoke tests, ruff clean.

> **2026-08-12, session 3 — the LLM layer is finished.** `chain.py` landed with
> `LLMClient`, retry/backoff, pool-aware skipping and a total time budget.
> `base.py` was then extracted from the two providers, and every provider gained
> `context_window` + `max_output_tokens` with a pre-flight validator. Every token
> limit in the chain is now a **measured** number, read from each provider's own
> API or docs — see [Token limits](../../llm/failure-rules-and-limits.md#token-limits--measured-2026-08-12).
> **Suite: 73 unit tests, 7 smoke tests, ruff clean.**
>
> **Nothing above the `LLMClient` seam exists yet.** No retrieval, no vector DB,
> no agent, no API endpoint. That is exactly the walking-skeleton plan: Step 0
> slice 3 starts the layer above.

> **2026-08-11, session 2 — the provider landscape was re-verified end to end and
> much of it changed.** Cerebras died (`402`, card now required). Modal left the
> chain. Mistral joined and became central. The generator chain was re-ordered on
> two independent benchmark sources, which **demoted Nemotron 3 Ultra from tier 1
> to tier 4**. Embedder and reranker chains were designed for the first time.
> The Step 2 [agent design](../../agent/design.md#agent-design--step-2-recorded-2026-08-11) was also
> recorded — intent→plan, the correspondence gate, and the citation rule.

**Where the code actually stands (end of session 3):**

- **`CHAIN` holds all seven generator tiers, every one proven live** — see the
  table under [Chain 1](../../llm/chains.md#chain-1--generator-true-fallback).
- **`LLMClient` exists and is the seam.** `generate(prompt) -> LLMResult`,
  walking the chain, catching `LLMError`, recording an `Attempt` per tier and
  raising `AllFreeTiersExhausted` when every tier is spent.
- **`base.py` holds `HTTPProvider`** — the shared `complete()` template. The two
  providers now supply only `_endpoint`, `_headers`, `_payload`,
  `_extract_message`, `_usage_summary`. `gemini.py` went 124 → 61 lines,
  `openai_compatible.py` 121 → 60.
- **Two abstractions, on purpose**: `Provider` (a `Protocol` in `chain.py`) is
  what the *chain requires*; `HTTPProvider` (an ABC in `base.py`) is what the
  *providers share*. A future Cohere reranker will inherit the second and never
  appear in `CHAIN`.
- `LLMError` now carries `status`, `retry_after`, `reset_at`, filled by
  `_http.error_from_response`. Control flow branches on those fields, never on
  the message string.
- `OpenAICompatibleProvider` gained `account_env` + `_endpoint()` so Cloudflare's
  account ID can sit in the URL path.
- `DEFAULT_TEMPERATURE` was **0.2** and is now **0.0** — the repeatability rule
  had never actually been in force.
- Four `CHAIN` invariants are pinned by tests: tiers run 1..N in order, no two
  adjacent tiers share an `api_key_env`, every env var is documented in
  `.env.example`, and every provider declares its token limits.
- Suite: **73 unit tests passing, 7 smoke tests, ruff clean.**


### Thinking models — the count is at least four of seven

*(Corrected 2026-08-12. An earlier note implied `gemini-3.6-flash` was safe
because it passed a 64-token test. It passed by luck on a trivial prompt.)*

Google AI Studio exposes a **Thinking level** selector for `gemini-3.6-flash`
— Minimal / Low / Medium / High, defaulting to Medium. And OpenRouter's own page
calls Nemotron 3 Ultra an *"open frontier-**reasoning** … model"*. So:

| Tier | Model | Thinking? |
|---|---|---|
| 1 | Gemini 3.6 Flash | **yes** — level selector, defaults to Medium |
| 3 | Gemini 3.5 Flash | **yes** — proven live, spent 60 of 64 output tokens |
| 4 | Nemotron 3 Ultra | **yes** — NVIDIA's own description |
| 7 | `gpt-oss-120b` | **yes** — proven live, `content: null` at 20 tokens |
| 2, 5, 6 | GLM-5.2, Devstral 2, North Mini Code | **unverified — assume yes** |

$$
T_{\text{out}} = T_{\text{think}} + T_{\text{answer}}
$$

`max_tokens` budgets both. Too small a budget returns an empty answer that the
chain then wastes a tier on.

**Measure the rest for free on the next smoke run.** Those 7 requests already
happen weekly — print each raw body once and read `usageMetadata.thoughtsTokenCount`
(Gemini) or `choices[0].message.reasoning` (OpenAI shape). The universal signal
needs no field name at all: **completion tokens far larger than the visible
answer**. That is what caught `gpt-oss-120b`.

**Thinking level is a per-task knob, not a global setting** — `explain_divergence`
wants High, the correspondence gate wants Minimal. That argues for a `thinking`
field on `GeminiProvider`, added in **slice 4** when real `max_tokens` values are
chosen. Not before: nothing reads it yet. Get the exact REST field name from
`<> Get code` in AI Studio rather than from memory.

`feat/llm-client` was squash-merged into `main` on 2026-08-11 and **kept, not
deleted** (user's choice). It is now kept **in sync with `main` by merging after
every commit**, so the two are identical. `LEARNED.txt` no longer differs — the
merge removed it there too.

~~**Two repository secrets are still missing on GitHub.**~~ **Added 2026-08-14.**
All seven repository secrets now exist: `CLOUDFLARE_ACCOUNT_ID`,
`CLOUDFLARE_API_KEY`, `COHERE_API_KEY`, `GOOGLE_API_KEY`, `MISTRAL_API_KEY`,
`OPENROUTER_API_KEY`, `VOYAGE_API_KEY`. `smoke.yaml` maps all five it needs, with
the variable name and the secret name matching on both sides of the colon — the
thing the 2026-08-11 `OPENROUTE_API_KEY` typo got wrong. Weekly smoke cost is 7
requests, and tier 7 should now pass. **Secrets are repository-wide, so they
apply on every branch — but scheduled runs still fire from `main` only.**

Setup is complete:
- Git repository connected to `https://github.com/a1mohamad/labpilot`
- Virtual environment on Python 3.13
- Four dependencies installed and pinned
- API keys stored in `.env` (git-ignored), template committed as `.env.example`
- All platform accounts for Steps 0–4 created and verified
  (see [Platform Accounts](../../llm/platform-accounts.md#platform-accounts--verified-august-2026))

Package layout is created and pushed — one folder per layer: `labpilot/llm/`,
`ingest/`, `retrieval/`, `agent/`, `prompts/`, `api/`, plus `data/samples/`,
`notebooks/`, `tests/`, `docker/`. All `__init__.py` files exist and are empty.
Flat layout, **not** `src/` — both give the identical import path
(`from labpilot.llm import LLMClient`), so moving to `src/` later is one
`git mv` that changes no imports. Not a decision worth making now.


### Slice 1 — DONE 2026-08-10

Step 0 is split into five slices. Finish one before starting the next; a
six-provider client written in one go has six places to be wrong at once.

1. ~~**Tier 1 alone returns text**~~ ✅ **done 2026-08-10**
2. ~~The fallback loop + 429 backoff, all seven tiers~~ ✅ **done 2026-08-12**
3. ~~Dumb retrieval — read one hardcoded paper + code pair from `data/samples/`~~ ✅ **done 2026-08-14**
4. ~~The single-pass comparison prompt~~ ✅ **done 2026-08-17** — see
   [Slice 4 — DONE](../../step0/slices-1-to-4.md#slice-4--done-2026-08-17)
5. ~~A bare FastAPI endpoint~~ ✅ **done 2026-08-17** — see
   [Slice 5 — DONE](../../step0/slice-5-and-the-api.md#slice-5--done-2026-08-17)

**What slice 1 shipped.** `labpilot/llm/` split by reason-to-change, not by size:

| Module | Holds |
|---|---|
| `__init__.py` | the package's public API — the only door other packages use |
| `errors.py` | `LLMError` |
| `contracts.py` | `Attempt`, `LLMResult` — imported by everything, imports nothing |
| `defaults.py` | `DEFAULT_TIMEOUT`, `DEFAULT_MAX_TOKENS`, `DEFAULT_TEMPERATURE`, `ERROR_BODY_CHARS` |
| `_text.py` | `truncate` — package-internal helper |
| `openai_compatible.py` | `OpenAICompatibleProvider` — the shared wire format for tiers 1, 4, 5, 6 |
| `registry.py` | `OPENROUTER_URL`, `NEMOTRON_3_ULTRA`, `CHAIN` — provider data and order |

Design decisions worth keeping:
- **Providers are instances, not subclasses.** OpenRouter, Mistral and Cloudflare
  differ only in data (URL, model, key name), so they are instances of one
  class. Only Gemini differs in *behaviour*, and it gets its own module.
- **No `base.py` yet.** An interface designed before the second implementation
  exists is a guess. It arrives with `gemini.py`, when the real difference is
  visible.
- **`max_tokens` is an argument of `complete()`**, not a provider field — answer
  length belongs to the task, not the model.
- **The provider stores the *name* of the env var**, never the key. The value is
  read at call time, so no log or `repr` can leak it, and CI can inject it.

Seven failure paths handled, each with a test: missing key · `RequestException`
· non-200 status · 200 with a non-JSON body · missing or empty `choices` ·
empty/`null` `content` · empty prompt. The last one raises **`ValueError`**, not
`LLMError` — a caller's bug must never be swallowed by the fallback loop.

Tooling landed with it: `pytest.ini`, `ruff.toml` (`E,F,I,UP,B`, line 88),
`.pre-commit-config.yaml`, `requirements-dev.txt`, GitHub Actions **CI** on every
push, and a separate **smoke** workflow that is manual + weekly only.

**Verified live on 2026-08-10** (3 requests spent of 50):
- `pytest -q` → 13 passed, 1 skipped, ruff clean.
- `pytest -m smoke --run-smoke -q` → 1 passed against the real endpoint.
- A deliberately broken slug returns **HTTP 400**, not 404 — and the error reads
  `Nemotron 3 Ultra: HTTP 400: ... is not a valid model ID`. The feared
  "HTTP 200 with an `error` key" case **did not occur**, so no extra branch was
  added for it. Re-check if a future provider behaves differently.


### Slice 2 — DONE 2026-08-12

**What has landed.** The providers, not the loop. `gemini.py` was written first
on purpose: it is the only provider with a different request *and* response
shape, so writing it showed where a shared interface really belongs instead of
guessing one.

| Module | Added |
|---|---|
| `gemini.py` | `GeminiProvider` — its own `_extract_message`, plus `_endpoint()` |
| `registry.py` | `GOOGLE_URL`, `GEMINI_3_6_FLASH` (tier 2), `GEMINI_3_5_FLASH` (tier 3), `NORTH_MINI_CODE` (tier 4) |
| `__init__.py` | re-exports all of the above — the package's public API |

`GeminiProvider` deliberately mirrors `OpenAICompatibleProvider` field for field.
Only three methods differ: `_endpoint()`, `_headers()`, `_payload()`. **That is
where `base.py` will cut** when it is finally written.

Four differences from the OpenAI shape, all now pinned by a test:
- model name lives in the **URL** (`{base}/{model}:generateContent`), not the body
- auth is `x-goog-api-key`, never `Authorization: Bearer`, and never `?key=`
- `contents: [{parts: [{text}]}]` instead of `messages`, and `maxOutputTokens`
  lives inside `generationConfig`
- response is `candidates[0].content.parts[*].text` + `finishReason` +
  `usageMetadata` — different nesting **and** camelCase

Extra failure branches Gemini has and OpenAI does not: a **blocked prompt**
(`promptFeedback.blockReason`, no `candidates`) and a candidate whose `content`
is an empty `{}` with no `parts` at all. `AttributeError` is in the caught tuple
here because `.get()` on a non-dict raises it where `[...]` raises `TypeError`.

Tests added: 12 unit for `gemini.py`, 1 for the `CHAIN` tier invariant, and
smoke tests for both Gemini models and North Mini Code. Suite was **27 passed,
4 skipped**, ruff clean *at that point in the day*.

**Verified live 2026-08-11:** all four providers that existed then — Nemotron 3
Ultra, both Gemini Flash models, and North Mini Code — answered. *(Tier numbers
in this paragraph are the pre-reorder ones; see the current table under
[Chain 1](../../llm/chains.md#chain-1--generator-true-fallback).)*

**Then, later the same day, three more providers landed** — `glm-5-2` and
`devstral-2512` on Mistral, and `@cf/openai/gpt-oss-120b` on Cloudflare — and
every tier was renumbered onto the benchmark-based order. `CHAIN` is now seven
entries; the suite is **30 unit tests, 7 smoke tests**.

Two bugs the renumbering exposed, both worth remembering:

- **Reordering `CHAIN` is not the same as renumbering `tier=`.** The tuple was
  put in the right order while the `tier` fields kept their old values, so the
  chain read `2, 2, 3, 1, 4, 6`. Only the invariant test caught it.
- **`DEFAULT_TEMPERATURE` was 0.2, not 0.0.** CLAUDE.md had required
  `temperature: 0` since slice 1 for repeatable comparisons, and the code had
  never enforced it. Every smoke test until then had been sampling.


### Where to pick up — the rest of slice 2

*Rewritten 2026-08-11. Cerebras is dead; Mistral replaces it and the chain was
re-ordered on measured benchmarks — see [The three chains](../../llm/chains.md#the-three-chains--restructured-2026-08-11).*

**1. ~~Reorder `registry.py` and add the Mistral and Cloudflare providers.~~**
**DONE 2026-08-11.** `CHAIN` now holds all seven tiers, every one proven live.
Two invariants are pinned by tests: tiers run 1..N in order, and no two adjacent
tiers share an `api_key_env`.

**`account_env` — how Cloudflare's account ID reaches the URL.** Cloudflare is the
only provider whose account ID sits *in the path*:

```
https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/chat/completions
```

`OpenAICompatibleProvider` gained one optional field, `account_env`, and an
`_endpoint()` method that interpolates it. **A subclass was rejected** — CLAUDE.md's
rule is *variants that differ only in data are instances, not subclasses*, and a
missing path segment is data. The template also generalises free to Azure OpenAI
and AWS Bedrock, which put account or region in the path the same way. And
`account_env` stores the **name**, read inside `_endpoint()` at call time — the
same discipline as `api_key_env`, so no log can leak it.

**2. ~~`chain.py`.~~ DONE 2026-08-12.** `LLMClient` walks `CHAIN`, records an
`Attempt` per tier, honours `Retry-After`, skips dead pools and enforces a total
time budget. `AllFreeTiersExhausted` deliberately does **not** subclass
`LLMError`, or the loop's own `except LLMError` would swallow the signal it
exists to report.

**3. ~~`base.py`.~~ DONE 2026-08-12.** `HTTPProvider` owns the template; the
subclasses own `_endpoint` / `_headers` / `_payload` / `_extract_message` /
`_usage_summary`. Written only after the second implementation existed, so the
seam was observed rather than guessed.

**4. ~~`context_window` + the pre-flight validator.~~ DONE 2026-08-12.** Both
limits are fields on `HTTPProvider`; `_check_fits` runs before `requests.post`.
*One correction to the old note:* the validator does **not** check
tokens-per-minute. TPM is a *rate*, not a per-request size, so it cannot be
validated from a single prompt — it belongs to the chain's backoff, which already
handles 429s. TPM is still what excluded Groq; that reasoning was about model
selection, not about this check.

**Chains 2 and 3 (embedder, reranker) are Step 1 work.** They are designed and
recorded above, but retrieval does not exist yet. Do not build them now.

**Tier order must change if Google is ever lost again.** Tiers 1 and 3 share the
Google pool. If Google goes down, promote Mistral so the chain does not spend
both Google attempts before reaching an independent quota.


### Slice 3 — DONE 2026-08-14

**What shipped.** Three packages, and the seam between them finally closed.

| Package | Fate | Holds |
|---|---|---|
| `labpilot/ingest/` | **permanent** | `Piece`, `Chunk`, three splitters, `chunker.py` |
| `labpilot/retrieval/` | **throwaway** | `select()` — a hardcoded rule, deleted at Step 1 |
| `labpilot/prompts/` | grows in slice 4 | `build_context()` — chunks → one string |
| `labpilot/tokens.py` | permanent | `estimate_tokens`, moved out of `llm/_text.py` |

**The selector, in one sentence:** split the budget in half, then take chunks
from the top of each side until that half is full. No scoring, no question, no
relevance. It is scaffolding and it is *supposed* to be bad.

**Two flaws in it, both deliberate and both left alone:**

- **It wastes budget.** Fixed halves. On the sample pair it sent 14,273 tokens
  of a 20,000 budget, because side B filled its 10,000 while side A needed only
  4,273. The leftover is not shared.
- **It picks by position, not meaning.** It covered three of the four known bug
  lines *by luck* — they sit early in the file — and missed the fourth at line
  1146 entirely. Move a bug to line 1400 and it disappears.

That second flaw **is the argument for Step 1**, now demonstrated rather than
asserted.

**The pipeline test.** `tests/unit/test_pipeline.py` runs the real chain with no
mocks — chunk both files, select, and check that the prompt fits the budget,
both sides survive, every chunk is still checkable against its file, and the
same input gives the same answer twice.

#### The first real answer — measured 2026-08-14

Tier 1 (`gemini-3.6-flash`) answered a bare prompt: context plus one question,
**no instructions at all**. Scored against `EXPECTED.md`:

| | |
|---|---|
| findings **correct** | **10 of 18** |
| **hallucinations** | **0** — every claim pointed at code that exists |
| line citations correct | **about half** |
| overall, honestly | **5 / 10** |

**It found the two hardest ones:** pooling the projected features, and the
stopword mask — including *both halves* of the scattered fact, the tokenizer and
the model.

**Three failures, and each one sets a task for slice 4:**

1. **It cannot count lines.** Given a header saying `lines 579-604`, it invented
   a plausible number inside that range and was wrong about half the time —
   `197` for a line that is at `205`, `251` for `257`. **A model sees text, not
   line numbers.** So the citation rule cannot work by hoping. Slice 4 must
   either number the lines inside the prompt, or require the model to **quote
   the chunk header verbatim** instead of inventing a number.
2. **Its final conclusion was false, and it is the exact trap the fixture was
   built to set.** It summed the paper's ablations, produced a range, and said
   the code's 0.822–0.826 *"accurately reflects these compound errors."* But
   0.851 is a clean **test** score and 0.826 is a **validation** score with the
   threshold tuned on itself. They are not comparable. It subtracted two
   different things and declared agreement. Slice 4 must instruct it to ask
   *"are these two numbers measured the same way?"* before comparing them.
3. **It walked past evidence it was given.** Seven of the eight missed findings
   were **in the text sent to it** — most importantly the 12-point
   train-vs-validation gap sitting in the docstring. Only one miss (#9, the
   threshold leak at line 1146) was the selector's fault.

**The one-line summary worth remembering: it is good at *spotting* differences
and bad at *judging* them.** A user reading the last section would have believed
something false. That is why slice 4 is a whole slice and not a paragraph.

**Where answers are saved.** `artifacts/` (git-ignored), one timestamped
Markdown file per run holding the model, tier, chunk count, which tiers failed,
the answer, **and the exact prompt that produced it**. Keep the prompt — when an
answer is bad, the chunks are usually the cause, and without the prompt there is
nothing to inspect.

**A filename typo hid four tests.** `tests/unit/prompts/text_context.py` — `text`
instead of `test` — was committed and never ran, because pytest only collects
`test_*.py`. Nothing failed, nothing warned, and the suite count still went up
because other files were added at the same time. **Check the collected count,
not just the passing count**: a test that is never collected is indistinguishable
from a test that passes.

**`max_tokens` needs ~8000, not 2000.** At 2000 the answer was cut mid-sentence,
because Gemini spends part of the budget thinking.

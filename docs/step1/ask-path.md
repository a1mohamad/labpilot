# Step 1, slice 7: the ask path

[Docs home](../README.md)

## Slice 7 — the decisions taken before any code, 2026-09-13

*Taken in session 21 with the user, before a line of slice 7 was written. Several overturn or narrow something this file already said.
Section numbers below (1-16, with letters) are cited by code comments; they are kept.*

### 1. The API splits into INGEST and ASK

`POST /api/v1/compare` took **both files on every request**, so every question re-chunked and re-embedded the whole corpus. Slice 7 split it:
`POST /artifacts [file]` → `{"id": "a1"}` once (chunk, embed, store) and `POST /compare {a, b, question}` per turn (search, rerank, answer). The
reason is not speed: this file's design says artifacts are **state**, not input ("after an artifact is ingested the only thing crossing the wire each turn is
a prompt"). Three things follow free: **retrieval becomes measurable** (the same corpus can be asked two questions), **0-, 1- and 2-artifact sessions cost one
field** (the door takes ids, so a session simply has fewer), and **pgvector stops being scaffolding**. Measured: a FastAPI-sized repository on `codestral-embed`
was calculated at 166 minutes per question under the old shape; **measured 2026-09-14 it is about 15** (the quota that figure rested on is not enforced, section 9),
which is still unusable, and paying it once is still the point.

### 2. ONE LIST OF EMBEDDERS, SORTED TWO WAYS

*The user's rule; it corrects a two-pool version I proposed first (a fast pool of two models, both exhausted, was a dead end).* One list, every embedder, and the
**order** changes: fits the prompt budget → STUFF IT (no embedder chosen at all) · small corpus → sort by STRENGTH, walk down · large corpus → sort by SPEED, walk
down. Walking down = take the first model whose quota is alive (Google counts as spent only when **both keys** are). The threshold is **time**:
`T = (t(A) + t(B)) / rate`, `T > 6 min ⇒ sort by speed`, checked before the first call. Speed order at 341.6 tokens per chunk, chunks per 6 minutes:
`mistral-embed` ~10,800 · `embed-v4.0` ~5,760 (10 req/min × 96) · `codestral-embed` ~878 · `gemini-embedding-*` ~527 · `bge-base` unknown. **The strength order
(and Cloudflare's speed) is slice 8's job.** The fall-through is free because it happens *before* any vector exists; switching models *mid-corpus* is the
unrecoverable case this file forbids ("never continue a half-finished corpus with a different model").

### 2b. A SLOW INGEST IS OFFERED, NEVER IMPOSED

*The user's call.* If every fast model is spent the walk reaches a slow one; we use it rather than refuse, **but ask first** ("this will take about 63 minutes.
continue?"; nothing starts without a yes). The old "codestral is 37 minutes" came from a quota later measured to be unenforced (codestral really takes ~3.3 min);
the slow model reached today is `gemini-embedding-*` at ~63 min, which IS enforced. This path only exists when the corpus is too large to stuff.

### 3. One embedder per SESSION — a simplification, NOT a safety rule

Both artifacts use the same model; two models is a candidate for later and the database already allows it (`v` is undimensioned, the model lives on the artifact
row). **The stated reason was WRONG and is corrected:** "the alignment matrix would compare across models, `cos(E_A(q), E_B(d))` = noise" was repeated for weeks
unchecked. A's vectors never meet B's: the matrix compares *claims extracted from A as TEXT* against B's chunks, embedded in B's space. What survives: two query
embeds per turn instead of one; ~~the gate's threshold is calibrated **per model** (Step 2)~~ (no longer true: D78, 2026-10-29, the gate reads the two summaries and has no cosine threshold); and a future caller could pool A's and B's **vector scores** in one
sorted list (cannot happen today: `select()` loops `for side in ("A","B")` and `weighted_rrf` fuses by **rank**). Reranked scores come from ONE cross-encoder and are
comparable across sides, so merging A and B into one 100-document call is safe on scale and unsafe only on *coverage*.

### 4. The full decision ladder, start to finish

(1) Does EVERYTHING fit the prompt budget? Yes → STUFF IT ALL (no embedder, search, rerank or database). (2) Else estimate the time, sort the one list, walk to the
first live model, show the estimate and ask if long, embed + store. (3) Search → top `SEARCH_LIMIT`. (4) Gate: obvious winner → skip the reranker. (5) Rerank if a
tier is available, else `skip()` and keep the vector order. Step 1 keeps being under-weighted: a paper plus a notebook often fits, and then retrieval is not merely
unnecessary but **harmful** (a bad retriever can hide the very line the report needs). Both N's were placeholders then (`recall@N` is monotone); it is **two** numbers
because the reranked and vector-only paths have different recall curves.

### 5. MEAN TOKENS PER CHUNK IS 341.6, NOT 192 — measured 2026-09-13

Slice 1 recorded **192 tokens per chunk** from `B_train.py`, one file. Chunked over this whole repository: **5,386 chunks, 1,839,759 est tokens, mean 341.6, max 509**
(1.8x higher; the "37 minutes" consequence was later disproved by section 9, but the token-count correction stands). **A benchmark answers the question its fixture
asks.**

### 6. OPEN DEFECT: BGE's input guard is enforced with OUR tokenizer

`HTTPEmbedder._check_texts` enforces `max_input_tokens` with `estimate_tokens` (`chars/3`, Mistral-shaped); BGE tokenizes **2.36x** more on the same corpus (39,936 vs
codestral's 14,979), so its real 512-token limit is ~217 of our tokens: on this repository 0 chunks are refused by the guard and **3,978 of 5,391 (73.8%) would be
silently truncated by BGE**. Not fixed and not urgent (BGE has no caller). The mechanism is certain; the 73.8% is extrapolated from one ratio on one Python file
(*later measured: BGE's real ratio is 1.12-1.45x and 91% of geo chunks exceed its 512 limit; BGE was dropped*). **A limit is only enforced if it is measured in the
units the provider counts.**

### 7. Cohere's exclusion is LIFTED, and its old reason was already stale

`embed-v4.0` was excluded because Cohere was the rerank primary; slice 6 demoted it to rerank tier 7 of 8 behind ~29,800 Google calls a day, so that reason died
unnoticed. Cohere is now a member of the one list, and a fast one; what remains true is a budget fact (1,000 calls a **month**, an embedded corpus spends it on
every future query, plus the `x-trial-endpoint-call-limit: 10` ceiling). **When a decision has two reasons and one dies, say which one still carries it.**

### 8. TIME IS A PRODUCT CONSTRAINT, and it has TWO thresholds

*The user, 2026-09-14, replacing a single 6-minute number doing two jobs:* **6 min** decides the sort order of the embedder list (strength vs speed); **2 min** decides
whether to STOP and ask the user first. Embedding is one stage of several (exact search 34 ms · rerank 1.3 s with flash-lite, 18-22 s with Gemma · one full report
52.7 s live · embedding 0.9-61 min), so a 2-minute embed is already a 3-4 minute answer before the agent exists. `Ingested.minutes` is the EMBEDDING estimate only and
must be labelled that way.

### 8b. THE AGENT MAKES IT SLOWER, NOT FASTER - and that is the trade

Step 2 is an **accuracy** optimisation, never a speed one (one call found 13 of 19; the 7 misses each need a *different question*, so four questions cost four
calls). **"Simpler" applies to the developer, never to the clock.** It is not 10x thanks to routing (a report is ~10 calls and only ONE needs the strong slow model),
the gate that halts a mismatched pair, batched `verify` and stuffing: honestly **2-3x Step 0's wall clock**.

### 8c. THE PRODUCT CONSTRAINT, written down so it binds

> **We will not ship a tool that costs ten minutes for a simple task.** It is a requirement on the planner: "summarize this" → 1 node, "find bugs" → a few, "why
> do they diverge" → the whole graph. When a simple question gets expensive the fix is to stuff instead of embed, not a louder warning.

### 8d. THE END-TO-END NUMBER IS UNMEASURED, and slice 8 owes it

`WARN_MINUTES = 2.0` is a guess like the 6; slice 8 must measure the real end-to-end time (done: ingest ~26 s per 100 chunks, answers 119-497 s, generation 98.2%).
Writing a total without derivation would repeat the `r = 5` mistake.

### 8e. WHERE THIS ACTUALLY LIVES: STEP 3, NOT HERE

The warning window, the "this is not ChatGPT" notice and the progress display are **Step 3** (UI); Step 1 owes only the NUMBER and the honest label (`ingest_artifact`
returns `minutes`; nothing in `api/` or `retrieval/` asks a user anything). The page is throwaway ("throw away 100 lines, not an app") and worth REBUILDING at the
END of Step 1, once artifacts are real stored things with ids, chunk counts and timings (done 2026-09-15).

### 9. THE PUBLISHED QUOTA DOES NOT PREDICT TIME — measured 2026-09-14

*The user refused an estimator built on `tokens_per_minute` and asked for one built on our own measurements; measuring it overturned four claims above.*

```
codestral-embed   DOCUMENTED quota   50,000 tokens/minute
                  MEASURED           590,000 tokens/minute   (11.8x over, 71 seconds, 37 requests, ZERO refusals)
```

It is not universal: Google enforces its number exactly (`gemini-embedding-001` and `-2` both 429 on the SECOND call in a minute, ~29,000 against 30,000).

#### Every embedding timing this project has

Timeboxed pushes from a Frankfurt VPN exit on real chunks; *sustained* = 4+ requests, *burst* = never met a limit. Tokens/min: **codestral** burst 619,000 · sustained 4
batches 600,000 · sustained 71 s **590,000 (37 requests)** · sustained 30 s 474,000 · **mean of multi-request runs 554,000**. **mistral-embed** burst 703,000 · sustained 40 s
520,000 (25 requests) · **slice 4's 5-repo ingest 504,000 (849 requests)** · **mean 512,000** (two numbers weeks apart corroborate each other). **gemini-embedding-001** burst
274,000, **throttled 29,000** (6× 429); **-2** throttled 28,700. **embed-v4.0** burst only 641,000 (6 requests). **bge-base** burst 288,000 / 926,000 / 732,000 (3.2x span).

#### Three traps this exposed, and each one produced a wrong number first

(1) **Averaging a burst with a throttled run is nonsense** (Google 274,000 and 29,000 average to 151,717 and describe nothing): bursts count only where no limit exists.
(2) **A quota is not a throttle, and treating it as one was 12x PESSIMISTIC** (`tokens/TPM` says a 19,000-token call needs 23 s; it takes 1.8 s: a provider lets you send a
minute's allowance at once and the limit only bites on the NEXT call). (3) **Timing ONE batch gives a burst rate that cannot be sustained.**

#### What the estimator uses now

`embedding_minutes = max(tokens / measured_tokens_per_minute, requests / requests_per_minute)`. `measured_tokens_per_minute` is OURS (on `Spec`, the only basis for the
time; no provider reports throughput); `requests_per_minute` stays as a ceiling no throughput can beat (Cohere's 10 calls a minute make a 57-request corpus 5.7
minutes however fast the wire is); `rate.tokens_per_minute` is recorded but NOT used (it lets `rates.learn()` warn when a header stops matching, which is how we would
learn Mistral started enforcing); **a model nobody timed returns `inf` and sorts last**. **The seeds are MEANS**: the first version used the lower of each pair ("never
under-promise") in the wrong layer; **keep the estimator unbiased; padding belongs at the display.**

#### What it predicts, and what it overturns

This repository (1,839,759 tokens, 57 requests): codestral **3.3 min** (was claimed as 37) · mistral 3.6 · cohere 5.7 (requests bind) · gemini **63.4** (enforced) · bge cannot
(over its 684,000-token daily budget). The two-orderings rule stands but its motivating example evaporated: sorting by speed now changes anything only above ~9,700 chunks
or when Google is the best model alive.

#### Honest limits

One account, one VPN exit, two days (Mistral may begin enforcing; the `rates.learn()` staleness warning would tell us); BGE is the roughest number; Cohere and BGE are
BURST ONLY (capped at 6 requests to protect a 1,000-a-MONTH and a 10,000-neuron-a-DAY budget).

#### OPEN DEBT: nothing learns throughput at runtime

`rates.py` learns `requests_per_minute` from a header; throughput is not reported by any provider, only timing our own calls can learn it, and nothing does. It is
deliberately NOT half-built: accumulating needs a decision about what "elapsed" means (sum of request durations = burst rate, or wall clock = the true ingest rate;
choosing wrong reintroduces the 619,000-vs-554,000 error). It belongs with the progress display at Step 3. **A vendor's published limit is a promise about what they will
REFUSE, never a prediction of what you will GET.**

### 10. THE ASK PATH — decided 2026-09-14, before piece 4 was written

*Taken with the user in the same discipline as sections 1-9: the decisions first, the code after. Three of them narrow or correct something this file already said.*

#### 10a. THE STUFF CHECK MOVED, because artifacts became state

The ladder in section 4 was written for the single endpoint. Option 2 split it, so the check moved: `POST /artifacts` ALWAYS chunks, embeds and stores (state, no
decision); `POST /compare` asks "do A and B TOGETHER fit the budget?" — yes → read every row back and STUFF (no query embed, search or rerank), no → search.
**Ingest never skips embedding, deliberately:** a small A may later be paired with a huge B and then A must be searchable; deciding at ingest would make an artifact
usable in one mode only. The size needs no new column (`estimate_tokens` is `ceil(chars/3)` and `embed_text` is `header + "\n" + text`): `select count(*), sum(length(header) + length(text) + 1) from chunks where ...` is exactly the number our Python
would produce, in one round trip with no rows moved (a stored token count is a second copy of the truth, the argument that rejected `chunk_count`). **The cheap check
comes FIRST** (reading 24,000 rows to learn one boolean spends ~14MB over the VPN). `store/` therefore gained two functions: `measure()` and `read_chunks()`.

#### 10b. THE THREE NUMBERS — only their ORDER is a rule, the rest is a knob

**`SEARCH_LIMIT = 50` counts documents in ONE call on ONE artifact** (`store.search()` takes one `artifact_id` and one limit; the dense top-50, "we send 50 of a free 100",
"61% of the 82-chunk quora corpus" and Voyage refusing a 50-document window were all one corpus; read as a total, every figure halves).

```
search     SEARCH_LIMIT = 50  PER SIDE      100 candidates
retrieve   VECTOR_TOP_N = 25  PER SIDE      <- THE CUT (this section's plan; see 14.3: the cut moved per tier)
rerank     25 -> RERANK_TOP_N = 10
RERANK_TOP_N  <=  VECTOR_TOP_N  <=  SEARCH_LIMIT      all three PER SIDE, the only rule: arithmetic, not taste
```

The cut BEFORE the reranker means a bad reranker costs ordering and never content (slice 6: `bge` took r@10 from 0.933 to 0.711), at the price of the rescue: ranks 26-50
(requests r@20 0.978 = r@50 0.978, cost 0.000; quora r@20 0.941 vs r@50 1.000, one query of 17). It also makes Voyage reachable (10d). A `RERANK_TOP_N` above
`VECTOR_TOP_N` would make the DEGRADED path sharper than the good one. **`N/2` is NOT a rule** (my error): it is a default chosen for symmetry; the two numbers are
**joint** (a wide window with a hard cut is a different system from a narrow window sent whole), and slice 8 sweeps them together. *A ratio that looks tidy is still a
guess* (pgvector's `ef_search = 40` and RRF's `k = 60` were tidy and wrong here). `RERANK_TOP_N` has a softer reason to sit below its range: a good reranker shifts the
recall curve LEFT (reranked N=3 scores 0.882 vs vector 0.765) and that is collected only by cutting harder (an argument, not a measurement).

> **A constant's UNITS are part of its meaning.** This was nearly written with `SEARCH_LIMIT` as a total (25 per side), silently re-scaling every rerank, neuron, token and
> corpus-ratio figure recorded earlier; the user caught it. **Before reusing a number in a new section, grep for it and read what the OLD sentences assume.**

#### 10b-bis. `SEARCH_LIMIT` HAS NEVER BEEN SWEPT — slice 8 owes it

Slice 6's measurement 2 varied how many chunks to **send**, never the retrieval **window**. `SEARCH_LIMIT = 50` ("retrieve wide, rerank to ~10") has been a default since slice 4.
Sweep 10 → 100 per side (below 10 the reranker has nothing to reorder; at 100 Cohere bills per CALL up to 100 documents and we send 50). Voyage caps the usable end far
lower (30 passed, 40 refused on a card-free account): the sweep measures QUALITY and the chain decides REACHABILITY. *(Done in slice 8: the window turns over between 50 and 100.)*

#### 10c. PER SIDE, NOT MERGED — and slice 8 must measure it

Earlier text said merging A and B into one rerank call is "safe on scale and unsafe only on coverage". Both halves are still true, and **the decision goes the other way**:
merged = 100 documents, ONE call, half the rerank budget, but one side can take every slot; per side = 50 documents, TWO calls, **coverage is STRUCTURAL**. **A guarantee in
the shape beats a guarantee in a downstream rule.** And merged is the one shape that loses Voyage (per side 25 documents ≈ 9,040 tokens, under the 10K ceiling; merged 50 ≈
16,900, refused). Per side is the DEFAULT, not the answer; the merged-vs-per-side measurement is owed *(slice 8 did not measure it; per side stays on the structural argument)*.

#### 10d. THE PRE-RERANK CUT MAKES VOYAGE REACHABLE — predicted, not measured

Voyage cannot serve 50 documents free (50 ≈ 16,900 tokens refused, 40 ≈ 13,100 refused, 30 ≈ 8,900 passed, against a 10K TPM that counts a call whole). Cutting to 25 gives
`t_q × N_d + Σ t_di = 20 × 25 + 25 × 341.6 ≈ 9,040` tokens, under the ceiling: the first shape in which our second-best measured reranker is usable free. **A PREDICTION**
resting on `chars/3`, which straddled Voyage's real boundary in both directions in slice 6; one real call settles it (1 of ~16,000). *A first draft reached the same
conclusion through a units error (SEARCH_LIMIT as a total); a right answer from a wrong premise gets quoted back and then collapses.* *(14.3 later replaced the global cut with
a per-tier window: Voyage's `max_documents` is its measured 30.)*

#### 10e. "N in {20, 50} is ELIMINATED" was too strong — corrected

`recall@N` is monotone, so N=50 has the highest recall of any N; 15 → 50 buys 0.000 recall and costs DILUTION, a *generation* property never measured here. So 50 is not
eliminated, it is **unmeasured in the only direction that could condemn it**; `VECTOR_TOP_N = 50` would ship as the conservative choice (never discard a chunk already paid
for), and slice 8 measures DOWNWARD, expecting 20 or 15. **A metric that only moves one way cannot eliminate a value, only fail to reward it.** *(Slice 8 v3 later set
`VECTOR_TOP_N = 15`; the 30 that shipped first was a unit error.)*

#### 10f. What piece 4 does NOT decide

Decided: stuff at ask time and search when it does not fit; per side reranking with `RERANK_TOP_N <= VECTOR_TOP_N`; every top_n PER SIDE (50 / 25 / 10); exact search and no
fusion on the query path (then); the reranker RUNS with the chain assembled at entry; the search query is the user's question. NOT decided (slice 8 unless noted): the stuff
threshold (it is `PROMPT_BUDGET`, unchanged), merged vs per side, all three values, whether `wRRF` replaces vector search, whether reranking SHIPS, and claim extraction
(Step 2).

### 11. THE OUTPUT BUDGET — nine decisions, taken 2026-09-14

*Taken with the user during build step 1, interrupted by a question this file could not answer ("why does raising `max_tokens` hurt a model that would never reach it?"),
because the answer was a defect. Four of the nine are the user's, and two overturn something this file already said. No code changed.*

#### 11.1 `max_tokens` and `max_output_tokens` are a GRID, and the missing operator is `min()`

Two axes: `max_tokens` = what THIS JOB needs (changes per task, same on every model; SENT in the request); `max_output_tokens` = what THIS MODEL can do (per model, same for
every task; a note in `registry.py`). Both count `T_out = T_think + T_answer`. The number actually sent is a CELL:

| | gate (200) | summarize (1,000) | report (32,000) |
|---|---|---|---|
| Gemini (65,536) | 200 | 1,000 | 32,000 |
| Gemma (32,768) | 200 | 1,000 | 32,000 |
| Devstral (16,384) | 200 | 1,000 | **16,384** |
| Groq (8,000 total) | 200 | 1,000 | refused on INPUT |

`sent = min(what the job needs, what the model can do)`. A single global `max_tokens` would reserve 65,536 tokens on Gemini for a one-word gate answer (and on Groq, where a
reservation is charged whether used or not, give one call per minute); a single per-model one would make Gemini write 65,536-token reports and Gemma 32,768-token ones, so a
difference between reports could no longer be attributed to the model (the same comparability rule as `temperature: 0`).

#### 11.2 CLAMP, not refuse - but only when the number rises

`_check_fits` runs three checks: (1) `max_tokens > max_output_tokens` → refuse (**weak**), (2) `padded > max_input_tokens` → refuse (real, Gemma's 16K/min), (3) `padded +
max_tokens > context_window` → refuse (real, what stops Groq). **Check 1 rests on an assumption measured FALSE** ("caught locally instead of costing a request"): Mistral was
asked for `max_tokens: 32000` on `devstral-2512` (cap 16,384) and answered **200**, writing less. Today harmless (at `REPORT_MAX_TOKENS = 32_000` it excludes only Devstral,
genuinely too small, and Groq, already caught by check 3). **It becomes a defect the moment the number rises past 32,768**, excluding Gemma and Laguna.

> **THE DECISION: keep the refusal today; if `REPORT_MAX_TOKENS` ever rises, change check 1 to `max_tokens = min(max_tokens, self.max_output_tokens)` in the same commit.**

It cannot land silently: `test_only_known_tiers_cannot_serve_a_full_report` asserts the unable-list is EXACTLY the pinned names (then `("GPT-OSS 120B (Groq)", "Devstral 2")`),
so raising the number turns it red at exactly the right moment. Keep it when the task chains are written.

#### 11.3 The one real loss the refusal costs

When every tier that CAN finish is spent, the chain returns **503 and nothing**, where a clamped tier could have returned a truncated report (truncation is visible:
`finish_reason` is on `LLMResult` and the page renders `MAX_TOKENS` as a warning). Rare with a long chain; needs a second pass through a simple, well-tested loop.
**Recorded, not built; fix it only if it happens.**

#### 11.4 Four of six providers have NEVER been tested above their cap

Mistral asked above its cap: **200**, caps itself and writes less (measured). Groq: **413**, refuses and writes nothing (measured). Google, OpenRouter, Cloudflare, Cline:
unknown, never tried. Clamping sidesteps the blanks (a clamped number is one no provider can object to). **Do not generalise from either measured provider to the other four.**

#### 11.5 A `HIGH` report cannot fit a 32,768 cap - arithmetic, not policy

`T_think + T_answer ≤ C_out`. Measured on `gemini-3.6-flash`: a complete report needs `T_answer` ≈ 5,655 and `HIGH` spent `T_think` ≈ 29,747: `35,402 > 32,768`. Clamping only turns
a refusal into a truncation; the lever is the thinking level, measured: at `MEDIUM` the same model finished with 2.5x more report.

> **More budget buys more thinking, not more answer.** Raising `max_tokens` to survive reasoning burn treats the symptom; `thinking` is the cause.

Visible even on a trivial prompt (2026-09-14 health check, 10 input tokens): `gemini-3.6-flash` and `3.5-flash` STOP with 4 output tokens and 178 THOUGHT tokens (44x the visible
answer, "say ok"), because every Gemini tier ships `MEDIUM`.

#### 11.6 A THINKING PRESET MUST RESTRICT THE CHAIN, NOT ONLY THE NUMBERS

*The user's, extending the rule that a preset sets the level AND `max_tokens` together.* **Deep is not a dial that exists on every tier**: (a) no knob at all (at the time
`REJECTS_THINKING = ("gemma-4-31b-it",)`, Gemma answering HTTP 400 to a thinking field — *CORRECTED 2026-09-30 (Step 2 §15.6): Gemma accepts `MINIMAL` and `HIGH` and refuses
`LOW`/`MEDIUM`; the registry now uses `GEMMA_MODELS` + `GEMMA_LEVELS`*), (b) no room (11.5). Fast/Balanced: every tier eligible; Deep: only tiers with a thinking knob AND
`C_out >= thinking + a finished report`. **The user's better fix for the silent-downgrade risk: build the chain so it cannot happen** — every real *Gemini* model carries a
thinking level, so a Gemini-only Deep chain has nothing to warn about (*put a rule where it cannot be broken, not where it can be checked*, one level up).

#### 11.7 A SCARCE TIER BELONGS IN AN EXPENSIVE CHAIN AND NEVER IN A CHEAP ONE

*The user's.* A report is ~10 calls and the strong models are scarce (every Gemini Flash is **20 requests a day**). A 200-token gate call that fell through (Gemma HTTP 500 at
about 1 call in 3 → Groq refused → Flash-Lite ok → ...if the chain continued: Gemini 3.7 Flash) would burn 1/20th of the day's report budget silently — **a quota leak is silent
by construction, so it needs a test.** The partition (then 23 tiers): cheap work = Cline ×2 (free) · Gemma ×4 (57,600/day) · Flash-Lite ×4 (2,000/day) · Groq (1,000/day, small
jobs) · Mistral (rate-limited, not capped); reserved = Gemini Flash ×6 (120/day) · OpenRouter ×3 (50/day SHARED) · Cloudflare GPT-OSS (~11 reports/day). **One-directional**: a
scarce tier may sit in the report chain, a cheap chain must contain none, and each task chain must still end in something that cannot run out.

#### 11.8 THE REPORT CHAIN IS BUILT FROM CAPABILITY, AND DEGRADATION MUST BE VISIBLE

*The user's, correcting "`EXPLAIN_CHAIN = CHAIN`, everything, strong first".* For TOKENS the chain already self-filters free (`_check_fits` removes Groq and Devstral before any
request). For THINKING there is no filter: a Deep request falling through to Gemma returns a report that is not deep and nothing says so — a silent downgrade, which this
project bans. Report chain = tiers that can ACTUALLY serve THIS report, strong first ("can serve" = tokens (checked today, free) + thinking (NOT checked: the gap)). The answer
is not exclusion but the pattern used twice already (`skip()` returns `model=SKIP`; `MAX_TOKENS` renders as a warning): **Degrade, but never silently.** The trap the other way:
LOWERING `REPORT_MAX_TOKENS` would silently let weak tiers into the report chain; the same exact-list test catches that too.

#### 11.9 DO NOT RESERVE THE STRONGEST TIER FOR THE REPORT ON AN ASSUMPTION

*The user's, challenging "reserve tier 1 for `explain_divergence`, which is the actual product".* Model strength was **MEASURED and eliminated as the cause of coverage**
(session 10: position, context and model strength all eliminated); the same model at LOWER thinking in ONE call recovered five findings seventeen runs never found once the
QUESTION changed. Blind spots are **per-model and disjoint** (`3.5-flash` never finds #12/#14/#18/#10b, `3.6-flash` never finds `SKIP_CONNECTION`/loss-config/CUDA `Event`;
both score 11-13), which argues for VARYING the model; and in slice 6 the cheapest tier won outright (flash-lite 0.799 beat gemma-4-31b 0.732, Voyage and Cohere). The one place
strength is explicitly required, with evidence: cross-language alignment ("route the alignment reasoning to the top of the generator chain, never to a weak tier").
**THE HONEST GAP: the lean `REPORT` template had never been run on a cheap tier.** The measurement was nearly free (the saved lean prompt, STUFFED, scored against `EXPECTED.md`
on `gemini-3.5-flash-lite` and `gemma-4-31b-it`; if either reached ~13/19, "reports stop being capped at ~20 a day").
**UPDATE: slice 8 job 9 ran it on flash-lite — ~8 of 19 findings, 2 of the 5 that carry the story, and it broke the comparability gate — so the report keeps the strong chain;
11.9 stands only for the other nine calls of a report, which is where routing already sends cheap tiers.**

#### What section 11 does NOT change

No code. `REPORT_MAX_TOKENS` stays **32,000** (measured to work at `MEDIUM`). Check 1 stays a refusal. Every task chain named here belongs to **Step 2**, and the
Fast/Balanced/Deep control to **Step 3** (Step 2 plan §19: Effort and Strength). Only the nine decisions are written down instead of re-derived.

### 12. THE OUTLINE — build step 2's design, decided 2026-09-14

*Decided with the user before writing it. Four of the calls are theirs, and one turned a single rewrite into a three-level ladder.*

#### 12.1 What the outline is FOR, in one sentence

A checklist of every chunk, marked sent or not sent, placed before the evidence.

> **It lets the model tell "it is not there" apart from "I was not shown it."**

Without it a gap in OUR retrieval is reported as a defect in the USER's code, a confident false finding (the worst failure this tool can produce): the paper states gradient
clipping, retrieval drops the chunk holding `CLIP_NORM = 1.5`, and a model with no outline writes "the code does not implement gradient clipping."

#### 12.2 The problem - measured 2026-09-14 on `labpilot/` alone

410 chunks, 94 files: outline PER CHUNK **10,592 tokens** (41% of `PROMPT_BUDGET` before any evidence); PER FILE **2,193** (8%). `cost = n × h̄`, `h̄ ≈ 20-26` tokens per row.
The saving is the chunks-per-file ratio, only 4.4 here (many small files); the worst measured case: **8,334 parts cost 210,541 tokens** against 26,000, a table of contents 8x
the whole prompt.

#### 12.3 THE DESIGN IS A LADDER, NOT A REWRITE

*The user's call, better than the single per-file shape first proposed.* Three renderings, measured per unit: (1) **per chunk**, one row per chunk with full header, **25.8 /
chunk**; (2) **per file + `defines:`**, the file's distinct top-level labels, **44.9 / file** (renders `train.py  B-40..B-70  31 parts, lines 1-1420 · none included` +
`defines: load, Tokenizer, Trainer, evaluate, main`); (3) **per file plain**, **23.3 / file**. **Take the richest level that fits the outline's share of the budget** (a few
hundred chunks get per-chunk honesty for ~2,000 tokens; a repository degrades to 2, then 3). **`defines:` is worth less than it looks: 410 chunks compress to 270 distinct
labels (ratio 1.5), mean 2.9 labels per file, max 16**, so level 2 is 2.5x cheaper than level 1, not 20x.

#### 12.4 The stuff path keeps a FILE LIST and nothing more

*The user's call.* When everything fits nothing is dropped, so "what you did not get" disappears. A per-chunk outline there would be pure duplication (`_text()` already renders
`{id}  {chunk.header}` above every included chunk). The file list stays because it is cheap navigation, not accounting. The arithmetic: with `REPORT` ~2,000 tokens and 341.6
per chunk, `341.6n + 25.8n + 2,000 ≤ 26,000 ⇒ n ≤ 65`: the stuff zone is about **65 chunks across both sides**, where a per-chunk outline would cost only ~1,700 tokens (cheap, and still duplication).

#### 12.5 THE FILE RANGE ASSUMES CONTIGUITY, AND A TEST MUST PIN IT

*The user's call: a test, not a workaround.* `B-40..B-70` is only true if every chunk of one file sits together in id order. It does today (`chunk_source` walks files in sorted
order and `assign_ids` numbers the tuple as it arrives) but nothing enforced it, and if it breaks the range silently names the wrong chunks, the citation failure this section
exists to prevent. Same class as slice 2's sorting rule: sorting was correctness there, contiguity is correctness here.

#### 12.6 PER FILE IS NOT FREE EITHER - recorded, not capped

2,193 tokens for 94 files is 8%; a 500-file repository would be ~11,000 tokens, **42% of the budget**, with no evidence sent yet. Level 3 is the answer, beyond it a cap or a
per-directory grouping. *Neither was built at the time (no 500-file fixture, so the number would be a guess dressed as a decision — the reason `MAX_ARCHIVE_BYTES` stayed an
xfail).* **BUILT 2026-09-28 for the planner's map: Step 2 §12 `build_map`, level 3 counts files by folder.**

#### 12.7 "NOT INCLUDED" IS THE WRONG WORD, AND IT IS `instructions.py`'s JOB

*Raised by the user: a user who uploaded the whole file will be confused by "31 parts were not included".* The phrasing blames the upload for our own retrieval limit. WRONG:
"31 parts of train.py were not included". RIGHT: "I searched 21 of 82 parts of your code. Clipping was not in those 21; it may be in the 61 I did not retrieve." It only appears
when the corpus really did not fit, and the API already reports `chunks: {side: {total, sent}}` (the page renders `21/82 chunks`). **The wording rule belongs in the REPORT
template and the evidence-basis axis already demands it** ("seen in one, not found in the provided context" must read "not present in the retrieved context", never "absent
from the code"); whether the lean 1,997-byte rewrite still carries that rule was **UNVERIFIED** (losing it is a live defect in the most dangerous direction). Step 2's job:
`context.py` decides what the model READS, `instructions.py` what it WRITES.

#### What build step 2 changes, and what it does not

`prompts/context.py` `_outline()` → the ladder; `prompts/builder.py` `reserve()` follows automatically. `_text()`, `assign_ids` and every id are untouched, so citations are
unaffected; `retrieval/` is step 3. One over-estimate was knowingly left: `reserve()` adds an id prefix for EVERY chunk because selection happens after reserve (fixed at 13.1).

### 13. THE SELECTOR, AND THE SCENARIO MATRIX BEHIND IT — decided 2026-09-14

*Build step 2 shipped; step 3 was stopped before a line was written, because the user asked why A should be filled before B and the answer in this file did not survive the
question. One item OVERTURNS a rule carried since 2026-08-14.*

#### 13.1 Build step 2 is DONE, and it exposed the next bottleneck

Measured on the same 8,333-part upload: outline PER CHUNK 187,695 tokens of 26,000; PER FILE **26**. `_outline` is a LADDER taking the richest level that fits
`OUTLINE_BUDGET`; a side where everything was sent gets a plain file list. **Fixing it made the next defect visible:** `reserve()` (**a 24,899-token over-estimate hiding behind the per-chunk outline**) charged a `B-1234 ` id label for EVERY chunk in
the corpus though only the selected handful is printed — before: reserve 25,616 of 26,000, room 384 → **4 chunks of 8,333**; after: reserve 759, room 25,241 → **266 chunks**.
Without removing it the outline fix would have bought 0 → 4 instead of → 266. The real ~3-token per-chunk charge belongs in the SELECTOR, which charges per chunk as it packs.

#### 13.2 "FILL A BEFORE B" IS REJECTED — and this file has said it since 2026-08-14

The old argument: *dropping part of B is recoverable (A still tells us what to look for; report "not found"); dropping part of A loses a statement we never learn exists.* The
asymmetry is REAL (A dropped = unknown unknown, B dropped = known unknown) and still does not earn A priority:
1. **It covers `verify` only.** Session 10: removing side A ENTIRELY and asking "what could go wrong?" recovered **five findings seventeen comparison runs never found once**;
   seven of the nineteen live in B alone with no A anchor. The flagship runs both kinds of question.
2. **Half the scenarios have no reference.** Code-vs-code is SYMMETRIC ("never say one side is wrong, say only that they differ"); A-before-B biases it by **upload order**.
3. **The slots are the user's choice** (`POST /artifacts` takes `side` as a form field; nothing infers it).
4. **THE KILLER, the user's: "A before B" means A has NO CAP.** A 30,000-token reference takes the whole budget and B gets **zero**. A comparison with one side is not a comparison.

And the rule was never load-bearing: **when A fits, A-before-B and a fair split give the IDENTICAL answer**, so the fair rule loses nothing and cannot starve a side.

#### 13.3 THE RULE: equal share, and the leftover flows over

Pass 1: each side takes up to its share, `SIDE_SHARE = 0.5`. Pass 2: anything unspent flows to the other side.

| case | fixed halves (old) | A before B | share leftover |
|---|---|---|---|
| A small, B large | **wastes A's half** | good | **good - identical** |
| A large, B small | wastes B's half | **starves B** | good |
| both large | fair | **starves B** | **fair** |
| one artifact | half wasted | - | **all of it** |
| code vs code | fair | **biased** | **fair** |

It fixes the measured waste (14,273 tokens sent of 20,000 on the sample pair). **`SIDE_SHARE` is a KNOB, not a law** (slice 8 may sweep it). **If a capability ever wants a side
weighted, STEP 2's PLANNER passes that in** — the only layer that knows which capability is running.

#### 13.4 THE SCENARIO MATRIX — arrival order is irrelevant, TYPE decides

*The user's framing: the user sends whatever they want, however they want, and the system must be ready for every shape.* **Artifacts are STATE, so when they arrive changes
nothing** (turn 1 upload A → summarize/find_bugs; turn 4 upload B → + verify, align, explain_divergence; both at once, one by one, or B first: identical outcome — what the
ingest/ask split bought). **What decides the MODE is the artifact TYPE, known before any model call:** A = document + B = code → ASYMMETRIC (extract claims from A, verify in B);
A = code + B = code → SYMMETRIC (no claims exist: generate topics, search BOTH, compare topic by topic); one artifact → summarize, find_bugs; none → answer_question.
`sources/defaults.py` already splits `DOCUMENT_SUFFIXES` from `CODE_SUFFIXES`, so the planner can pick the mode from the filename for free (corrects an earlier claim that the
model decides the mode in its report). *(Step 2 plan §18.1 later withdrew the suffix rule and "roles" idea: the planner chooses from the question and the corpus map.)*

#### 13.5 A IS READ WHOLE, B IS SEARCHED — the asymmetry is ACCESS, not budget

Call 1 `extract_claims(A)` over ALL of A (no retrieval, no B); per claim `search(B, claim)` then `verify(claim, hits)`. A is read completely because a missed claim is a question
never asked; B is searched because it is too big to read; **they never share a budget here.** It works because A is small (`A_paper.md` ~3,900 tokens, a typical paper
8,000-15,000, against 26,000). **B still gets a WHOLE read when both exist**: `find_bugs` is a 1-artifact capability, so the planner runs it on B alone in its own call (where
session 10's five extra findings came from).

#### 13.6 ONLY ONE PLACE SHARES A BUDGET

Step 2: A whole (own call) + B whole (own call) + B searched per claim. TODAY: A and B in ONE prompt, so they share. Step 2 makes the question stop existing, but the flagship
report and the stuff path still share, so the split rule has to be right today.

#### 13.7 Three holes this opened, recorded rather than built

1. **A HUGE REFERENCE HAS NO DESIGN** (claim extraction assumes A fits one call; a reference *repository* needs its own map-reduce, one pass per file then a merge) — a Step 2
   hole, **now Step 2 slice 12 (was 9; D26-D28)**.
2. **LOW COVERAGE SHOULD ASK THE USER, NOT GUESS** *(the user's idea)*: on a huge repo `sent 266 of 8,333` is 3% coverage and a confident report over 3% is the wrong answer; the
   honest one: "I could not find what you asked about in the 266 parts I retrieved of 8,333. Point me at a file or a folder and I will look there." The same pattern as a missing
   artifact, applied to COVERAGE instead of PRESENCE. Needs the agent + the UI (Step 2 + Step 3).
3. **MAP-REDUCE'S COST OBJECTION IS STALE** ("79 calls for one file against an OpenRouter cap of 50/day" was written before quotas were measured; Gemma ×4 is 57,600 a day,
   Flash-Lite ×4 2,000; a 94-file walk is 94 calls). The blocker is now **LATENCY**; re-cost it rather than inherit the old verdict.

#### What step 3 builds

`retrieval/` — Chunk in, Chunk out, equal share + leftover, charges the id label. `api/` — SearchHit / StoredChunk → Chunk (step 4, with `ask()`). `retrieval/` is CORE and
`store/` an ADAPTER, so the selector CANNOT see `SearchHit` or `StoredChunk` (`test_architecture` forbids it; both store types also lack `side` and `artifact_id`); the converter
now would be a function with no caller.

### 14. SLICE 7 BUILD STEPS 1-3 ARE SHIPPED — 2026-09-14

*Built, measured and mutation-tested in one session on `feat/ask-path`. Three of the decisions are the user's, two overturn something already written.*

#### 14.1 What shipped

| step | landed | mutations |
|---|---|---|
| **1** | `store/reader.py` — `measure()` and `read_chunks()` | 4, three real and firing alone |
| **2** | `prompts/context.py` — the outline ladder, and `reserve()` fixed | 4, all real |
| **3** | `retrieval/selector.py` — equal share + leftover; `dumb.py` deleted | 3, all real |

787 passed, 48 skipped, 1 xfailed, ruff clean. **Step 1:** `measure()` is one round trip and no chunk row crosses the wire; `read_chunks()` reads everything in `chunk_index` order
and is only correct to call once `measure()` says it fits; no size is stored (`count(*)`/`sum(length(...))` on demand). **A correction to this file's own SQL sketch:** the flat
`+ 1` for the `embed_text` newline over-counts one character per header-less chunk (right by luck on real corpora, wrong by rule, silent); a `case` expression counts it exactly.
**One mutation SURVIVED and is recorded:** swapping the LEFT JOIN for an INNER changes nothing because `write_artifact` refuses a zero-chunk artifact, so "stored and empty" is
unreachable (kept because it is free and honest; no test pins it, like the `::vector` cast in `search.py`). **Step 2:** the 187,695 → 26 tokens measurement above; and
`reserve()`'s all-chunks id label (13.1) exposed immediately. `instructions.py` taught the old shape in all five templates ("Parts marked 'text NOT included'"), reworded in place
in four locations (FULL and CORE too: a frozen baseline whose prompt describes a format we never render could not be re-run). **Step 3:** A small/B huge → A 4, B 48, 19,912 of
20,000; A huge/B small → A 48, B 4, 19,912 (exact mirror); both huge 24/24, 19,488; B only 0/49, 19,894. `test_neither_side_is_privileged` is the mirror; re-implementing "fill A
before B" fires **four** tests: that decision is defended by code, not a paragraph.

#### 14.2 `VECTOR_TOP_N` WAS DOING TWO JOBS — the user found the conflation

One number answered two questions (how many the RERANKER SEES; how many we SEND if reranking failed). **Four numbers, four jobs:** `SEARCH_LIMIT` 50 (what search returns, per
side) · `RERANK_WINDOW` (what the reranker sees, NEW, see 14.3) · `RERANK_TOP_N` 10 (what survives reranking) · `VECTOR_TOP_N` 25 (what we send when NO reranker ran).

#### 14.3 THE RERANK WINDOW IS PER TIER, NOT GLOBAL — the user's call

*This supersedes 10b's "the cut comes BEFORE the reranker".* The cut to 25 bought three things (a bad reranker could only re-order; half the rerank tokens; **Voyage
reachability**: 50 ≈ 16,900 tokens refused, 40 refused, 30 passed). Two things cut the other way, stronger: (1) **the cut discards exactly the queries reranking is best at**
(`constant` questions, +0.186 MRR where the bi-encoder is worst at 0.354; `D2` sits in the FORTIES on codestral, so cut at 25 it is gone before any reranker sees it); (2) **the tier
the cut protects is no longer at the front** (the four LLM tiers beat Voyage; flash-lite is listwise, 50 documents ≈ 17,000 tokens against a 1M context). **THE ANSWER IS PER
TIER, and the shape exists:** every reranker carries `max_documents`; Voyage's said 1,000 (the BILLED tier's limit, wrong twice, since the free constraint is TOKENS); set it to
its measured 30 and let `chain.rerank()` (the one layer that sees documents and tier) hand each tier what it can take: `reranker.rank(query, documents[: reranker.max_documents],
top_n=top_n)`. flash-lite sees all 50, Voyage sees 30 and ANSWERS instead of burning a request on a refusal.

> **A limit that belongs to one provider should be modelled on that provider, never averaged into the pipeline.** (Same lesson as `quota_pool` and Groq's `context_window = 8_000`.)

Slice 8 still owns the sweep (its measurement 7, "where the cut goes").

#### 14.4 Step 4 is the ask path, and its decisions are taken

`ask(conn, a_id, b_id, *, question, client) -> Comparison`: (1) `measure(A)` + `measure(B)`, fits `PROMPT_BUDGET`? yes → `read_chunks` both, STUFF; (2) embed the question with
EACH artifact's own model, search per side at 50; (3) gate `should_rerank(scores)` (`SKIP_MARGIN` None, so always yes); (4) rerank PER SIDE, never merged, each tier taking up to
its own `max_documents`; (5) SearchHit/StoredChunk → Chunk adding `side` and `artifact_id`; (6) select → build_prompt → generate.
- **D1 — a chunk's `side` comes from the STORED artifact row, not the request slot.** `_artifact_id` is `f"{side}-{hash}"`, so the side is baked in and the same file uploaded
  twice is two corpora; two `A-...` ids must be REFUSED (the prompt would have no side B).
- **D2 — `skip()` truncates to whatever `top_n` it is handed**, so the degraded path must not get the reranked number: call `rerank(top_n=None)` and cut afterwards on what
  happened: `kept = RERANK_TOP_N if ranking.model != SKIP else VECTOR_TOP_N` (`Ranking` already carries `model=SKIP`).
- **D3 — two artifacts may hold two different embedders** (`ingest_artifact` picks per artifact): embed the question once per DISTINCT model, refuse a model not in `MIGRATION`.
- **D4 — `ask()` had no caller until step 6** (scaffolding with a scheduled consumer, like `write_artifact` after slice 4).

**THE TRAP THAT LIVES IN STEP 4** (why `tests/integration/test_retrieval_to_rerank.py` numbers its chunk ids from 100): `search()` returns `SearchHit.chunk_index`, an ID in the
corpus; `rerank()` returns POSITIONS in the list it was handed. `hits[p]` is right; treating `p` as an id cites the wrong file and line with full confidence. And
`UnknownArtifact` and `ModelMismatch` become reachable the moment `search()` has a caller, so they are mapped and come off `ALLOWED_TO_ESCAPE` at step 4, not step 6.

#### 14.5 What none of this decided

Every number is still slice 8's (`SEARCH_LIMIT`, `RERANK_WINDOW`, `VECTOR_TOP_N`, `RERANK_TOP_N`, `SIDE_SHARE`, `OUTLINE_BUDGET`, merged vs per side, whether reranking ships), but each is
now a NAMED CONSTANT with its job written beside it, so a sweep changes one number instead of a design.

### 15. SLICE 7 IS COMPLETE — steps 4, 5 and 6, 2026-09-14

*The ask path, the assembled rerank chain, and the door that finally takes IDS. Two of the defects below were found by the USER reading the code rather than by any test.*
804 passed, 4 skipped, 1 xfailed (unit + api + integration, ruff clean; smoke deliberately not run).

**Pieces 1-3 (2026-09-14, rebuilt piece by piece onto `main`):** the rebuilt embedding-time estimator, `ingest_artifact()` and `POST /api/v1/artifacts`. **Step 7 (never in the plan;
not recorded in sections 14-15 when written) was the REPOSITORY DOOR**, commit `a1415ca`: `POST /artifacts` takes a `file` **or** a `url`, `services.ingest_source()` stores a whole
repository (a file, a `.zip` or a git URL) as ONE artifact, and `MAX_ARCHIVE_BYTES` moved 50MB → 10MB so the old xfail became a real test (that is why the suite has no xfail left).

#### 15.1 Step 4 — `ask()`, the ladder

Same ladder as 14.4, with `task="query"` on the question embed. **Three new errors, and each status is an argument rather than a habit.** `UnknownArtifactId` is **404**
(`StorageUnavailable` is 503 because the database being down is OUR failure; an id we never stored is a fact about the REQUEST). `ArtifactSidesClash` is **422** (the side is baked
into the id, so two `A-` ids is not a comparison). **`ArtifactChanged` is 409, and it exists because the user refused "unreachable":** the draft left `ModelMismatch` in
`ALLOWED_TO_ESCAPE`, reasoning that we pass `model=` from the very row `search()` checks it against. But `measure()` and `search()` are TWO round trips and `write_artifact`
DELETES then re-inserts, so re-ingesting an artifact with a different embedder moves the model under a request already in flight: nobody's bug, retrying fixes it (a 500
would blame us, a 404 the user). **`ALLOWED_TO_ESCAPE` is now clear of `store/`**; `RerankError` took its place (the rerank chain swallows it per tier and ends in `skip()`, exactly
the `LLMError` case).

**THE SEARCH PATH WOULD HAVE LIED, caught while designing:** `build_context` sees only the RETRIEVED chunks, every one "kept", so it rendered "FILES - every part below is included"
over 20 rows of an 8,333-part corpus. `build_context` now takes `totals` (which `measure()` supplies free) and a partial side says: `SIDE B — 20 of 8333 parts were retrieved for
this question. The rest were NOT searched, and you have not read them.` **`_fits` is deliberately conservative:** it charges the outline its full `OUTLINE_BUDGET` because the real
cost cannot be known without the headers (the thing the check avoids fetching), so a corpus near the line is SEARCHED when it could have been stuffed (the safe direction; a wrong
`yes` reads ~14MB to learn it did not fit). **`_best` takes its reranker INJECTED** (`rank=`, defaulting to the assembled chain), so the door is testable with no provider (the shape
`LLMReranker` and `LLMClientDep` use).

#### 15.2 Step 5 — the chain assembled where both adapters are visible

`api/reranking.py`: `RANKING_CONFIG`, `PROVIDERS`, `_listwise`, `CHAIN`, `rank`. **IT WAS BUILT AND NOT CONNECTED:** `_best` still defaulted to the bare `rerank`, so the ask path
would have used ONLY the cross-encoders and never the four tiers that beat them; a chain built and never bound still returns rankings from the weaker half of the measurement
with nothing to report it. `test_the_ask_path_reaches_the_assembled_chain_and_not_the_bare_one` pins it. **The configuration is worth more than the choice of model:**
flash-lite TUNED MRR 0.799 vs UNTUNED 0.706 (0.093 apart, wider than flash-lite vs Cohere's cross-encoder); every Gemini tier SHIPS `thinking=MEDIUM` for generation, so reusing a
`CHAIN` entry unchanged throws the gain away while the ranking still looks plausible. **`_listwise` is a FACTORY, not a loop body, and that is load-bearing:** inline lambdas would
close over the loop VARIABLE, so all four tiers would call whichever provider the loop ended on while each reported its own name (the chain looks healthy, one model answers
everything, the measured order is fiction). The code already existed in `tests/smoke/test_rerankers.py` (the `GEMMA_4_26B` shape: working code trapped where production could not
reach it); the smoke test now imports the production objects.

#### 15.3 Step 6 — `/compare` takes ids

`POST /artifacts [file] → {"artifact_id": "A-9f2c..."}` once; `POST /compare {a, b, question}` per turn. JSON, not multipart. `question` carries NO `min_length` on purpose: a blank
one must come back through our own envelope as `invalid_question`, and a Pydantic constraint would make FastAPI answer in ITS shape (two error formats from one endpoint).
`services.compare()` is DELETED. **413 STAYS (removing it was my error):** `ArtifactsTooLargeToCompare` is a 413 raised inside `_prompt`, which `ask()` calls, and
`RequestBodyLimitMiddleware` wraps every route. **A real bug a test caught:** the route passed `questions=` instead of `question=` (every `/compare` would have been a
`TypeError` and a 500), found by the test asserting the VALUES reach `ask()`, not by the one asserting a 200.

#### 15.4 The test migration was smaller than 23 tests suggested

`test_compare.py` held 23 tests and **eleven were never about comparing**: `read_artifact` is the guard, SHARED by both routes, so testing it through `/compare` was one test per
COMBINATION rather than per failure. MOVED to `test_artifacts.py`: binary, size limit ×2, empty, pdf, scanned pdf, non-ascii, broken notebook. DELETED as redundant: "a rejected
upload never reaches the model" (the loader runs INSIDE `ingest_artifact`, so stubbing it removes the very code that refuses). REWRITTEN for ids: 11 tests, the new
`test_compare.py`. REWIRED: `test_api_over_the_chain.py` (store stubbed at its own door; prompt, chain and provider HTTP stay real).

#### 15.5 What slice 7 did NOT do

`web/app.js` still posted two files to `/compare` and got a 422 (**fixed 2026-09-15**: each slot uploads on its own to `POST /artifacts` and keeps the id; `/compare` gets
`{a, b, question}` as JSON; the page also shows chunk count, embedder, the embed-time estimate with `slow` as a warning, a git URL field, and `sent/total` per side so a searched
side reads `B: 25/1094 chunks searched`). Every number is still slice 8's and each is a NAMED CONSTANT (`SEARCH_LIMIT` 50 · `VECTOR_TOP_N` 25 · `RERANK_TOP_N` 10 · `SIDE_SHARE` 0.5 ·
`OUTLINE_BUDGET` 4,000 · per-tier `max_documents`). Two measurements this slice ADDED to slice 8: whether the per-tier rerank window beats a global cut, and whether
`explain_divergence` really needs the strongest tier (11.9: session 10 measured model strength out as a cause; the lean `REPORT` had never run on a cheap tier).

### 16. SLICE 7 IS CLOSED — the review pass, 2026-09-15

*The twenty-fifth session wrote almost no product code and found three real defects. It began by restoring two test files a session rewind had reverted on disk, wrote the tests the
repository door shipped without, then swept every slice 7 invariant never mutated. Suite 808 → 843 passed, 4 skipped, 0 xfailed, ~175s (was ~260s).*

#### 16.1 The rewind, and the rule it produced

`test_compare.py` reverted to its `eef2254` version and `test_reranking.py` deleted — **on disk only**, every commit intact and pushed. Hashing the working-tree blob against every
commit proved nothing unique was in it and `git checkout --` restored both. > **After a rewind, check git before rewriting anything.** The restore moved the project FORWARD
(668+1 failing → 808 passing).

#### 16.2 DEFECT 1 — the suite was spending live rerank quota on every run

The worst finding, **measured, not suspected**: any test reaching the search branch of the ask path went straight to real providers (Gemini 3.5 Flash-Lite → 3.1 Flash-Lite → Gemma
26B → Gemma 31B → Cohere → Voyage → Cloudflare), though tests must never call Cohere (its 1,000/month is shared with chat and embed, and it is the rerank primary). It hid behind a
Python detail: `def _best(question, hits, *, rank: Callable[..., Ranking] = _rank):` — **a default argument is evaluated once, at import time**, so `monkeypatch.setattr(services,
"_rank", ...)` rebinds the module name and never reaches it; a path that looked stubbed was not. > **Spending quota makes a suite slower, never redder.** Found by patching
`requests.post` to raise and watching four provider URLs scroll past. **The fix keeps `labpilot.api.reranking.CHAIN` EMPTY for every non-smoke test** via an autouse fixture in
`tests/conftest.py`: an empty chain is not a mock (`rerank()` walks it, finds nothing, ends in `skip()`, the degraded path we ship), so the default under test is "no reranker was
available" and a test wanting reranking supplies its own. `test_no_default_test_can_reach_a_real_reranker` (in `test_suite_rules.py`) fires **alone** across 750 tests when the
fixture is removed.

#### 16.3 DEFECT 2 — the API lied about how much it had read

Found by the new system test, the first to run both doors against each other. On the search path: corpus 120 chunks stored; the PROMPT said "20 of 8333 parts were retrieved"
(honest); the RESPONSE said "25 of 25 chunks" (not). `ask()` computed the true per-side totals for `build_context` but **`Comparison` never carried them**, so the router counted
the chunks in hand and called that the total — the number the page renders to prove the file was really read claimed it was read **whole**. `Comparison.totals` now carries it
and the router prefers it. > **Fixing a lie in one layer does not fix it in the next** (the prompt and the response are two audiences for one fact).

#### 16.4 DEFECT 3 — a dead line, reported and NOT fixed (REMOVED 2026-09-28)

In `ingest_source`: `chunks = tuple(replace(chunk, artifact_id=artifact_id) for chunk in chunks)`. Removing it changes nothing: `ChunkRecord` has no `artifact_id`, `_row` takes the id
from the `ArtifactRecord`, and no production code reads `Chunk.artifact_id` (every match is a SQL column name). No test, because there is no behaviour to pin: *a mutation that
survives is not always a bad test; sometimes it is a false claim in the code.* Reported rather than fixed (deleting production code was not what the review was asked to do), then
removed on 2026-09-28.

#### 16.5 What the new tests cover, and what was DELETED

**35 tests across four levels, every invariant mutation-tested:** unit `test_ingest.py` 6 (hashing the container instead of the file paths breaks the zip-vs-clone test alone) ·
unit `test_ask.py` 5 (`task="document"`, the wrong embedder, a retired model, an outage, `top_n` handed down) · api `test_artifacts.py` 11 (the case fold, the exactly-one-of guard,
each of the four error mappings) · integration 13 (per-file numbering fails four tests with `UniqueViolation: chunks_pkey`). **Two tests were written and DELETED for never
firing alone** (re-uploading the same file; a 404 for a missing id): one test per COMBINATION rather than per failure. **The highest-value single test**,
`test_two_uploads_then_a_question_produces_a_cited_answer`: the model gives a pointer and we read the line back from our own copy **after it has been through Postgres** (a dropped
header or shifted `start_line` resolves to the wrong line with nothing raising). Its first fixture could not catch that: a one-chunk file starts at line 1, so forcing
`start_line=1` broke nothing (proven by mutation); the fixture was widened to two functions so the cited line sits at **line 56**, and the mutation then fires alone.

> **A fixture that cannot fail is worse than no test.** Two shapes cause it here: ids numbered from zero (an id is indistinguishable from a position) and a single chunk (a
> correct offset is indistinguishable from a lost one).

#### 16.6 The mutation sweep steps 4-6 never got

Sections 14-15 recorded mutations for steps 1-3 and none for 4-6. Six were run; four fired alone, **two survived**: P1 the degraded cut uses `RERANK_TOP_N` (fires alone) · **P2
`top_n` handed DOWN to the chain (SURVIVED — gap closed)** · P3 the LLM tiers keep their generation settings (alone) · P4 every tier gets the full window (alone) · **P5
`min_length=1` on `question` (SURVIVED — gap closed)** · P6 two artifacts from the same slot accepted (alone). **P2:** `_best`'s docstring says the cut must happen AFTER the
call (`skip()` truncates to whatever it is handed); its test pinned the CUT but injected its own `rank`, so it never observed the ARGUMENT; a new test records the call.
**P5:** `CompareRequest` documents a deliberate decision (no `min_length`, or FastAPI answers in ITS shape); the test sent `"  "` and **two spaces clear a `min_length` of 1**; the
empty string pins it, now parametrized in. > **A docstring recording a decision is not a guard.** **Three mutations were BROKEN rather than surviving** and each looked exactly
like a dead test (deleting an `except` left a `try` with no handler; two anchors matched zero or three times): `mutate.py` now refuses a non-unique anchor and prints "the MUTATION
is broken, not the test".

#### 16.7 What was deliberately NOT added

No new smoke test (the repository door calls no LLM, its embedder is covered by `test_embedders.py`; a smoke test would spend quota to prove wiring integration tests prove free —
*"do not add tests to raise a number"* binds hardest where the test costs quota). The dead line of 16.4 was reported, not fixed (removed 2026-09-28). **`MAX_ARCHIVE_BYTES` vs
`MAX_UPLOAD_BYTES` was a NAMED OPEN QUESTION — CLOSED 2026-09-28: both are 10MB now (Step 2 §12.6).** The archive limit was 10MB and the per-file upload limit 5MB, so a zip
between the two was refused by the upload guard and the archive limit never fired — the same shape as the xfail slice 7 had just closed, one door further in.

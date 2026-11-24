# Step 1, slice 6: reranking

[Docs home](../README.md)

## Slice 6 — the theory, recorded 2026-09-09

*Session 19 wrote no source: the lesson came first, the user pushed back on the cost arithmetic four times and every push was right.
What came out: **verified provider facts**, a rule about what can and cannot be batched, and a measurement slice 6 owed before closing.*

### The concept — and why the embedder cannot do this job

A **bi-encoder** (`embed/`) encodes query and chunk **separately**: `s(q,d) = E(q)·E(d) / (‖E(q)‖‖E(d)‖)` with `E(d)` independent of `q`.
That is what lets a vector be computed at ingest and stored, and it is the weakness: the chunk's vector was made **before the question
existed**, one fixed summary good for every future question. A **cross-encoder** (a reranker) puts both into **one** sequence:
`s(q,d) = f(q ⊕ d)` and `s(q,d) ≠ g(q)·h(d)` for any `g, h`; self-attention runs over query and chunk tokens together in every layer (**late
interaction** vs **early interaction**). The worked example is our worst miss: query `D2` ("gradients are clipped at a global norm of
1.0"), answer `CLIP_NORM = 1.5`; in the bi-encoder `clipped` and `1.5` never meet (codestral ranked it 46th), in a cross-encoder attention
connects them. **The non-factorisation is the whole story:** it is why a cross-encoder is more accurate, why it cannot be precomputed or
indexed, and why it cannot be batched across queries.

### What batches, and what does not — the rule

> **Batching works when the inputs are independent. It fails when they must be joined.**

Embedding `E(text)` batches (96 per request, built); reranking `f(q ⊕ d)` does not batch across queries (no provider's `query` field takes
more than one string; measured later on three providers: 400 / 400 / 422). Query embedding is therefore not a quota problem (30 claims × 20
tokens = 600 tokens, one request; one ingest = 384,000 tokens, 21 requests): **the embedding quota only binds at ingest.**

### The provider facts — read from the official docs 2026-09-09

| | Cohere | Voyage | Cloudflare |
|---|---|---|---|
| documents per call | up to 100 per search unit | up to 1,000 | — |
| free allowance | **1,000 API calls/month**, 10 req/min | **200M tokens**, one-time | **10,000 neurons/day** |
| billed by | **the CALL** | tokens | tokens (283 neurons / 1M input tokens) |

**Voyage publishes the token formula** `tokens = t_q × N_d + Σ t_{d_i}`; with our measured 229-token chunk and ~20-token query a 50-chunk
call is `20 × 50 + 50 × 229 = 12,450` tokens (the budget section had assumed 25,000 from a 500-token chunk we do not have). Real capacities
roughly double what was recorded: Voyage ~16,000 calls, Cloudflare 3.5 neurons per call = **~2,850 calls PER DAY**, Cohere 1,000/month
whatever the document count. **A free lever nobody had noticed: Cohere bills per call up to 100 documents and we send 50**; sending 100
costs the same and can only raise recall (on Voyage and Cloudflare it doubles the token cost): a per-provider choice for slice 8.

### Two counting errors in this file, now corrected

(1) **`r = 5` was wrong:** the 5 came from the *verify batching* line (5 claims per **generation** call). Claim extraction yields ~14 claims
and each needs its **own** search. **Batching `verify` saves generation calls and no rerank calls.** (2) **`14` is itself a guess**, probably
low (one fact per claim forbids merging: "lr 3e-4 with cosine decay and 500 warmup steps" is three claims; re-retrieval raises it again).
**The honest form is `r = N + 1`, with `N` unknown until Step 2 exists.**

### A process failure worth more than the numbers

Asked "how many rerank calls per report?" I gave four different answers in four messages (5, 14, ~4, 1-2), each quietly changing an
assumption and presented in tables so guesses looked like measurements. **When a question has no answer yet, say so; a number with no
derivation is worse than a blank, because a blank cannot be quoted back six weeks later.** The deeper fix: stop estimating `N` and find the
provider whose budget makes `N` stop mattering.

### Four ways to spend less on reranking — from the literature, 2026-09-09

(1) **Run the model yourself and batching returns** (a cross-encoder cannot merge two queries but can score many pairs in one forward pass;
MiniLM-class 22M: 100 documents in 50-80 ms; "one call per query" is an API billing shape, not a model limit). (2) **Fan-out, merge,
deduplicate, then ONE rerank** against the *original* question; the deciding rule is **do all these searches serve ONE answer or N separate
answers?** It applies to `answer_question`, **not to `verify`** (merging destroys the claim-to-chunk mapping). (3) **Gate it:** skip when
the margin `m = s(1) − s(2)` exceeds `τ` (15-80% compute saved in the literature; **reranking can make results worse when the first stage
was already confident and correct**); `τ` is calibrated, never chosen. (4) **Adaptive depth** (provider-dependent).

### The decision ladder

(1) Does the WHOLE artifact fit the prompt budget? Yes → send it all (no search, no rerank). (2) Too big → vector search, top
`SEARCH_LIMIT` (50). (3) Is the winner obvious (margin)? Clear → skip the reranker; close → rerank. (4) Send the final chunks; how many is
measured. The reason to cut 50 to ~10 is **quality**, not budget (50 × 229 = 11,450 tokens fits a ~24,000 budget): sending 50 gives
`recall = 0.994` but dilutes the signal and invites *lost in the middle*; sending 10 is sharper at `recall = 0.930`.

### THE MEASUREMENT SLICE 6 OWES BEFORE IT CLOSES

Run on the local ONNX model (free, repeatable, cache every result): (1) `r@10` and MRR before vs after reranking per corpus and embedder;
(2) how many chunks to send (5/10/20/50); (3) the gate; (4) wRRF fusion re-measured WITH the reranker. **Report the headroom captured**,
`(r@10_after − r@10_before) / (r@50 − r@10_before)`, because a raw +0.03 means nothing without knowing how much was available, and a free
instrument check: **`r@50` must not move** (a reranker only reorders). Rules carried from slice 5: this fixture may REJECT, never CONFIRM
(one query on the 45-query fixture is 35% of the headroom); name the corpus AND the embedder beside every number; judge by how many
independent ways a method was shown better. One number to verify: the file reported `recall@1 0.645` and `MRR 0.645` (settled later:
`0.645` was the MRR; true r@1 is 0.412-0.533).

### THE CHAIN ORDER STAYS — and what could change it

Chain 3 was NOT reordered (the user's decision 2026-09-09): Cohere → Voyage → Cloudflare → `ministral-3b` → `skip`, on the rule *spend the
bucket that expires anyway, bank the one-time grant*. Per query the quota shape argued the other way (Cohere 1,000/month smallest; Cloudflare
~2,850/DAY the largest renewing; local ONNX unlimited and it BATCHES), giving a candidate order local ONNX → Cloudflare → Voyage → Cohere →
skip — **a proposal with evidence, not a decision**; it could be killed by quality or by the 512MB budget (the ~120MB local model was
deliberately excluded from the container). *(Superseded: slice 6/8 measured the order and Cloudflare's model hurt; and the 512MB estimate
was itself 6x too high, which re-opens the local-reranker exclusion — Step 2 plan section 10.)*

### What slice 6 may NOT conclude

Whether reranking helps our data, roughly how much headroom it captures, how many chunks to send and whether the gate is worth having could
be concluded; **which provider is best**, that the chain-3 order is settled, that fusion is dead (retest with rerank on) and the real value
of `r` (needs Step 2) could not.

### Notes for the code, before a line is written

- **`rerank/` is an ADAPTER**: add it to `ADAPTERS` in `test_architecture.py` (or the build fails on "belongs to no layer"); it may import
  only `tokens` and `_text`, so it **cannot** see `SearchHit` and its signature is plain strings in, an order out
  (`rerank(query: str, documents: Sequence[str]) -> tuple[int, ...]`); the caller in `api/` owns the translation.
- `test_error_boundaries.py` fires the moment `api/` imports `rerank`: catch and map the error, or name it in `ALLOWED_TO_ESCAPE` with the
  reason; never delete the test.
- **A reranker must NOT inherit `HTTPProvider`** (the old slice-1 note predicting it is stale: that is a *completion* template and a
  reranker would fill four fields with fiction); follow the `embed/` precedent and write no `base.py` until the second reranker exists.
- **Tests must never call Cohere** (its 1,000/month is one bucket shared with chat and embed): use the local ONNX model, installed in
  `requirements-dev.txt` only (`test_no_runtime_requirement_would_blow_the_memory_budget` reads `requirements.txt` alone).
- **Probe cheapest first** when learning each wire shape: Cloudflare (~3.5 neurons), then Voyage (1 of ~16,000), **Cohere last** (1 of 1,000).
- **The 510-token trap is closed**, and the numbers depend on it: Cohere splits any document over ~500 tokens and bills each piece; the
  2026-09-05 cap fix put 0 of 4,889 chunks over (before it 43 of 1,094 were, and every rerank budget was wrong by up to 3x).

Sources for the provider facts: Cohere Rerank API reference and rate-limits page, Voyage reranker documentation and FAQ, Cloudflare Workers
AI pricing.

## Slice 6 — DONE 2026-09-11: built, measured, and NOT switched on

> **UPDATE: "NOT switched on" is OUT OF DATE.** Slice 8 (2026-09-16/19) measured reranking on twenty corpora and **it SHIPS**: slice 7
> wired the assembled chain into `ask()`, `bge-reranker-base` and the local MiniLM were deleted, and the LLM tiers lead chain 3.
> What follows is the measurement history and the rules it earned.

*The code was written, tested and mutation-verified (654 passed, 14 of 14 mutations real, 12 firing alone). The measurement then said
something nobody planned for, and then the opposite: **the cheapest reranker makes retrieval clearly WORSE and a better one clearly BETTER.**
Same corpus, window and instrument; only the model changed. So "does reranking help" is not a question about reranking.* Slice 6 landed on
`main` re-committed piece by piece (~40 commits, not a merge); `feat/reranking` is dead and behind `main`.

### What shipped

`rerank/` is the **seventh** package and the fifth adapter (`test_architecture` fired the moment the folder appeared: "belong to no
layer"): `contracts.py` (`Ranking`: an order, its scores, which model produced it), `errors.py` (`RerankError`), `defaults.py`
(`MAX_DOCUMENTS` 100, `MAX_DOCUMENT_TOKENS` 510, `RERANK_TOP_N` 10), `base.py` (`HTTPReranker`, written from three live probes), `cohere.py` ·
`voyage.py` · `cloudflare.py`, `registry.py` (`RERANK_CHAIN`) and `chain.py` (`rerank()` and `skip()`); plus **`retrieval/gate.py`**
(`margin()`, `should_rerank()`, core, not the adapter) and `scripts/retrieval/score_rerank.py` (the instrument, which validates itself).

### Probing first found things the docs do not say

All three providers were probed live before a line was written: **a list of queries is refused (400 · 400 · 422)**, so the no-batching rule
is MEASURED on three providers; empty documents give Voyage 400, Cohere 400 and **Cloudflare 500** (a caller's bug becomes *their* 500, so
`_check_inputs` refuses locally); Cloudflare `top_k` truncates the body with **identical neurons** (cost follows input, never output); Cohere
with 3 documents reports `search_units: 1` (per-CALL billing confirmed, and we send 50 of a free 100); Cohere headers carry
`x-endpoint-monthly-call-limit: 1000` **and `x-trial-endpoint-call-limit: 10`** (a second ceiling never recorded); an unknown field gives
Voyage **400** and Cloudflare **200, ignored** (prefer the provider that refuses). The published neuron rate is exact (87 tokens cost 0.024589
neurons = `87/1e6 × 283`), so a 50-document call is **3.52 neurons of 10,000 a day ≈ 2,840 calls daily**.

### The instrument validates itself before anything is believed

**Is a cross-encoder pointwise?** The per-pair cache is only valid if other documents in a call cannot change a pair's score: measured drift
Cloudflare 2.4e-07…6.3e-07, Voyage 0.0, and `score_rerank.py` refuses to continue above `1e-6` (had a provider normalised, every number would
have been quietly wrong, the identical-vectors bug of slice 4 again). **Can `r@50` move?** It cannot (a reranker only reorders); it is reported
on every run, and a change means "the measurement is broken, not the reranker".

### MEASUREMENT 1 — `bge-reranker-base` hurt, on every run

Cloudflare's `bge-reranker-base` over the dense top-50, four runs (MRR vector → reranked): quora/codestral 0.608 → 0.528 (r@1 0.412 → 0.353),
quora/google 0.674 → 0.527, requests/codestral 0.646 → 0.476 (r@10 0.933 → 0.711), requests/google 0.650 → 0.477. Headroom captured −100%, −∞,
−500%, −86%: not noise (0.17 MRR on 45 queries). **Once a reranker runs, it decides the order and the embedder almost stops mattering** (on
`requests` the reranked numbers were identical to three decimals for both embedders), so with reranking on, rank embedders on `recall@50`
alone. **Read the model name, not the word "reranking".**

### THE NEGATIVE RESULT WAS ABOUT THE PROVIDER — measured 2026-09-11

*The project nearly closed the slice on "reranking does not help us"; the theory section forbade it ("may NOT conclude which provider is best"),
so a second provider was measured.* At a 30-document window (Voyage cannot take 50 free), quora/codestral: **`rerank-3-lite` (Voyage)** r@1
0.588 (+0.176), MRR **0.725 (+0.117)**; `rerank-v4.0-fast` (Cohere) r@1 0.471, MRR 0.669 (+0.061); vector alone 0.412 / 0.608;
`bge-reranker-base` 0.353 / 0.520 (**−0.088**). Cohere cost 17 of its 1,000 monthly calls and was worth it. **A 43% relative gain in getting the
right chunk FIRST, from the same 30 candidates; the cheap model loses 14%.** **"Does reranking help?" is a question about a specific model; our
two differ by 0.205 MRR, three times the whole headroom.** The gain lands where theory says: `r@10` does not move (0.941 both ways) and all of it
is ordering inside the window. **It also inverts the gate:** with `bge` the best threshold never reranks; with `rerank-3-lite` the gate sweep
(`τ` 0.000 → 0.607, 0.030 → 0.708, 0.100 → 0.735, none → 0.725) is a small optimisation inside noise, so `SKIP_MARGIN` stays `None`.

### The second corpus was STOPPED at 8 of 45, on purpose

Voyage's 200M tokens are a **one-time** grant and 3 RPM makes 45 queries an hour; the user: do not spend a one-time grant on a heavy
measurement. The 8 scored queries were the entire `constant` block (the file is grouped by category): vector 0.390 MRR, `bge` 0.514, `rerank-3-lite`
0.533. **A fixture ordered by category cannot be truncated: the first k queries are a category study wearing a corpus study's clothes.**

### NINE RERANKER CONFIGURATIONS SCORED — and CONFIG matters as much as MODEL

Same corpus, embedder and 30-document window (MRR / r@1 / latency / budget): **`gemini-3.5-flash-lite` tuned 0.799 / 0.706 / 1.3 s / 500 a day** ·
`gemini-3.1-flash-lite` tuned 0.745 / 0.588 / 5.3 s / its own 500 · `gemma-4-26b-a4b-it` tuned 0.732 / 0.647 / 18.7 s / its own 14,400 ·
`gemma-4-31b-it` tuned 0.732 / 0.588 / 22.8 s / 14,400 · `rerank-3-lite` 0.725 / 0.588 · `gemini-3.5-flash-lite` UNTUNED 0.706 / 0.529 / 3.9 s ·
`rerank-v4.0-fast` 0.669 / 0.471 · *vector alone 0.608 / 0.412* · `bge-reranker-base` 0.520 / 0.353 · `ms-marco-MiniLM` (local) 0.472 / 0.294 ·
`ministral-3b-2512` 0.440 / 0.176. **Two rows are the SAME MODEL, 0.093 MRR apart: configuration was the larger effect.**

### `gemma-4-26b-a4b` — the MoE sibling, and MoE bought less than expected

25.2B total / ~3.8B active, but only **18% faster** than the 31B (median 18.7 s vs 22.8 s; flash-lite 1.5 s): the bottleneck is Google's serving of
Gemma, not its size (12.1 s on a 13-token prompt). It ties the 31B on MRR and beats it on `r@1` (0.647 vs 0.588), and has its own 14,400/day (two
Gemmas = 28,800). **One real defect: it sometimes returns an empty ranking `[]`** (~6%, 1 in 17 queries); a decline keeps the retrieval order, so
**a decline is invisible in MRR** and the rate must be counted separately.

### `gemini-3.1-flash-lite` — dominated on quality, valuable on QUOTA

3.5 dominates 3.1 on every axis (0.799 vs 0.745, 1.4 s vs 5.3 s), but Google's quota is per model, so 3.1 is **a second independent 500/day** at an
MRR still above Voyage, Gemma and Cohere: the two Flash-Lites are a natural pair at the top of the chain. Recall barely moves for any reranker
(`r@5`/`r@10` sit at 0.941 for all): only `r@1` and MRR have room on this saturated fixture.

### The two settings that did it, both measured

**`thinking=None`**: every Gemini tier ships `thinkingLevel: MEDIUM`, and for one 30-document ranking with an identical 109-token answer MEDIUM cost
3.88 s and 930 thought tokens, LOW 2.24 s / 351, no thinking field 1.28 s / 0. **A JSON response schema** (`responseMimeType: application/json` plus
an integer-array schema): gemma 45.5 s → 14.4 s and the reply stops being prose around an answer. `GeminiProvider.generation_config` carries both
(the Gemini twin of `extra_body`).

### Gemma: I was wrong about it TWICE, and the user was right to push

First I recorded it as unable to follow the format: that was **my parser** (Gemma reasons in prose and gives its ranking last, `3, 1, 2, 4`; a
left-to-right scan read the reasoning). **Reading the first 90 characters of a reply is not reading the reply.** Then I recorded it as too slow
at 95 s; the user ("something in your setup is wrong") was right: the missing JSON schema. The objection's premise was inverted (`gemma-4-31b-it` is
a 31B dense model, the *heavier* one; its larger quota made it look cheaper) yet right that the setup was broken.

### What this does to chain 3

The shipped chain (Cohere, Voyage×2, Cloudflare) did not contain the two best rerankers, and its last tier was worse than not reranking. The live
trade is **latency against budget** (flash-lite best and fastest on 500/day; gemma second and 11x slower on 14,400/day; `verify` at ~30 claims is 40 s
against 7 minutes). **Quota is not the only budget; latency is one too, and it is the one nobody writes down.**

### The cross-encoder table, and the generation line inside it

`ms-marco-MiniLM-L-6-v2` (2021, local, free) −0.136…−0.202 MRR · `bge-reranker-base` (2023, Cloudflare) −0.088…−0.170 · `rerank-v4.0-fast` (Cohere)
+0.061 · `rerank-3-lite` (Voyage) +0.117. **The dividing line is the model's GENERATION, not local-vs-API and not price**: both MS-MARCO-era
cross-encoders hurt on every run (a mechanism: trained on web prose, they fail on code, like `bge` collapsing on `structure` and `behaviour`
queries). It takes away the cheap answer to Step 2's cost problem (the local model is the only reranker that BATCHES, yet it hurts); a newer local
model (`bge-reranker-v2-m3`, the Qwen3 rerankers) is the open move, untried. The pointwise check refused the local model at first (int8 GEMM is
sensitive to batch **shape**; padding to 512 made it fifty times worse). **Set a numerical tolerance against the EFFECT SIZE, never against zero**
(local ~1e-2; API models stay at 1e-6).

### What this does NOT establish, stated before anyone quotes it

The provider flip rested on ONE saturated corpus (17 queries, `r@5` 0.941, a 30-document window = 37% of the corpus), one embedder, one window, and
Cohere (the primary) unmeasured then; it did not reopen fusion.

### What it DOES establish, and it changes slice 8's job

The candidate order from the slice 6 theory (local, Cloudflare, Voyage, Cohere) would have put the one model measured to hurt at the front; chain 3's
order became a **quality question with evidence**; "cheapest instrument" (Cloudflare's 2,840 calls a day made 124 measurements affordable) and
"best instrument" are different choices. **Measure the thing you will ship, not only the thing you can afford to measure.**

### MEASUREMENT 2 — how many chunks to send

On requests/codestral `bge` was worse at every window (top-1 0.533 → 0.311, top-10 0.933 → 0.711, top-50 +0.000), so `RERANK_TOP_N = 10` shipped as a
**number with no evidence**.

### MEASUREMENT 2 WAS MIS-SPECIFIED, and the correction is the useful part

**`recall@N` only ever rises with N** (r@1 0.533, r@5 0.800, r@10 0.933, r@20 0.978, r@50 0.978), so retrieval can find where MORE stops helping and
**never where FEWER starts**: `P(good report) ≈ P(answer in the N) [rises] × P(the model uses it) [falls]`; the left factor is a retrieval
measurement, the right one a generation measurement. **A metric that only moves one way cannot choose a middle.**

### What the frontier DID settle, for free

A good reranker shifts the curve LEFT (reranked N=3 0.882 vs vector N=3 0.765), a bad one RIGHT (`bge` needs N=30 to reach vector's N=15); vector alone is
flat from 15 on `requests` (15 → 50 buys 0.000). **N ∈ {20, 50} was "eliminated" — corrected later: recall is monotone, so 50 is unmeasured in the only
direction that could condemn it; generation chooses among {3, 5, 10, 15}.**

### The design this produced — TWO numbers, not one

The user's: `RERANK_TOP_N` (best N with a reranker) and `VECTOR_TOP_N` (best N on vector alone), because the two paths have different curves; at runtime a
reranker that answered sends `RERANK_TOP_N`, a skipped gate or failed chain sends `VECTOR_TOP_N`. `skip()` truncates to whatever `top_n` it is handed,
so the caller must pass the vector-path N on the degraded path.

### MEASUREMENT 3 — the gate, and the answer is "skip everything"

Sweeping `m = s₁ − s₂`: with `bge` the best `τ` was 0.000 (never rerank) on 3 of 4 runs (the two exceptions on the 17-query corpus were non-monotonic noise).
`SKIP_MARGIN` ships as `None` (OFF): a threshold is **calibrated, never chosen**, and the calibration said "this reranker should not run". Reranking does
worst exactly where the first stage was most confident.

### MEASUREMENT 4 — slice 5's fusion gain does not survive

requests/codestral: vector MRR 0.646, wRRF 0.662 (slice 5 reproduced), vector → rerank 0.476, wRRF → rerank 0.472: **the gain vanishes the moment a reranker
runs** (`r@10 +0.000`). Fusion and reranking cannot be decided separately.

### The finding that outlives the negative result: it is a ROUTING signal

By `asks` (requests, MRR vector → +rerank): constant 0.354 → **0.540**, error 0.600 → 0.613, api 0.456 → 0.289, behaviour 0.787 → 0.530, structure **0.926 → 0.392**.
BM25 won and collapsed on the same kinds (constant 0.423, structure 0.426): a reranker and a keyword ranker are both LOCAL relevance models, a whole-chunk
embedding answers "what is this chunk about?". *(OVERTURNED by slice 8: it was a fingerprint of `bge`, not a law. With flash-lite there is not one negative
category and `structure` went −0.534 → +0.201; the routing signal is DEAD.)*

### The bad result was PROBED, not accepted — 2026-09-11

"It doesn't make any sense that the Cloudflare model gets that ugly result" (the user): four checks, wiring survived all four — **no 512-token truncation**
(scores grow as a chunk's prefix grows), **`id` is the right index at scale** (an answer planted at positions 0, 37 and 49 ranked first every time),
**the response is not capped** (50 of 50 back), **there is exactly one Cloudflare reranker**. The failure has a shape: 23 queries worse, 13 better, 9 unchanged;
the five worst cases (place 1 → 36, 32, 18, 16, 15) were all queries the bi-encoder already had at place 1, the best gains only 3-5 places. **When the first
stage is already right at #1, reranking has zero upside and maximum downside.** Process note: the first diagnostic compared `(index, score)` tuples with a
set of ints and reported "max damage zero" against the aggregate; **two numbers from the same data disagreeing is a bug, not a subtlety.**

### Two confounds tested and eliminated

The chunk header is not the problem (with header MRR 0.476, without 0.469). The corpus ratio is a real limit: the top-50 window is **61% of the 82-chunk quora
corpus** and 15% of requests; at 1,000-10,000 chunks it would be 0.5-5%.

### Provider corrections, measured and then confirmed on Voyage's own dashboard

(1) **The Voyage rate limit was the BILLED tier's:** a card-free account gets **3 RPM and 10K TPM**, not "4M TPM / 2,000 RPM". (2) **The 200M free grant covers only
"Voyage series 3 models"**, so the `rerank-2.5-lite` chosen on 2026-08-11 was never covered; `rerank-3-lite` and `rerank-3` both answer; **the registry uses
`rerank-3-lite`**. Pacing does not rescue it (a call counts whole against the minute): 50 documents (~16,900 tokens) refused, 40 (~13,100) refused, **30 passed**
(~8,900). **Voyage cannot serve `SEARCH_LIMIT = 50` on a card-free account at all** (the Groq shape). A pre-flight token check was REFUSED (our `chars/3` estimator
straddles the boundary in both directions: *an estimate is not a budget*). **A provider's published rate limit is not your account's, and its free grant may not
cover the model you picked.**

### The slice 6 closing review — 2026-09-11

(1) **Nothing checked the translation between two number spaces that look identical:** `store.search()` returns `SearchHit.chunk_index`, an ID in the corpus;
`rerank()` returns POSITIONS into the list it was handed; neither package can check it (`rerank/` may not import `store/`).
`tests/integration/test_retrieval_to_rerank.py` runs chunk → store → search → rerank → back to real chunks with **ids starting at 100**. (2) **The four tiers that
lead chain 3 had no liveness check**; they now do, and assert `declined == 0`. Mistakes in my new tests: the fakes were bare functions (the protocol needs a `.rank`
method) and `Ranking` does not refuse an out-of-range position (it never learns how many were sent; the check lives in `HTTPReranker._validated`). **Loud is the
property worth pinning; "impossible" was wishful.**

### What slice 6 deliberately did NOT do

Nothing called `rerank` (slice 7 wired it); `ministral-3b-2512` was not built (an LLM-as-reranker needs a prompt, a parse and its own failures); the local ONNX
model was not installed (Cloudflare's 2,840 calls a day plus a per-pair cache gave the same repeatability); no `api/` test (`api/` did not import `rerank` yet).

### What slice 6 may NOT conclude, restated against its own results

`bge-reranker-base` hurts on 2 corpora × 2 embedders, **not** that reranking hurts; `rerank-3-lite` helps on one saturated corpus, **not** in general; the provider
matters more than the stage; the gain and loss are question-type shaped (later overturned); fusion's gain does not survive `bge`, **not** that fusion is dead;
Voyage cannot serve a 50-document window free; `RERANK_TOP_N` cannot be set from `recall@N` (monotone).

### The r@1 / MRR question is SETTLED

`0.645` was the **MRR** mislabelled as `recall@1`. True `r@1`: quora/codestral 0.412, quora/google 0.529, requests/codestral 0.533, requests/google 0.533: the top slot
is wrong **half the time**, a bigger gap than the file claimed.

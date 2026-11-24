# Step 1, slice 8: the measurements

[Docs home](../README.md)

## SLICE 8 — MEASURED 2026-09-16. STEP 1 IS COMPLETE

*The full run is in `docs/slice8/RESULTS.md` and the findings with their
evidence in `docs/slice8/FINDINGS.md` - both TRACKED, because they are
analysis rather than model output. The raw run files are in
`artifacts/slice8/runs/`, which is git-ignored like the rest of `artifacts/`. New instruments: `warm_embeddings.py`,
`load_corpus.py`, `bench_index.py`, `validate_fixture.py`,
`score_report_tier.py`, plus `geo` added to `score_hybrid.py`.*

**Exit `80.240.20.89`, AS20473 The Constant Company (Vultr, Frankfurt) — a
FOURTH ISP, and a datacenter one. Google answered 200.** The probe decided
it; the ISP name would have predicted nothing.

### 0. A THIRD FIXTURE, and it is what made the run worth doing

`data/samples/golang_geo/queries.json` — `golang/geo` at `b200a11`,
computational geometry on the sphere. **729 chunks, 45 queries, 9 per
category, categories INTERLEAVED so any prefix is a stratified sample** (the
`requests` fixture's first ten queries are all `constant`, which is how the
2026-09-11 Voyage run became a category study by accident).

| | quora | requests | **geo** |
|---|---|---|---|
| language | Python | Python | **Go** |
| domain | ML | HTTP client | **spherical geometry** |
| splitter | AST | AST | **`split_recursive`, first ever measured** |
| chunks · mean | 82 · 217 tok | 335 · 244 tok | **729 · 474 tok** |
| 50-doc window | 61% of corpus | 15% | **7%** |
| vector `r@50` | 1.000 | 0.978 | **0.867 — NOT saturated** |

Two by-products: the generic splitter packs Go chunks **94% larger** than the
Python AST splitter, and their headers carry **no function label** at all.
Both change which tiers can accept them.

**All four recorded 2026-09-07 runs reproduce to three decimals**, so nothing
below rests on a drifted instrument.

### 1. THE EMBEDDER — codestral stays, and NOT because it wins on recall

| embedder | quora | requests | **geo** | mean r@50 |
|---|---|---|---|---|
| **codestral-embed** | 0.608 | 0.646 | **0.526** | 0.948 |
| gemini-embedding-001 | 0.674 | **0.650** | 0.493 | 0.956 |
| embed-v4.0 | **0.710** | 0.627 | 0.458 | **0.963** |
| gemini-embedding-2 | 0.702 | 0.559 | **0.341** | 0.919 |
| mistral-embed | 0.461 | 0.474 | 0.380 | 0.926 |

**No model wins everywhere and the averages are within 0.013.** Recall does
not decide this — **a capability gate does**:

> **GOOGLE COUNTS ONE TEXT AS ONE REQUEST. It can embed 1,000 CHUNKS a day
> per model per key, not 96,000.** Proven twice: `729 + 335 = 1064` texts hit
> `limit: 1000`; and three 40-text calls in six seconds hit `limit: 100`.
> Three HTTP calls cannot exceed 100 — 120 texts can.

LabPilot targets 1,000-10,000 chunks per artifact. **Google can embed a
notebook and cannot embed a repository** — ten days for a 10k-chunk repo.

**`gemini-embedding-2` is now scored and does not justify its rank.** It was
placed above 001 on Google's own MTEB numbers, the only entry in `MIGRATION`
ranked on somebody else's benchmark. On geo it is **the worst of five**
(0.341, below `mistral-embed`) with `r@50` 0.756. Strong on the saturated
Python corpus, collapses on Go.

**BGE is dropped.** Its real tokenizer ratio is **1.12-1.45x** our estimate,
not the 2.36x recorded — that figure compared BGE to *codestral*, a different
denominator. **91% of geo chunks** exceed its 512-token limit.

**Cohere's trial tier is 100,000 tokens/minute**, recorded nowhere; the
registry's 640,000 was a burst that never met a limit, so the estimator is
6.4x optimistic for it.

### 2. FUSION — SLICE 5 IS OVERTURNED, and the reason is measurable

Slice 5: *"NOT ONE fusion setting improved recall@50 on any run."* True — and
a statement about **two saturated Python corpora** where `r@50` was already
0.978-1.000. Nothing was available to win.

On geo, with real headroom:

```
vector alone        r@10 0.689   r@50 0.867
score a=0.85        r@10 0.756   r@50 0.933   +0.067
wRRF k=30 w=0.3     r@10 0.756   r@50 0.933   +0.067
```

**Every one of the 30+ wRRF settings in the sweep improved `r@50`.** Not one
was negative, and it reproduces on a second embedder.

**DECISION: the keyword channel is switched ON for large corpora.** It has
been built and callerless since slice 5; it now has a caller. The gain is one
corpus and it costs nothing on the saturated ones.

### 3. RERANKING SHIPS, and slice 6's negative result was about ONE MODEL

| corpus | reranker | MRR | headroom captured |
|---|---|---|---|
| **geo** | `gemini-3.5-flash-lite` | 0.526 -> **0.759** | **+75%** |
| **geo** | `rerank-v4.0-fast` | 0.526 -> 0.632 | +100% of r@10 |
| **geo** | `bge-reranker-base` | 0.526 -> **0.347** | **-50%** |
| **requests** | `gemini-3.5-flash-lite` | 0.646 -> **0.791** | +50% |

`r@50` unchanged on every run — the sanity check passed every time.

**THE CATEGORY SPLIT DOES NOT REPRODUCE.** Slice 6 measured `bge` at -0.534
on `structure` and built a **routing signal** on it. With flash-lite, per
category on geo / requests: error **+0.400 / +0.300**, constant +0.231 /
+0.153, api +0.172 / +0.216, behaviour +0.161 / +0.141, structure **+0.201 /
+0.000**. **Not one negative cell.**

> The split was a fingerprint of `bge-reranker-base`, not a law about
> reranking. Routing by question type may still be right; **this is not
> evidence for it, and the old evidence describes a model we should delete.**

**`bge-reranker-base` is DELETED, not reordered** — worse than not reranking
on three corpora, two languages, three domains, which is exactly the
condition `rerank/registry.py` set for removing it.

**The gate stays off.** Third corpus, same answer: the best `tau` skips 2 of
45 and is within noise of always-rerank. `SKIP_MARGIN = None` confirmed.

### 4. THE WINDOW TURNS OVER BETWEEN 50 AND 100

| window | r@1 | r@10 | MRR |
|---|---|---|---|
| 10 | 0.622 | 0.689 | 0.640 |
| 20 | 0.689 | 0.756 | 0.726 |
| 30 | 0.667 | 0.778 | 0.719 |
| **50** | **0.711** | 0.822 | **0.759** |
| 100 | 0.511 | **0.911** | 0.686 |

**The two metrics disagree above 50.** More candidates means more chances to
surface the answer *somewhere in the ten* and more chances to put something
else first. **`SEARCH_LIMIT = 50` is the default** because it wins MRR and
`r@1`; 100 wins only if generation cares about "is it in the ten" more than
about ordering, and that is a generation measurement nobody has made.

**This also settles section 14.3 for the per-tier window.** A global cut to
25 would have cost `r@10` 0.822 -> 0.756, and the tier it protected cannot
serve this corpus at any width.

### 5. TWO RERANK TIERS CANNOT SERVE A REAL CORPUS, and chunk size is why

```
gemma-4-26b-a4b-it   16,000 input tok/min   50 geo docs ~27,344  REFUSED locally
same, at window 30                          ~16,376              STILL refused
Voyage, card-free    10,000 TPM, whole call ~23,700              refused by provider
```

Gemma is third-best on quora and **cannot rerank a Go repository**; even at a
width it accepts, its per-minute input budget makes 45 queries ~34 minutes.

> **A tier's usable window is a property of the CORPUS, not only the
> provider.** The same tier serves 50 Python chunks and refuses 30 Go ones.

### 6. EXACT SEARCH STANDS — measured on the real instance

| artifact | rows | client ms | **server ms** |
|---|---|---|---|
| requests | 335 | 356 | **2.86** |
| geo | 729 | 340 | **6.07** |
| labpilot | 1,387 | 358 | **11.33** |

Linear at 8.2-8.5 microseconds per row, so 10,000 chunks extrapolates to
**~82 ms**. And the first thing the numbers say is that **the database is not
the cost**:

```
exact search, 1,387 rows       11 ms
one round trip to Supabase    350 ms      30x larger
one report                 52,700 ms   4,600x larger
```

With a partial HNSW index per artifact: **below ~1,000 rows Postgres refuses
the index and sorts instead**. At 1,387 it uses it — **9.3x faster, recall
0.960** — and at `ef_search = 100` it **stops using it again**, because a
wider search costs more than sorting 1,387 rows. So "raise ef_search to
recover recall" and "use the index at all" are in TENSION at this size.

**DECISION: exact ships, and the question is CLOSED rather than deferred.**
The only condition 2026-09-05 allowed — time on real artifacts — is measured
and does not overturn it. Revisit at ~20,000 chunks in one artifact.

### 7. TWO PRODUCTION DEFECTS, both found by measurement — BOTH FIXED since (2026-09-27)

**`MAX_BATCH_SIZE = 96` is a Mistral constant wearing a global name.** 96 geo
texts = 44,554 tokens -> **429**; 40 texts = 18,072 -> **200 immediately
after**, so the call was refused for its own size. The halving fallback
matches the word `token` and Google's 429 never says it, so `embed_batches`
**raises instead of halving**. Every Google entry in `MIGRATION` fails on its
first batch for any corpus averaging over ~312 tokens per chunk — which
includes this repository.

**`embedding_minutes()` counts HTTP calls where Google counts texts, and
models no daily REQUEST budget at all.** It reports 118 minutes for a
10,000-chunk Google ingest; the truth is ten days.

### 8. JOB 9 — the report keeps the strong chain

The lean `REPORT`, stuffed, on `gemini-3.5-flash-lite`: **STOP, 16.4s, 12 of
12 citations resolved**, and **~8 of 19 findings** against the baseline's 13,
with **2 of the 5 that carry the story** against 4. It also **breaks the
comparability gate** — §6 correctly says the two F1 numbers are not
comparable and §9 compares them anyway, the exact failure recorded on
2026-08-14.

Section 11.9's challenge was well argued and **does not survive for the
report**. It stands for the other nine calls in a report, which is where
routing already sends cheap tiers.

### WHAT SLICE 8 DID NOT SETTLE

- **Merged vs per-side reranking** — not measured. Per-side stays the
  default on the structural-coverage argument, not on evidence.
- **`VECTOR_TOP_N` / `RERANK_TOP_N`** — the WINDOW is measured; how many
  chunks to SEND is a generation property and still unmeasured.
- **`gemini-3.1-flash-lite` on geo** — died on repeated `UNAVAILABLE`.
- **`rerank-3` (non-lite)** — still never scored anywhere.
- **Voyage on geo** — 3 RPM is ~56 minutes for 45 queries, and it cannot take
  the window regardless.
- **Above 1,387 rows** in the index benchmark; 10,000 is an extrapolation.
- **A fourth language.** Three corpora beats two and is still three.


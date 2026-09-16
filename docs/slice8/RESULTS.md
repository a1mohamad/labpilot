# SLICE 8 — the measurement, and the decisions it settles

Run 2026-09-16. Exit `80.240.20.89`, **AS20473 The Constant Company** (Vultr,
Frankfurt) — a fourth ISP for this project and a datacenter one; Google
answered **200**, so the probe decided it and the ISP name did not.

Every number below is reproducible from the repository: `score_hybrid.py`,
`score_rerank.py`, `bench_index.py`, `warm_embeddings.py`, `load_corpus.py`,
`validate_fixture.py`, and the three fixtures. Raw output is in
`artifacts/slice8/runs/`. Findings with their evidence are in
`artifacts/slice8/FINDINGS.md`.

---

## 0. What made this run different: a third fixture

Both older corpora are **Python**, and one of them is saturated. So every
retrieval number this project had recorded described one language, and slice
5's headline rested on two corpora where the metric had no room left to move.

**`data/samples/golang_geo/queries.json`** — `golang/geo` at `b200a11`,
computational geometry on the sphere.

| | quora | requests | **geo** |
|---|---|---|---|
| language | Python | Python | **Go** |
| domain | machine learning | HTTP client | **spherical geometry** |
| splitter | Python AST | Python AST | **`split_recursive`, first time measured** |
| chunks | 82 | 335 | **729** |
| mean chunk | 217 tok | 244 tok | **474 tok** |
| 50-doc window as % of corpus | 61% | 15% | **7%** |
| vector `r@50` | 1.000 | 0.978 | **0.867 — not saturated** |
| queries | 17 | 45 | **45, 9 per category** |
| any prefix is stratified? | no | **no** | **yes** |

Validated by `scripts/validate_fixture.py`: every query resolves to 1–2 target
chunks, none is too broad, and **none leaks the identifier it searches for**.

Two by-products worth keeping. The generic splitter packs Go chunks **94%
larger** than the Python AST splitter, and its headers carry **no function
label** — only file and lines. Both change what downstream tiers can accept
(see §5).

**The instrument was proved first.** All four recorded 2026-09-07 runs
reproduce to three decimals (quora/codestral MRR 0.608, requests 0.646, wRRF
0.662). Nothing below rests on a scorer that had drifted.

---

## 1. Embedder — codestral stays primary, and NOT because it wins on recall

Vector search alone, five models × three corpora:

| embedder | quora | requests | **geo** | mean MRR | **mean r@50** |
|---|---|---|---|---|---|
| **codestral-embed** | 0.608 | 0.646 | **0.526** | 0.593 | 0.948 |
| gemini-embedding-001 | 0.674 | **0.650** | 0.493 | **0.606** | 0.956 |
| embed-v4.0 (Cohere) | **0.710** | 0.627 | 0.458 | 0.598 | **0.963** |
| gemini-embedding-2 | 0.702 | 0.559 | **0.341** | 0.534 | 0.919 |
| mistral-embed | 0.461 | 0.474 | 0.380 | 0.438 | 0.926 |

*(MRR per corpus; `r@50` averaged because that is the number that matters once
a reranker runs — slice 6 measured that reranked scores barely move with the
embedder, so its only remaining job is getting the answer into the window.)*

**No model wins everywhere.** Cohere takes quora, Google takes requests by
0.004 over codestral, codestral takes geo. Averaged they are within 0.013 of
each other — well inside what 45 queries can resolve.

So recall does not decide this. **A capability gate does**, and it is F4:

> **Google counts one TEXT as one request, so it can embed 1,000 CHUNKS a day
> per model per key — not 96,000.** Proven twice: `729 + 335 = 1064` texts hit
> `limit: 1000`, and three 40-text calls in six seconds hit `limit: 100`.
> Three HTTP calls cannot exceed 100; 120 texts can.

LabPilot targets **1,000–10,000 chunks per artifact**. Google tops out at
1,000 chunks a day. It can embed a notebook and cannot embed a repository —
ten days for a 10k-chunk repo, and switching model mid-corpus is a re-embed,
not a continuation.

Cohere is gated too, less hard: **100,000 tokens/minute on the trial tier**
(F3, recorded nowhere before — the registry's 640,000 was a burst that never
met a limit), plus 1,000 calls a month shared with rerank.

**DECISION — `MIGRATION` order changes on capability, not on score:**

```
codestral-embed          measured 550k tok/min, no daily cap   PRIMARY
mistral-embed            same platform, 510k tok/min           same-platform backup
embed-v4.0 (Cohere)      100k TPM, 1,000 calls/MONTH           small artifacts only
gemini-embedding-2       1,000 CHUNKS/day                      small artifacts only
gemini-embedding-001     1,000 CHUNKS/day                      small artifacts only
@cf/baai/bge-base        91% of geo chunks exceed its 512      DROP from the walk
```

**`gemini-embedding-2` is measured and does NOT justify its rank.** It sits
above 001 in the registry on **Google's own MTEB numbers** — the only entry in
`MIGRATION` ranked on somebody else's benchmark. Ours disagrees in the place
that matters most:

```
quora     0.702  second best      <- Python, saturated
requests  0.559  fourth
geo       0.341  WORST OF FIVE, below mistral-embed, and r@50 only 0.756
```

It is strong on the Python corpus that cannot discriminate and **collapses on
Go**. Its MTEB lead did not survive contact with a second language.

**BGE is out.** F2: its real tokenizer ratio is **1.12–1.45×** our estimate,
not the 2.36× recorded (that figure compared BGE to *codestral*, a different
denominator). The conclusion survives and worsens — **91% of geo chunks**
exceed its 512-token limit and would be silently truncated.

---

## 2. Fusion — slice 5 is OVERTURNED, and the reason is measurable

Slice 5 concluded: *"NOT ONE fusion setting improved recall@50 on any run."*
That was true, and it was a statement about **two saturated Python corpora**
where `r@50` was already 0.978–1.000. There was nothing to win.

On geo, vector alone reaches only **`r@50` 0.867** — the first fixture where
the window genuinely loses answers. With room to move:

| geo / codestral | r@10 | **r@50** | MRR |
|---|---|---|---|
| vector alone | 0.689 | 0.867 | 0.526 |
| `wRRF k=30 w=0.3` | 0.756 | **0.933 (+0.067)** | 0.536 |
| `score a=0.85` | 0.756 | **0.933 (+0.067)** | 0.522 |
| `wRRF k=10 w=0.3` | 0.733 | 0.889 (+0.022) | **0.538** |

**Every one of the 30+ wRRF settings in the sweep improved `r@50`.** Not one
was negative. It reproduces on a second embedder (google-001: `score a=0.85`
also +0.067, ADAPTIVE +0.044).

**DECISION: the keyword channel is switched ON for large corpora.** It is
already built and already off-by-default (slice 5 shipped `store/keyword.py`
and `retrieval/fusion.py` with no caller). What changes is that it now has
one.

**The honest limit:** the gain is +0.067 `r@50` on **one** corpus, and it
vanishes on the saturated ones — where it also costs nothing. And §3 shows
reranking captures 75–100% of the remaining headroom anyway, so fusion's
value is in *raising the ceiling the reranker works under*, not in ordering.

---

## 3. Reranking — it SHIPS, and slice 6's negative result was about one model

Slice 6 measured `bge-reranker-base` making retrieval worse and could not
conclude whether reranking helps. It now can.

| corpus | reranker | MRR before → after | headroom captured |
|---|---|---|---|
| **geo** | `gemini-3.5-flash-lite` | 0.526 → **0.759** | **+75%** |
| **geo** | `rerank-v4.0-fast` (Cohere) | 0.526 → 0.632 | **+100% of r@10** |
| **geo** | `bge-reranker-base` | 0.526 → **0.347** | **−50%** |
| **requests** | `gemini-3.5-flash-lite` | 0.646 → **0.791** | +50% |
| quora (slice 6) | `gemini-3.5-flash-lite` | 0.608 → 0.799 | — |

`r@50` is unchanged on every run — the sanity check that says a reranker only
reorders. It passed every time.

### The category split does not reproduce

Slice 6 measured `bge` at **−0.534 on `structure`** and +0.186 on `constant`,
and this project built a **routing signal** on that. With flash-lite:

| asks | geo | requests |
|---|---|---|
| error | **+0.400** | **+0.300** |
| constant | +0.231 | +0.153 |
| api | +0.172 | +0.216 |
| behaviour | +0.161 | +0.141 |
| structure | **+0.201** | +0.000 |

**Not one negative cell, on either corpus.** `structure` was the worst
category and is now among the best. Cohere on geo *is* mixed (`behaviour`
−0.015, `constant` −0.044), which is what a real per-model difference looks
like.

> The split was a fingerprint of `bge-reranker-base`, not a law about
> reranking. Routing by question type may still be a good idea; **this is not
> evidence for it, and the old evidence describes a model we should delete.**

### The gate stays off

```
tau 0.000 (never rerank)   MRR 0.525
tau 0.050 (skip 2 of 45)   MRR 0.752   <- best, and 2 queries from "always"
always rerank              MRR 0.746
```

Third corpus, same answer. **`SKIP_MARGIN = None` confirmed.**

**DECISION: reranking ships, led by `gemini-3.5-flash-lite`.**
**`bge-reranker-base` is DELETED, not reordered** — it is worse than not
reranking on three corpora, two languages, three domains (F6), which is the
exact condition the registry itself set for removing it.

---

## 4. The window — WIDER, not narrower

Slice 6 could not answer this: `recall@N` is monotone, so retrieval can find
where *more* stops helping and never where *fewer* starts. Reranked quality
**can** have an optimum, and it was measured:

| window | reranked r@1 | reranked r@10 | MRR | ceiling in window |
|---|---|---|---|---|
| 10 | 0.622 | 0.689 | 0.640 | 0.689 |
| 20 | 0.689 | 0.756 | 0.726 | 0.800 |
| 30 | 0.667 | 0.778 | 0.719 | 0.822 |
| **50** | **0.711** | 0.822 | **0.759** | 0.867 |
| 100 | 0.511 | **0.911** | 0.686 | 0.933 |

**The curve TURNS OVER between 50 and 100, and the two metrics disagree.**
Widening to 100 gives the reranker more to find — `r@10` rises to 0.911, the
best measured — while `r@1` falls from 0.711 to 0.511 and MRR from 0.759 to
0.686. More candidates means more chances to surface the answer *somewhere in
the ten*, and more chances to put something else first.

**`SEARCH_LIMIT = 50` is therefore the default**: it maximises MRR and `r@1`,
and `r@10` at 0.822 is already well above vector alone's 0.689. **100 becomes
the right answer only if generation turns out to care about "is it in the
ten" more than about ordering** — and that is a generation measurement this
run did not make. Cohere would bill 100 documents the same as 50, so nothing
but quality decides it.

**This also settles section 14.3 in favour of the per-tier window.** A global
pre-rerank cut to 25 would have cost `r@10` 0.822 → 0.756 on geo — and the
tier that cut was protecting (Voyage) cannot serve this corpus at any window.

---

## 5. Two rerank tiers cannot serve a real corpus, and chunk size is why

| tier | limit | 50 geo documents | outcome |
|---|---|---|---|
| `gemma-4-26b-a4b-it` | 16,000 input tok/min | ~27,344 | refused locally, no request spent |
| same, at window 30 | 16,000 | ~16,376 | **still refused, by 376 tokens** |
| Voyage, card-free | 10,000 TPM, call counted whole | ~23,700 | refused by the provider |

Gemma is third-best on quora and **cannot rerank a Go repository**. The cause
is the corpus, not the provider: geo's generic-splitter chunks are 474 tokens
where Python's are 230.

> **A tier's usable window is a property of the CORPUS as well as the
> provider.** The same tier serves 50 Python chunks and refuses 30 Go ones.

---

## 6. Exact vs HNSW — exact stands, measured on the real instance

| artifact | rows | client ms | **server ms** | plan |
|---|---|---|---|---|
| requests | 335 | 356 | **2.86** | Sort |
| geo | 729 | 340 | **6.07** | Sort |
| labpilot | 1,387 | 358 | **11.33** | Sort |

Linear at 8.2–8.5 µs/row, so 10,000 chunks extrapolates to **~82 ms**.

**The first thing the numbers say is that the database is not the cost:**

```
exact search, 1,387 rows       11 ms
one round trip to Supabase    350 ms     30x larger
one report                 52,700 ms     4,600x larger
```

With a partial HNSW index per artifact:

| rows | ef | server ms | vs exact | recall@10 | plan |
|---|---|---|---|---|---|
| 335 / 729 | 40, 100 | 2.9–7.2 | 1.0x | 1.000 | **index NOT USED** |
| **1,387** | **40** | **1.22** | **9.3x** | **0.960** | **INDEX** |
| 1,387 | 100 | 11.61 | 1.0x | 1.000 | **index NOT USED** |

Below ~1,000 rows Postgres refuses the index. At 1,387 it uses it and is 9.3×
faster — costing **4% of recall**. And raising `ef_search` to recover that
recall makes the planner **stop using the index again**, which no earlier
measurement showed.

**DECISION: exact search ships. The question is closed, not deferred.** HNSW
would save ~10 ms of a ~50,000 ms answer and cost 4% of recall at the only
setting the planner will choose. Indexes are already 22 MB of a 44 MB total
for 2,451 rows.

**Revisit at ~20,000 chunks in one artifact.** Nothing below that moves it.

---

## 7. Two production defects this run found

**F1 — `MAX_BATCH_SIZE = 96` is a Mistral constant with a global name.**
96 texts of geo = 44,554 tokens → **429**; 40 texts = 18,072 → **200
immediately after**, so the call was refused for its own size. The halving
fallback matches the word `token`, and Google's 429 never says it, so
`embed_batches` raises instead of halving. **Every Google entry in
`MIGRATION` fails on its first batch** for any corpus averaging over ~312
tokens per chunk — which includes this repository.

**F4 — the estimator has no daily request budget**, and counts HTTP calls
where Google counts texts. `embedding_minutes()` reports 118 minutes for a
10,000-chunk Google ingest; the truth is ten days.

Both are unfixed and both are one-line-ish. They are written up with their
evidence in `FINDINGS.md`.

---

## 7b. Job 9 — the report stays on the strong chain

The lean `REPORT`, stuffed, on `gemini-3.5-flash-lite` (500/day):
**STOP, 16.4s, 12 of 12 citations resolved** — and **~8 of 19 findings**
against the recorded baseline's 13, with **2 of the 5 that carry the story**
against 4. It also **breaks the §6 comparability gate**: §6 correctly says
the two F1 numbers are not comparable, and §9 compares them anyway.

**DECISION: reports keep the strong chain.** Section 11.9's challenge was
well-argued and does not survive the measurement — for the report. It stands
for the other nine calls, which is where routing already sends cheap tiers.

---

## 8. What this run did NOT settle

- **Merged vs per-side reranking** — not measured. Per-side remains the
  default, on the structural-coverage argument, not on evidence.
- **`VECTOR_TOP_N` and `RERANK_TOP_N`** — the *window* is measured; how many
  chunks to *send* is a generation property and still unmeasured.
- **`gemini-3.1-flash-lite` on geo** — the run died on repeated `UNAVAILABLE`.
- **`rerank-3` (non-lite)** — still never scored anywhere.
- **Voyage on geo** — 3 RPM makes a 45-query run ~56 minutes, and it cannot
  take the window anyway.
- **Anything above 1,387 rows** in the index benchmark; 10,000 is an
  extrapolation and is labelled as one.
- **A fourth language.** Three corpora is better than two and is still three.

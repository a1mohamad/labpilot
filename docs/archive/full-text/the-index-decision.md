# Full text: THE INDEX DECISION — settled 2026-09-05 on five real repositories

[Docs home](../../README.md)

## THE INDEX DECISION — settled 2026-09-05 on five real repositories

*The user refused a synthetic answer and asked for five real repositories
between 10k and 25k chunks. **81,493 chunks were really embedded** with
`mistral-embed` (1024-dim, 22.7M tokens, ~45 minutes) and loaded into a local
`pgvector:pg17` container. Not the real project — see
[the outage](../../step1/vector-store.md#the-index-question-remeasured--2026-09-05-hnsw-wins-at-real-repo-size).*


### Speed and recall: HNSW wins, and it is not close

| repo | chunks | exact | HNSW | speedup | recall@10 |
|---|---|---|---|---|---|
| pytest | 9,929 | 33.7 ms | 0.53 ms | 64x | 1.00 |
| dask | 11,527 | 33.7 ms | 0.44 ms | 76x | 1.00 |
| pydantic | 13,153 | 34.2 ms | 0.40 ms | 86x | 1.00 |
| scikit-learn | 22,520 | 55.6 ms | 1.86 ms | 30x | 1.00 |
| **FastAPI** | **24,364** | **107.9 ms** | **0.98 ms** | **110x** | **1.00** |


### The query shape decides recall, and the default `ef_search` is too low

Those 1.00s used queries that were **copies of stored rows** — the easiest case,
because the query is already a node in the graph. Re-run with queries that are
NOT in the corpus:

| query | pydantic | scikit-learn | FastAPI |
|---|---|---|---|
| a stored chunk | 1.00 | 1.00 | 1.00 |
| **blend of two chunks** (realistic) | 0.94 | 0.98 | **0.86** |
| chunk + random noise (unrealistic) | 0.58 | 0.40 | 0.50 |

The noise row is not a fair test — random noise pushes a vector off the
embedding manifold, which an embedded question never does. **The blend is the
fair proxy**, and 0.86 on FastAPI is a real loss.

**`hnsw.ef_search` recovers it completely.** On FastAPI, the worst case:

```
ef_search =  40 (default)   1.37 ms   recall 0.86    59x
ef_search = 100             1.93 ms   recall 1.00    42x   <- ship this
ef_search = 200             3.61 ms   recall 1.00    22x
```

> **A default is not a measurement.** pgvector ships `ef_search = 40`, and at
> our size that quietly costs 14% of recall. Half a millisecond buys it back.


### The cost nobody had priced: the index is bigger than the table

| repo | chunks | table | HNSW index | total | x1.5 at 1536-dim |
|---|---|---|---|---|---|
| pytest | 9,929 | 56 MB | 81 MB | 137 MB | 205 MB |
| pydantic | 13,153 | 74 MB | 108 MB | 181 MB | 272 MB |
| scikit-learn | 22,520 | 126 MB | 184 MB | 310 MB | 465 MB |
| **FastAPI** | **24,364** | **136 MB** | **200 MB** | **336 MB** | **504 MB** |

**The index is ~1.5x the table.** At codestral's 1536 dimensions, ONE FastAPI-
sized repo plus its index is **504 MB — the entire Supabase free tier**, and
LabPilot compares **two** artifacts.

```
two 24k-chunk repos, 1536-dim, exact   ~408 MB   fits
two 24k-chunk repos, 1536-dim, HNSW   ~1008 MB   DOES NOT FIT
```


### The decision

**HNSW, with `ef_search = 100` — and storage must be solved first.**

The speed/recall case is settled: 30-110x faster at recall 1.00 on five real
corpora. Nothing about that is marginal. But it is **not free**, and on the free
tier storage binds before latency does — 108 ms of retrieval is nothing against
a report that takes ~50 seconds.

**The lever is `halfvec`**, already measured on 2026-08-28 as costing **0 of 10**
in ranking overlap. Half precision halves both table and index, which brings two
24k repos with indexes to ~500 MB. That is the shape to build at slice 8, where
the embedder and its dimension are chosen together.

> **The right question was never "is HNSW faster". It is "what runs out
> first".** Here it is disk, not milliseconds.


### A real bug this found in our own embedder

Three of the five repos **failed to embed**:

```
HTTP 400 code 3210  "Too many tokens overall, split into more batches"  (dask, fastapi)
HTTP 429            backend_out_of_capacity                             (scikit-learn)
```

`MAX_BATCH_SIZE = 96` is derived as `floor(50,000 / 510)` from the **per-minute**
token limit. Mistral also enforces a **per-request** limit, and our `chars / 3`
estimate under-counts real tokens badly enough to cross it: the batch that was
refused estimated **46,162** tokens, while a batch Mistral had already **accepted**
measured **59,466** real tokens.

> **An estimate is not a budget.** Batching on an estimate that can be wrong in
> the dangerous direction needs a retry that halves and re-sends, not a bigger
> constant.

**FIXED the same day: `embed/batching.py`.** `embed_batches()` sends one request
per yielded batch, halves on a refusal that names tokens, and **remembers the
smaller size** — going back to the full size would earn the same refusal again,
and every refusal costs a request. Any other failure is raised at once, because
retrying a bad key smaller only wastes requests.

It is matched on the word *token* rather than Mistral's code 3210, so it stays
true for the other four providers. Proven on the exact batch that failed:
`embed()` alone is refused; `embed_batches()` returns all 96 vectors in two
requests of 48. Four mutations were verified, and the test that found the
remembering bug was written before the code did it.

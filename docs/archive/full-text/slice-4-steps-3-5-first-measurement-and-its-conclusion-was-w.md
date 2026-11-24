# Full text: Slice 4, steps 3-5 — first measurement, and its conclusion was WRONG

[Docs home](../../README.md)

## Slice 4, steps 3-5 — first measurement, and its conclusion was WRONG

> **OVERTURNED the same day. Read
> [the corrected measurement](../../step1/vector-store.md#the-index-question-remeasured--2026-09-05-hnsw-wins-at-real-repo-size)
> first.** The numbers below are real; the *inputs* were not. Both the
> corpus size (1,000 rows) and the vectors (uniform random) were
> unrepresentative, and each one alone was enough to invert the answer.

*Step 3 was written as "partition per artifact + HNSW". It was built and
measured on a throwaway schema, **not** put in `schema.sql` — an index needs a
fixed width, and choosing one would have chosen the embedder that slice 8 owns.
The schema stays Shape A.*


### The numbers, on 10,000 rows across 10 artifacts, `vector(1536)`

| approach | latency | recall@10 | did the planner USE it? |
|---|---|---|---|
| **exact — B-tree on `artifact_id`, then sort** | **8.0 ms** | **1.00** by definition | — |
| shared HNSW over every artifact | 8.0 ms | 1.00 | **no — ignored, 76s to build, 57MB** |
| partial HNSW, one index per artifact | 8.0 ms | 1.00 | **no — ignored** |
| the same, forced with `enable_sort = off` | 1.2 ms | **0.82** | yes |
| **partitioned + HNSW per partition** | **1.4 ms** | **0.82** | **yes** |

**The decision (step 5): ship exact search. Build no index.**


### Why, in the order the reasons actually weigh

1. **8 ms is already fast, and it is exact.** The plan's own arithmetic guessed
   ~160 ms. Measured, it is **18x cheaper than estimated**.
2. **Cost follows rows PER ARTIFACT, not corpus size.** Measured: 1,000 chunks
   8.0 ms - 2,000 chunks 16.1 ms - 5,000 chunks 40.3 ms. A repository is ~1,000
   to 5,000 chunks and the filter is always `WHERE artifact_id = $1`, so adding
   artifacts costs nothing. **This is the whole reason the industry's
   filtered-search problem is not ours.**
3. **The only variant the planner will use costs 18% of recall.** End to end
   that is `0.941 x 0.82 = 0.77`, against 0.941 exact — a real loss for 6.6 ms.
4. **Postgres refuses the index on its own**, before and after `ANALYZE`. Both
   non-partitioned index shapes were built, sat there, and were never chosen:
   sorting 1,000 rows is genuinely cheaper than walking a graph and discarding
   90% of it. Partitioning is the only shape that gets used, because partition
   pruning removes the predicate and leaves a plain top-k inside one partition.
5. **Partitioning is not free**: **216 ms of DDL per ingest**, a lock, and
   partition lifecycle to maintain.

> **The index was never the question. "How many rows does one query actually
> touch?" was.** At ~1,000 it is not worth an approximation.

**Revisit when one artifact passes roughly 20,000 chunks** — exact would then
be ~160 ms and the trade changes. Nothing else moves the answer.


### Two measurement mistakes, both mine, both caught before they were believed

**1. Every row had the same vector.** The generator was

```sql
select ..., (select array_agg(random()) from generate_series(1,1536))
from generate_series(0, 9999) i
```

The inner subquery never references `i`, so Postgres evaluated it **once** and
gave all 10,000 rows an identical vector. It was caught by a sanity check that
should have been the first thing written: distances within one artifact came
back `min 0.000  avg 0.000  max 0.000`. The fix is a correlated `LATERAL`
(`generate_series(1, 1536 + 0*i)`).

**2. A recall of 1.00 that could not have been anything else.** The first
partial-index run computed its "truth" **after** creating the index, so it
compared the index against itself. Truth is now taken **before any vector index
exists**, and the same measurement then reported **0.82**.

> **A benchmark is code, and it fails the same way tests do.** Both mistakes
> produced confident, publishable-looking numbers. The generator bug also
> quietly voids the "10 of 10 overlap" claim from the 2026-08-28 gate, which
> used the same shape.

**And a fixture note worth keeping:** uniform `random()` puts every vector in
the positive orthant, where all pairs sit near 0.75 cosine and "nearest" is
noise. `random() - 0.5` spreads them over the sphere. Random vectors remain the
**hardest** case for HNSW, so 0.82 is a floor — real embeddings cluster and
would score better. The latency argument does not depend on that.


### What this does NOT decide

The embedder. `schema.sql` is untouched, `v` is still an undimensioned
`vector`, and slice 8 still chooses. If a 3072-dim model wins and an index is
ever wanted, the `(v::halfvec(3072))` expression index measured on 2026-08-28
is the route — but on today's numbers no index is wanted at all.

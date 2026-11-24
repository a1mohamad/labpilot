# Full text: The index question, remeasured — 2026-09-05: HNSW wins at real repo size

[Docs home](../../README.md)

## The index question, remeasured — 2026-09-05: HNSW wins at real repo size

*The first pass concluded "exact ships, no index". **That was wrong**, and it
was wrong for two independent reasons, both in the fixture rather than in the
database. Re-run on a local `pgvector/pgvector:pg17` container so a free-tier
instance was never the variable.*


### What a real artifact actually holds — measured on real repositories

| repository | chunks |
|---|---|
| **FastAPI** | **24,364** (14.7 MB of text) |
| Django | **REFUSED** — over our own 20 MB `MAX_TOTAL_BYTES` |
| requests | 924 |

**So 1,000 chunks is not the normal case, it is the small case.** The first
measurement sized every artifact at 1,000 rows and concluded from that.


### The corrected numbers, on CLUSTERED vectors, `vector(1536)`

| chunks in one artifact | exact | HNSW | speedup | recall@10 |
|---|---|---|---|---|
| 1,000 | 6.7 ms | *index not used* | 1x | 1.00 |
| 5,000 | 30.7 ms | **0.55 ms** | **56x** | **1.00** |
| 15,000 | 75.8 ms | **1.24 ms** | **61x** | **1.00** |
| 30,000 | 144.3 ms | **1.38 ms** | **104x** | **0.98** |

**At real repository size HNSW is 50-100x faster and costs nothing measurable
in recall.** Only at ~1,000 rows does the planner ignore it, and there exact is
already 6.7 ms, so nothing is lost either way.


### Why the first answer was wrong — the fixture, twice

**1. Uniform random vectors are DEGENERATE, not merely "hard".** In 1,536
dimensions independent uniform coordinates are nearly orthogonal and nearly
equidistant, so there is no neighbourhood structure for a graph to exploit and
the "true" top-10 is a set of near-ties. Same table size, same index, only the
data changed:

```
30,000 rows, uniform random   ->  recall@10 = 0.04
30,000 rows, clustered        ->  recall@10 = 0.98
```

**0.04 is not a measurement of HNSW. It is a measurement of noise.** The
earlier 0.82 figure came from the same family of fixture and must not be quoted
either.

**2. The corpus was sized at the small end.** Exact search does not degrade
gently: 6.7 ms at 1,000 rows, 144 ms at 30,000 locally — and **10,019 ms** at
30,000 on the Supabase free tier, where 184 MB of vectors stop fitting the
cache and every query goes to disk. The deployment target matters as much as
the algorithm.

> **A benchmark answers the question its fixture asks.** Ours asked "is an
> index worth it for a small artifact of meaningless vectors?" — and answered
> that correctly. It was not the question the project has.


### The operational lesson, learned the expensive way

Building the 30,000-row HNSW on the real Supabase project with
`maintenance_work_mem = 512MB` **took the instance down**, and it did not come
back on its own. The index itself built in 176 s; the connection died during
the `ANALYZE` after it.

> **Never size a benchmark to the machine you wish you had.** A free tier has
> the memory a free tier has, and a benchmark that kills the database is not a
> measurement, it is an outage. Run this class of work on a local container.


### What this changes, and what it does not

**Changed:** an index is now expected to be worth building. **Not changed:**
`schema.sql` is untouched and `v` is still an undimensioned `vector`, because
an index still needs a fixed width and that is still slice 8's choice. Nothing
is stored yet, so adding the index costs nothing when the embedder is settled.

**The decision therefore moves to slice 8**, taken together with the embedder,
and the shape to build is the one the planner will actually use — a partition
or a partial index per artifact, since a shared graph over every artifact is
skipped in favour of a B-tree.

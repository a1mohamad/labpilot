# Full text: THE FINAL DECISION — exact search ships, 2026-09-05

[Docs home](../../README.md)

## THE FINAL DECISION — exact search ships, 2026-09-05

*The user's call, after refusing three of my answers in a row and being right
every time. Recorded with the reasoning, the condition that would overturn it,
and the four things I had wrong.*

> **Exact search ships. HNSW is on the shelf with its numbers.**
> **Slice 8 re-measures both on real artifacts. TIME is the only thing that can
> overturn this — not recall, and not storage.**


### Why exact wins at OUR size

The target is **1,000 to 10,000 chunks per artifact**, not the 24k-30k stress
cases. At that size:

| | exact | HNSW |
|---|---|---|
| 1,000 chunks | **6.7 ms** | *the planner refuses the index* |
| 5,000 chunks | 30.7 ms | 0.55 ms |
| 9,929 chunks (pytest, real vectors) | **33.7 ms** | 0.53 ms |
| recall@10 | **1.00 by definition** | 1.00 only at `ef_search = 100` |
| storage per row, 1536-dim | **8 KB** | **20 KB** |

1. **34 ms against a ~50 second report is 0.07%.** We are not short of time.
2. **Recall 1.00 needs no tuning.** HNSW at pgvector's default `ef_search = 40`
   silently lost **14%** on FastAPI. Five embedders would mean five tunings,
   each needing its own re-measurement.
3. **Storage is 2.5x cheaper**, and storage is what runs out first.
4. **Below ~1,000 rows Postgres will not use the index anyway**, so much of the
   target range cannot benefit from it at all.

Published guidance agrees at this scale: under roughly 50k vectors the gap is
negligible, and the operational simplicity of no index tuning outweighs the
speedup.


### The ONE condition that reopens it

**Slice 8 measures exact vs HNSW on real artifacts, inside the full RAG system.**
If exact is genuinely too slow there, the answer changes to HNSW, or to a
platform with more RAM, or both.

**Time is the only admissible reason.** Recall cannot overturn it — exact is
1.00 by definition. Storage cannot overturn it — exact is the cheaper of the two.


### Four things I had WRONG, and the user corrected every one

**1. "The index changes speed, not correctness."** **False.** Index recall below
1.00 means different chunks reach the model, so the report can differ. That is
correctness, and it belongs to this slice — not to slices 5-8.

**2. "The index decision belongs to slice 8 with the embedder."** **False.**
Slice 8 ranks the embedders; it does not decide *whether* to use them. All five
models stay — one primary, four backups, permanently. So the index was **our
call today**, and deferring it was avoidance dressed as sequencing.

**3. "The index costs 1.5x."** **It costs 2.5x, and it never stops.** The 1.5x
was the index measured against the table alone. Per row at 1536-dim: vector
8 KB, graph +12 KB, **total 20 KB**. And it grows with **every row, forever** —
an index is never a one-time cost.

**4. Storage is per ROW, not per artifact.** A row *is* a chunk, so chunks
matter completely; how they are grouped does not:

```
2 artifacts x 10,000 chunks  =  20,000 rows
5 artifacts x  4,000 chunks  =  20,000 rows      <- identical storage
```

Measured: **~8.2 KB of index per row** whether it is one graph over everything
or one graph per artifact. Partitioning changes *where* the rows are cut, never
*how many* there are.

> **An index is a trade, never a saving.** Spend storage, buy time. If you are
> not short of time, you are paying for nothing. I recommended HNSW **before I
> had measured storage at all**, which is why the answer moved twice.


### And one constraint I mis-attributed

**Render's 512 MB is the API process's RAM. It is not the database.** The HNSW
graph would live in Postgres, so Render never constrained it. Two different
machines, two different budgets.

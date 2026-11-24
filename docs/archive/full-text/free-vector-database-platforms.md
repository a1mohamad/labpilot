# Full text: Free vector-database platforms — verified 2026-09-05

[Docs home](../../README.md)

## Free vector-database platforms — verified 2026-09-05

*Every row read from the provider's OWN pricing page. Blog and aggregator lists
were searched first and are **not** the source — this project has been burned by
them three times (Beam, Cerebrium, Saturn Cloud).*

| Platform | Free storage | RAM | Card? | Other limits |
|---|---|---|---|---|
| **Supabase** *(ours)* | 500 MB | **500 MB** | not stated | **paused after 1 week idle**, 2 projects |
| **Neon** | 0.5 GB/project | **up to 8 GB** | **no credit card, permanent, not a trial** | 100 projects, 100 CU-hours, sleeps after 5 min |
| **Qdrant Cloud** | **4 GB disk** | 1 GB | not stated | 0.5 vCPU, free forever |
| **Pinecone** | **2 GB** | — | not stated | 5 indexes, 2M writes/mo, 1M reads/mo |
| **Zilliz Cloud** | ~1M vectors @768-dim | — | not stated | 5 collections, 1 cluster per org |
| **Upstash Vector** | 1 GB | — | card on upgrade | **max 1,536 dim**, 10K queries/day |

### Three findings that outrank the storage numbers

**1. Supabase's binding limit is RAM, not disk — its own page says 500 MB.**
That is exactly why a 30k-row exact query took **10 seconds** there and 150 ms
on a local container. **Neon offers up to 8 GB at the same 0.5 GB storage**,
which is the single most useful fact in this table.

**2. Leaving Postgres means losing exact search.** Pinecone, Zilliz and Upstash
are **ANN-only** — brute force is not offered. Migrating there would *force* the
approximate search we just declined and hand back recall 1.00. Only Qdrant
exposes an exact flag.

**3. Upstash is disqualified outright** — max **1,536 dimensions**, and
`gemini-embedding-001` is **3072**. The embedder chain must keep all five
reachable.

### The migration target, if slice 8 ever calls for one

**Neon.** Postgres + pgvector, so `store/` works **unchanged** — a one-line
`DATABASE_URL` change, not a rewrite. No card, permanent, and 16x the RAM.

**Qdrant is the only one worth its 4 GB**, and it costs rewriting the whole
`store/` package plus a client dependency against Render's 512 MB.

> **What is NOT verified: the credit-card question for Qdrant, Pinecone and
> Zilliz.** Their pricing pages do not say. This project's second valid source
> is the **actual signup flow**, and it has not been run. Do not record any of
> them as no-card until it is.

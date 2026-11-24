# Full text: Slice 4 — the theory, recorded 2026-09-03

[Docs home](../../README.md)

## Slice 4 — the theory, recorded 2026-09-03

*Session 16 wrote no source on purpose. Lessons 1–3 of the vector-database gap
were delivered — what a vector index is, how HNSW walks a graph, and what one
row must hold. The lessons changed the schema twice and corrected two things
this file had already written down.*

**What slice 4 must prove:** ~2,000 chunks go into a database and come back out
unchanged, **and a query really uses the plan we intended.**


### The question slice 4 actually has to answer

Not *"how do we build an HNSW index?"*. It is:

> **Do we need an index at all?**

Because the numbers are small, and nobody had done the arithmetic:

```
rows per artifact          ~1,000   (a repo is 1,094 chunks, measured)
every query is filtered    WHERE artifact_id = $1
exact cost                 1,000 x 1,536 = ~1.5M ops  ~=  160 ms
```

**The 64.7 ms / 326.0 ms measurement of 2026-08-28 had NO filter on it.** It
compared an index scan against a full-table scan over 2,000 rows. The query we
will really write never touches 2,000 rows — it touches ~1,000, and Postgres
finds them with an ordinary B-tree on `artifact_id`.

> **A benchmark without your `WHERE` clause is a benchmark of a different
> query.** The pgvector gate proved the index *can be built*. It never proved
> the index is *needed*.


### Filtered vector search — the thing that makes an index awkward

HNSW builds **one graph over every row**, across all artifacts. The links were
created at insert time and they cross artifacts, so there is no sub-graph of
artifact 7 to enter. The greedy walk visits other artifacts' chunks and throws
them away:

```
iterative_scan off       visits ~200 of 10,000   ->  ~20 usable rows. TOO FEW
iterative_scan relaxed   visits ~2,000           ->  50 rows, ~10x slower
exact                    visits 10,000           ->  always correct
```

The name for this is **filtered vector search**. pgvector 0.8.0 added
`hnsw.iterative_scan` for it, and **we have 0.8.2**, so the setting is
available. It has a hard stop — `hnsw.max_scan_tuples`, default 20,000 — so on
a selective filter it can **still** return fewer rows than asked for, silently.

**Two corrections made during the lesson, both mine:**

1. I first wrote that per-artifact LIST partitioning **"cannot be used"**. That
   was wrong. It works. It costs two DDL statements per ingest and a brief lock,
   and Postgres only suffers in the **thousands** of partitions. **We will have
   tens.** A cost was written up as an impossibility.
2. I invented the number **"500 hops"** to illustrate a flat graph walk. There
   is no measurement behind it. Deleted rather than kept as a shaped guess.


### One index per MODEL, never per dimension

The obvious plan is a table per dimension. **It is wrong**, and the reason is
already in this file: `codestral-embed` and `embed-v4.0` are *both 1536* and are
**different spaces**.

A shared graph would link chunks that have nothing to do with each other, and
every query would then need `WHERE embedding_model = ...` — the filtered-search
problem a second time, on the same graph.

```
chunks_codestral   vector(1536)     own graph
chunks_cohere      vector(1536)     own graph      <- same width, different space
chunks_gemini      vector(3072)     own graph, indexed on (v::halfvec(3072))
```

**One table per model. The table IS the filter**, so no model predicate is
needed. The list is fixed and known — it is `MIGRATION`, five entries — unlike
`artifact_id`, which is unbounded.

*Alternative, same effect, fewer tables:* one table per dimension plus a
**partial index** per model (`... WHERE embedding_model = 'codestral-embed'`).
Same trap as the `halfvec` cast — **the query must match the index predicate
exactly, or the index is decoration.**


### The three shapes, and why the decision is deferred

Slice 8 chooses the embedder. Slice 4 must not pre-empt it.

| | mixed models in one table | index | verdict |
|---|---|---|---|
| **A** — one table, undimensioned `vector` | ✅ | ❌ **impossible** | simplest; defers everything to slice 8 |
| **B** — one table per model | ✅ | ✅ one HNSW each | full speed, five tables |
| **C** — one table `vector(1536)` | ❌ codestral only | ✅ | **rejected — it guesses the winner** |
| **D** — partition per artifact | ✅ | ✅ **pure graph** | what the industry does; DDL per ingest |

**pgvector allows a column declared `vector` with no width**, which stores any
dimension — but **cannot be indexed**. So the real fork is: *one table for every
model, or an index.* **UNVERIFIED against our Supabase project. Measure it; do
not put it in the schema on my word.**


### The decision ORDER, fixed now so a number cannot bend it later

```
1. the table + the write path        needed by everything
2. exact search                      the baseline, and the correct answer
3. partition per artifact + HNSW     the skill gap, and the speed
4. measure: recall and latency       exact vs HNSW, WITH THE REAL FILTER
5. decide which one ships
```

**Step 2 is not an alternative to step 3 — it is the instrument that judges
it.** There is no way to score an approximate index without the exact answer:

$$
\text{recall}_{\text{index}} =
\frac{\lvert \text{HNSW top-}k \;\cap\; \text{exact top-}k \rvert}{k}
$$

**And this recall is NOT slice 1's recall.** They are different failures and
they multiply:

| | asks |
|---|---|
| **embedder recall** (slice 1) — 0.941 | is the right chunk ranked high **at all**? |
| **index recall** (slice 4) | did the index find what the exact scan **would** have found? |

$$
0.941 \times 0.90 \approx 0.85
$$

An index at 0.90 quietly costs nine points of end-to-end recall, and **nothing
raises an error**. That is the price of the word *approximate*, and it is why
step 4 exists.

**If HNSW loses, keep the code anyway.** It was built to close one of
[the four gaps](../../rules/teaching-and-communication.md#the-four-gaps-are-the-whole-point--teach-them-hardest-of-all),
and the measurement is itself the lesson. Ship exact; keep the mechanism.


### Why the industry answer does not transfer

Big vector databases do not accept "search every tenant". They isolate:
Pinecone **namespaces**, Weaviate **multi-tenancy** (a shard and a graph per
tenant), Qdrant **tenant-ordered payload indexes** and filter-aware graphs like
**ACORN**. At real scale they also tier (small tenants share a graph, large ones
get their own), hash-shard, and offload cold tenants.

**None of it transfers, and the reason is our shape:**

| | big company | LabPilot |
|---|---|---|
| tenants | millions | **tens** |
| rows per tenant | 50–50,000 | **~1,000** |
| queries/day | millions | a few |

We sit in the *few tenants, medium tenant* corner, which is the easy one.
**Isolation is trivial for us and the million-tenant problem is not ours.**

> Those products are **evidence**, not tools. pgvector has no namespace feature
> — in Postgres you buy isolation with schema (a table, a partition, or a
> partial index per tenant), and that is the whole cost difference.


### The schema

```sql
CREATE TABLE artifacts (
    id               text PRIMARY KEY,
    name             text        NOT NULL,
    side             char(1)     NOT NULL CHECK (side IN ('A', 'B')),
    embedding_model  text        NOT NULL,
    dim              int         NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE chunks (
    artifact_id  text NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    chunk_index  int  NOT NULL,
    text         text NOT NULL,
    header       text NOT NULL DEFAULT '',
    source       text NOT NULL,
    start_line   int  NOT NULL,
    end_line     int  NOT NULL,
    v            vector(1536) NOT NULL,
    PRIMARY KEY (artifact_id, chunk_index)
);
```

#### Change 1 — `embedding_model` and `dim` move to the ARTIFACT

This file said, since 2026-08-13:

> *"Store `embedding_model` and `dim` on every row. Then a model mismatch is
> **detected** instead of silently poisoning search."*

**That is now overridden, and the user approved the change.**

| Where | Result |
|---|---|
| on every **chunk** | rows *can* disagree, so you need a check to **detect** it |
| on the **artifact** | rows *cannot* disagree, so there is nothing to detect |

> **Put a rule where it cannot be broken, not where it can be checked.**

The old rule was correct **when it was written** — slice 3 had a `Chunk`
dataclass and no database, so per-row was the only place it could live. Two
tables created a better place. `Chunk.embedding_model` and `Chunk.dim` stay on
the dataclass; they simply do not become columns.

#### Change 2 — no `side` column on `chunks`

One artifact has exactly one side, so `artifact_id` already determines it. **The
`side` filter from the chunking rules becomes `WHERE artifact_id = $1`** — the
filter we were writing anyway. One predicate, not two.

#### And no `chunk_count` column

`COUNT(*)` gives it. A stored count is a second copy of the truth, and second
copies drift. The UI's `42 chunks` reads the count; it does not need a column.


### The write path — two problems that are NOT the same problem

**Problem A — memory.** 2,000 vectors of 1,536 floats held as Python lists is
**~73 MB**, against a [512 MB box](../../product/memory-budget.md#memory-budget--render-free-tier-512mb) that
is also serving the API. So embed and insert in batches of `MAX_BATCH_SIZE`:

$$
96 \times 1{,}536 \times 32\ \text{bytes} \approx 4.7\ \text{MB peak}
$$

**Problem B — half a corpus.** If ingest dies at chunk 1,200 of 2,000, the
1,200 must not survive. A half-searched corpus returns confident wrong answers.

```sql
BEGIN;
  DELETE FROM artifacts WHERE id = $1;   -- cascade removes the old chunks
  INSERT INTO artifacts ...;
  INSERT INTO chunks ...;                -- batch 1, batch 2, ...
COMMIT;                                  -- all 2,000, or none
```

> **Streaming and atomicity do not conflict.** Streaming is about Python
> objects; the transaction is about the database. Batch the inserts *inside* one
> transaction. The leading `DELETE` also makes re-ingest **idempotent**.


### The driver — decided, not yet installed

**`psycopg[binary]==3.2.12`, and nothing else.**

| Rejected | Why |
|---|---|
| `asyncpg` | our routes are plain `def` (slice 5, because `requests` blocks). An async driver fights that |
| `supabase-py` | pulls `httpx`, `gotrue`, `storage3`. **Supabase is Postgres** — talk to it as Postgres |
| the `pgvector` Python package | wants **numpy** (~20 MB) for a convenience we do not need. A vector goes over the wire as a string, cast with `::vector` |

**Use port 5432, never 6543.** Supabase's transaction pooler rejects prepared
statements, which psycopg3 uses by default — the failure is
`prepared statement ... already exists`, and it looks like a code bug.


### `store/` is an ADAPTER

It talks to the outside world, so it sits beside `llm/`, `embed/` and
`sources/` — not with the pure logic in `ingest/`. It may import `tokens` and
`_text` only, and `test_architecture.py` fails the build if it reaches `api/`.

```
ingest/  ->  embed/  ->  [ store/ ]  ->  retrieval/  ->  prompts/  ->  llm/
  Chunk       Vector      SLICE 4        slice 5-7
```

Until slice 4, `embed()` returns a vector and **we throw it away**. Slice 4
gives it a home; slice 5 is the first thing that can ask it a question.


### What slice 4 must measure, and it is more work than the code

Estimated source: ~260 lines across `contracts` / `errors` / `schema.sql` /
`connection` / `writer` / `search` — the same size as `sources/` in slice 2.
**The measurement is the larger half.**

| Run | Must record |
|---|---|
| exact, real filter | latency, and recall = 1.00 by definition |
| HNSW, `iterative_scan` off | latency, index recall, **how many rows came back** |
| HNSW, `iterative_scan` relaxed | latency, index recall |
| partitioned + HNSW | latency, index recall |

**Assert the query PLAN, not only the result.** Writing the `ORDER BY` the
natural way silently falls back to a sequential scan — no error, no warning,
correctness unchanged, only speed. `EXPLAIN` is the only thing that tells you.

And `queries.json` already exists as the instrument: 17 graded queries whose
ground truth is stored as **line numbers**, so it survives any change to
chunking. `scripts/retrieval/score_retrieval.py` runs it for four embedding requests.


### What is NOT decided, on purpose

- **The embedder.** Slice 8 decides it. Slice 4 must not build a schema that
  assumes codestral won.
- **Exact vs HNSW.** Step 5 of the order above, on our numbers.
- **`hnsw.ef_search`, `m`, `ef_construction`.** Defaults until measured.
- ~~Whether an undimensioned `vector` column really works on our Supabase
  project.~~ **ANSWERED 2026-09-04: it works, and it cannot be indexed. See
  below.**

# Step 1, slice 4: the vector store

[Docs home](../README.md)

## Slice 4 — the theory, recorded 2026-09-03

*Session 16 wrote no source on purpose: lessons 1-3 of the vector-database gap (what an index is, how HNSW walks a graph,
what one row must hold) changed the schema twice and corrected two things this file had written.* **What slice 4 had to
prove:** ~2,000 chunks go in and come back unchanged, **and a query really uses the plan we intended.**

### The question slice 4 actually has to answer

Not "how do we build an HNSW index?" but **"do we need an index at all?"** Rows per artifact are ~1,000 (a repository is 1,094
chunks, measured), every query is filtered by `WHERE artifact_id = $1`, and exact cost is ~1,000 × 1,536 ≈ 1.5M ops. **The
64.7 ms / 326.0 ms measurement of 2026-08-28 had NO filter on it:** it compared an index scan with a full scan over 2,000 rows.
**A benchmark without your `WHERE` clause is a benchmark of a different query**: the pgvector gate proved the index *can be
built*, never that it is *needed*.

### Filtered vector search — the thing that makes an index awkward

HNSW builds **one graph over every row**, across all artifacts; links cross artifacts, so there is no sub-graph of artifact 7
to enter and the greedy walk visits other artifacts' chunks and throws them away (`iterative_scan off` visits ~200 of 10,000
and yields ~20 usable rows, too few; `relaxed` visits ~2,000 for 50 rows, ~10x slower; exact always correct). pgvector 0.8.0
added `hnsw.iterative_scan` (we have 0.8.2), with a hard stop `hnsw.max_scan_tuples` (default 20,000) that can still return
fewer rows than asked, silently. Two corrections made in the lesson, both mine: I first wrote that per-artifact LIST
partitioning "cannot be used", which was wrong (it works: two DDL statements per ingest and a brief lock, and Postgres only
suffers in the thousands of partitions while we will have tens), and an invented "500 hops" figure was deleted.

### One index per MODEL, never per dimension

`codestral-embed` and `embed-v4.0` are both 1536 and are **different spaces**. A shared graph would link unrelated chunks and
every query would need `WHERE embedding_model = ...` (the filtered-search problem again). Per-model tables make the table
itself the filter (the model list is fixed: `MIGRATION`); the alternative is one table per dimension plus a partial index per
model, with the same trap as the `halfvec` cast: **the query must match the index predicate exactly, or the index is decoration.**

### The three shapes, and why the decision is deferred

A — one table, undimensioned `vector` (mixed models; **cannot be indexed**; defers everything to slice 8) · B — one table per
model (one HNSW each, full speed, five tables) · C — one table `vector(1536)` (**rejected: it guesses the winner**, codestral
only) · D — a partition per artifact (pure graph, what the industry does, DDL per ingest). pgvector allows a column declared
`vector` with no width but cannot index it, so the real fork was *one table for every model, or an index*.

### The decision ORDER, fixed now so a number cannot bend it later

(1) table + write path · (2) exact search, the baseline and the correct answer · (3) partition per artifact + HNSW · (4) measure
recall and latency **with the real filter** · (5) decide what ships. **Step 2 is not an alternative to step 3; it is the instrument
that judges it** (recall_index = |HNSW top-k ∩ exact top-k| / k). This recall is **not** slice 1's recall: they are different
failures and they **multiply** (0.941 × 0.90 ≈ 0.85), so an index at 0.90 quietly costs nine points of end-to-end recall with no
error. If HNSW loses, keep the code anyway (it was built to close one of the four gaps): ship exact, keep the mechanism.

### Why the industry answer does not transfer

Pinecone namespaces, Weaviate multi-tenancy, Qdrant tenant-ordered payload indexes and ACORN isolate millions of tenants of
50-50,000 rows. LabPilot has **tens** of tenants of **~1,000** rows and a few queries a day: isolation is trivial and the
million-tenant problem is not ours. Those products are evidence, not tools (pgvector has no namespace feature; in Postgres you
buy isolation with a table, partition or partial index per tenant).

### The schema

Two tables, `artifacts` (id, name, side CHECK 'A'/'B', embedding_model, dim, created_at) and `chunks` (artifact_id → artifacts
ON DELETE CASCADE, chunk_index, text, header, source, start_line, end_line, a vector, PRIMARY KEY (artifact_id, chunk_index)).
The vector column was planned `vector(1536)` and built undimensioned (shape A).

#### Change 1 — `embedding_model` and `dim` move to the ARTIFACT

The old rule (since 2026-08-13) said to store them on every row so a mismatch is *detected*. **Overridden, with the user's
approval:** on the artifact, rows *cannot* disagree and there is nothing to detect. **Put a rule where it cannot be broken, not
where it can be checked.** (The old rule was right when written: slice 3 had a `Chunk` dataclass and no database. `Chunk.embedding_model`
and `Chunk.dim` stay on the dataclass and simply do not become columns.)

#### Change 2 — no `side` column on `chunks`

One artifact has exactly one side, so `artifact_id` already determines it: the `side` filter becomes `WHERE artifact_id = $1`.

#### And no `chunk_count` column

`COUNT(*)` gives it; a stored count is a second copy of the truth and second copies drift.

### The write path — two problems that are NOT the same problem

**Memory:** 2,000 vectors of 1,536 floats as Python lists is ~73 MB against a 512 MB box also serving the API, so embed and insert
in batches of `MAX_BATCH_SIZE` (96 × 1,536 × 32 bytes ≈ 4.7 MB peak). **Half a corpus:** if ingest dies at chunk 1,200 of 2,000 the
1,200 must not survive (a half-searched corpus returns confident wrong answers). One transaction: `DELETE FROM artifacts WHERE id
= $1` (cascade removes old chunks), insert the artifact, insert chunks in batches, `COMMIT` — all or none, and re-ingest is
**idempotent**. **Streaming and atomicity do not conflict:** streaming is about Python objects, the transaction about the database.

### The driver — decided, not yet installed

**`psycopg[binary]==3.2.12`, and nothing else.** Rejected: `asyncpg` (our routes are plain `def`), `supabase-py` (pulls `httpx`,
`gotrue`, `storage3`; Supabase is Postgres), the `pgvector` Python package (wants numpy ~20 MB; a vector goes over the wire as a
string cast with `::vector`). **Use port 5432, never 6543:** the transaction pooler rejects the prepared statements psycopg3 uses
by default (`prepared statement ... already exists`, which looks like a code bug).

### `store/` is an ADAPTER

It talks to the outside world, so it sits beside `llm/`, `embed/` and `sources/`, may import only `tokens` and `_text`, and
`test_architecture.py` fails the build if it reaches `api/`. Until slice 4, `embed()` returned a vector and we threw it away.

### What slice 4 must measure, and it is more work than the code

~260 lines of source (`contracts`, `errors`, `schema.sql`, `connection`, `writer`, `search`); the measurement is the larger half:
exact with the real filter, HNSW with `iterative_scan` off and relaxed, and partitioned + HNSW (latency, index recall, how many
rows came back). **Assert the query PLAN, not only the result:** writing the `ORDER BY` the natural way silently falls back to a
sequential scan (correctness unchanged, only speed) and only `EXPLAIN` tells you. `queries.json` is the instrument.

### What is NOT decided, on purpose

The embedder (slice 8), exact vs HNSW (step 5, on our numbers), and `hnsw.ef_search` / `m` / `ef_construction` (defaults until
measured). *Whether an undimensioned `vector` works on Supabase was answered 2026-09-04: it works, and it cannot be indexed.*

## Slice 4, first half — DONE 2026-09-04: the table and the write path

*Steps 1 and 2 of the five-step decision order. **533 passed, 10 of 10 mutations real.** Nothing here calls a model, so no ISP
probe was needed (a database is not a model).*

### The connection: the direct string is dead from here, and the dashboard says why

`db.<project-ref>.supabase.co` does not resolve (IPv4 or IPv6): the dashboard says "Direct connections use IPv6 by default" and
sells a paid IPv4 add-on. The answer is the **session pooler**:
`postgresql://postgres.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:5432/postgres`. Three things about that string are easy to
get wrong: the port must be **5432** (session mode; 6543 is transaction mode and fails as `prepared statement "_pg3_0" already
exists`, which reads like a bug in our code), the **user is `postgres.<project-ref>`** (one pooler serves many projects), and
the region is found by probing (a wrong one answers `Tenant or user not found`). **Read the connection string, never the tab
label** (the Connect dialog's default tab is a JavaScript SDK page with no Postgres string).

### What was measured, and it settles the schema

On the real project (PostgreSQL **17.6**, pgvector **0.8.2**, already installed): `create table (v vector)` with no width
works and holds a 3-dim and a 5-dim vector in one column; `<=>` works on it; **hnsw on it fails** (`column does not have
dimensions`); hnsw on `vector(3072)` fails (`cannot have more than 2000 dimensions`); hnsw on `(v::halfvec(3072))` works (the
2026-08-28 workaround holds). `idle_in_transaction_session_timeout` is **0 (no limit)** and `statement_timeout` is **2 min**. So
**shape A is real: one table, one undimensioned column, no index.** That is right for steps 1-2 (exact search needs no index) and
keeps slice 8 free to choose the embedder, which a `vector(1536)` column would silently decide. **The timeout row is what makes
the write path legal:** one transaction may stay open while we wait on the embedder between batches (had it been 60 s the
streaming design would have changed; it was worth two seconds to check).

### pgvector is float4 — vectors do NOT come back unchanged

`sent 0.3333333333333333 → read back 0.33333334` (max absolute error ~6.7e-9). **Text comes back exactly; vectors to about 7
significant digits.** Harmless for ranking (even 16-bit `halfvec` cost 0 of 10 in ranking overlap) but never to be asserted as
equality: `test_the_vectors_survive_only_to_float4_precision` pins it **including an assertion that it is NOT exact**, so a
future session cannot "fix" a bug that does not exist.

### What shipped

`store/` is the sixth package: `contracts.py` (`ArtifactRecord`, `ChunkRecord`, `Vector`, `Side`), `errors.py` (`StoreError`,
`NotConfigured`, `ModelMismatch`, `ConnectionFailed`), `defaults.py` (`CONNECT_TIMEOUT`, `INSERT_BATCH_SIZE`), `schema.sql`,
`connection.py` (`database_url`, `connect`, `create_schema`) and `writer.py` (`write_artifact`, one transaction, streamed); search
and keyword arrived later (`store/` is now contracts · errors · defaults · schema.sql · connection · writer · search · keyword ·
reader).

### `store/` may not import `embed/` or `ingest/`, and that shaped everything

`test_architecture.py` lets an adapter import only `tokens` and `_text`, so `store/` cannot accept an `ingest.Chunk` or import
`Vector` from `embed.contracts`. That is the rule working: two adapters that know each other's types are welded together. The
store owns its own record types and **`api/services.py` does the translation** (entry is the only layer allowed to import both):
`bytes → str → Chunk → vector → ChunkRecord → Postgres`. `Vector = tuple[float, ...]` is **duplicated**, not promoted: the
precedents for promotion (`truncate`, `estimate_tokens`) were *behaviour*, where two copies drift into a bug; a structural alias
cannot.

### The schema, and the three columns that are absent on purpose

`embedding_model` and `dim` sit on **`artifacts`** (one artifact has one model, so its rows cannot disagree: **put a rule where it
cannot be broken, not where it can be checked**). **No `side` column** (`artifact_id` decides it). **No `chunk_count`** (`count(*)`
gives it; a second copy drifts). **No index on `artifact_id`** (it is the primary key's leading column). `on delete cascade` is
load-bearing: it makes re-ingest **idempotent**, because the writer's leading `delete from artifacts` clears the chunks with it.

### Streaming and atomicity are not in conflict — and indentation is the boundary

Memory wants `INSERT_BATCH_SIZE = 96` at a time (~4.7 MB peak, derived independently of `embed`'s `MAX_BATCH_SIZE` from the same
memory budget, because `store/` cannot import `embed/`); atomicity wants one transaction. The batches therefore run *inside* one
`conn.transaction()`. **This was not theoretical:** the loop was first typed *outside* the `with` block; the symptom was lucky
(`InterfaceError: the cursor is closed`), but had the cursor stayed open every chunk would have committed separately and
**nothing would have raised**. **Four spaces of indentation decided whether the write was atomic; a correctness property with no
error message needs a test, not care.**

### How a vector crosses the wire

`str(list(vector))`: stdlib only, no numpy, and it is what the `pgvector` package would have produced (a plain list and
scientific notation both work). **Reading back returns a `str`, not a list**, so search must parse if it ever needs the vector.

### Testing: a new cost class, and a gap named rather than hidden

Database tests cost no API quota but need a live Postgres, so `--run-smoke` is the wrong gate: they carry a `database` marker and
**skip on a missing `DATABASE_URL`** (so a green run can mean they never ran: read the skip reasons with `pytest -q -rs`), and
`.env` is loaded **inside the fixture only** (five `tests/unit/embed/` files manipulate env vars). They run in their own
schema; the fixture connection is **autocommit** (otherwise one deliberate `CheckViolation` poisons the transaction and every
later test dies with "current transaction is aborted"; `conn.transaction()` still begins and rolls back under autocommit, so the
atomicity test is real). A test hitting Supabase is not a unit test, so it lives in `integration/`. **The gap that was stated here
(CI has no `DATABASE_URL`) was CLOSED 2026-09-04:** CI runs a `pgvector/pgvector:pg17` service container (no secret, works on forks;
533 tests in ~15 s against ~40 s over the VPN), and `test_ci_really_runs_the_database_tests` fails the build if the workflow loses
`DATABASE_URL` or the service. A secret was the obvious fix and the wrong one: two concurrent jobs would both
`drop schema labpilot_test cascade`, the flake below reintroduced by concurrency.

### The flaky suite, and the three causes behind it — 2026-09-04/05

*The user: "every time I run the full test, one test fails... after running 4 or 5 times all pass, without doing anything." A suite
that is not telling the truth. All three causes were in the test fixture, none in `store/`.* The instrument that found it: log
`pg_backend_pid()` on every connection (12 connections across 6 runs all reported one backend: Supabase's Supavisor pooler
recycles one server process and resets session state between checkouts).

- **Cause 1 — session state is not a place to keep isolation.** The fixture used a runtime `set search_path`; a pooler reset throws
  a runtime `SET` away but **restores a startup option** (measured: runtime SET → `'"$user", public, extensions'`, startup option →
  `'labpilot_test,public'`). The fix is a libpq **startup parameter** (`options=-c search_path=...`). The loss was **silent**: stale
  `public.artifacts`/`public.chunks` existed, so bare `artifacts` resolved to the real schema (the write went to `public`, the read
  to `labpilot_test`); those tables were dropped so a future loss fails loudly. **Isolation in session state is isolation a pooler
  can revoke.**
- **Cause 2 — a pooled connection is not a durable resource.** A module-scoped fixture held one connection; when the pooler dropped
  it (`server closed the connection unexpectedly`) every later test inherited a dead one. Fix: **pre-ping** before handing it out
  (~0.3 s, against ~2 s to reopen per test), **one retry** on a test's first statement, and `delete from artifacts` per test, **never
  `truncate`** (it needs ACCESS EXCLUSIVE and blocked on a pooled lock until the 2 min `statement_timeout`; the folder went 28 s →
  238 s). Measured after: 20 full runs, 0 failures.
- **Cause 3 — one schema name shared by every run** (found 2026-09-05 after "fixed" was declared wrongly: twenty green runs in one
  terminal proved nothing about two runs at once, and the suite was also run from the VS Code Testing panel). Every run used the
  same hardcoded `labpilot_test` and began with `drop schema ... cascade`, so run B deleted run A's tables mid-test (signature: two
  statements on one connection landing in different worlds, `relation "chunks" does not exist`). Reproduced on demand (two
  concurrent processes: 2 and 4 failures; one schema per run: 39 passed twice; two full suites at once: 544 passed twice). The fix is
  `labpilot_test_{pid}_{token_hex(3)}` and a teardown that removes only what it created. **"It passes on my machine, twenty times"
  is not evidence about concurrency; a shared mutable name is a shared mutable resource.** The reasoning had been applied to CI
  and not to the machine it was written on.

Two mutations verified (runtime SET instead of the startup option; pre-ping always claiming healthy) plus a **refusal guard**:
if `current_schema()` is not the test schema after setup the fixture raises (`Refusing to touch the real schema`) instead of
creating tables somewhere else. **A flaky test is a test whose environment you have not modelled; a wrong hypothesis costs nothing
if you test it** (two of mine died on contact); **fixing a silent failure often reveals a second one.**

### Mutation results — 10 of 10 real

Dropping `ON DELETE CASCADE`, pinning the column to `vector(3)`, dropping `IF NOT EXISTS`, dropping the side CHECK, putting the URL in
the error, dropping `from exc`, deleting the side guard, dropping the writer's leading DELETE, looping outside the transaction and
dropping the width check each fired the test meant to catch it. M5 printed the leak it prevents
(`could not reach postgresql://postgres.abc:hunter2SECRET@host...`): it pins that *we* never repeat the URL, while whether
**psycopg** leaks a password was measured live (it does not), which is why no scrubbing code exists — **check the threat before
writing the guard**. M2 guards a **decision**: writing `v vector(1536)` turns it red and forces the embedder conversation.

### One small defect the new dependency exposed

`test_every_package_labpilot_imports_is_pinned` split each requirement on `==` and never learned about **extras**
(`psycopg[binary]==3.2.12` was stored under a name the import could never match); `.split("[")[0]` fixes it, and deleting the
dependency still fails the test. **Loosening a parser can quietly kill a test's ability to fail; re-run the case the test exists
to catch.**

### What the first half deliberately did NOT do

No index (it must not come before the exact baseline that scores it), no search (`SearchHit` absent until its consumer exists), no
wiring into `services.py` (`write_artifact` reachable only from tests: scaffolding with a scheduled consumer) and no connection
pool (`psycopg_pool` is a separate package; one connection per operation until something measures otherwise).

## Slice 4, step 2 — DONE 2026-09-05: exact search

*The baseline, and the **instrument** that scores HNSW: exact search is the correct answer **by definition**, so there is nothing
else to grade an approximate index against. **544 passed.*** Added `store/search.py` (`search(conn, artifact_id, query, *, model,
limit)`), `SearchHit` (the hit plus its `score`), `UnknownArtifact`, and `SEARCH_LIMIT = 50` (retrieve wide, rerank to ~10).

### `<=>` is DISTANCE, so `order by` takes no `desc`

Cosine distance: smallest is nearest; `score = 1 - distance` flips it back for the reader. We still sort the **distance**, because
pgvector recognises exactly one shape: `order by v <=> q` can be served by an index, while `order by 1 - (v <=> q) desc` hides the
distance from the planner (same answers, no error, and 5x slower at 2,000 rows already). **`score` is a label that rides along,
never a sort key.**

### The guard that matters: two embedding spaces do not compare

`search` takes `model: str` and refuses when it differs from the artifact's `embedding_model`; without it a codestral corpus
searched with a Gemini query returns confident nonsense and raises nothing. `store/` cannot import `embed/`, so the model arrives
as a plain string (the layering rule doing its job). `UnknownArtifact` exists because returning `()` for a corpus never stored is
indistinguishable from "nothing matched".

### The `::vector` cast is NOT required — and I claimed it was

An earlier comment said the cast was load-bearing. **The mutation disproved it** (removing both casts: 10 passed; psycopg3 sends
the parameter as `unknown` and Postgres coerces it). The casts stay as belt-and-braces, the comment now says so and **no test
pretends to pin it**. **A surviving mutation is not always a bad test; sometimes it is a false claim in a comment.**

### Mutation results — 7 real, 1 survivor, 3 broken mutations

Reversing the order (4 order-dependent tests), score = raw distance, a filter matching every artifact, a disabled model guard, a
missing artifact returning `()`, a disabled width check and a disabled limit guard each fired the test meant to catch it (most
**alone**); `::vector` removed fired nothing (the claim was wrong, not the test). **Three mutations were themselves broken and
looked like results:** deleting the `where` line left 4 parameters for 3 placeholders; replacing it with `%s is not null` failed on
`IndeterminateDatatype`; a guard mutation written with 8 spaces where the code has 4 **never applied at all**. **Assert the anchor
before trusting a mutation:** `s.replace(old, new)` on a string that is not there is a silent no-op, indistinguishable from a test
that cannot fail.

### The fixture geometry is arithmetic, not a guess

Four chunks placed by hand against the query `[1, 0, 0]` (`[1,0,0]` → distance 0, score 1; `[0.9,0.436,0]` → ~0.1; `[0,1,0]` → 1.0;
`[-1,0,0]` → 2.0, score -1): the expected order is `0,1,2,3` and a stray `desc` returns exactly `3,2,1,0`. Every value follows from
the angle, so the test says what it means.

### What step 2 deliberately did NOT do

No index (it must not precede the baseline that scores it), no hybrid keyword search (slice 5), no caller (`search` was reachable
only from tests until slice 7 wired `api/services.py`).

## The chunk cap fix — 2026-09-05, the last cheap moment

*The oldest known bug, carried as `xfail(strict=True)` since 2026-08-28, fixed now for one reason: **the fix moves chunk
boundaries** and nothing was stored yet (re-chunking cost four embedding requests; after slice 7 it would mean re-chunking and
re-embedding every stored corpus).* **Fix chunk boundaries before pgvector holds anything, or not at all.**

### The bug

`MAX_CHUNK_TOKENS = 510` was enforced on `chunk.text`, but what the embedder and reranker receive is `chunk.embed_text` — **header
plus text**. `B_train.py` had 2 of 79 chunks over (worst 526), the whole repository 43 of 1,094; after the fix 0 of 82 (worst 504) and
**0 of 4,889** (worst 509). Real consequences: **BGE Base** declares 512 tokens and refuses those chunks, and **Cohere auto-splits**
any document over 510, silently multiplying the billed rerank documents the budget arithmetic assumes.

### The fix — reserve the header before you cut, not after

The header is built *after* every size decision and holds two things the split has not decided (the `part i/n` suffix and the line
numbers), so `_reserve` is deliberately **pessimistic** (it always allows `part 999/999` and the widest line numbers the file can
produce) and `_budget = MAX_CHARS - _reserve`; over-reserving costs a few characters, under-reserving is the bug.
`split_recursive` takes `max_chars` (threaded through `_blocks` and `_pack`); `_pack`'s target became `min(TARGET_CHARS, max_chars)`
(`TARGET_CHARS` 1,500 sits just under the old cap); and **`_merge_small` had to learn the same budget** or it could rebuild the
oversized chunk the split had just avoided.

### Re-scored, because boundaries moved

`B_train.py` 79 → 82 chunks: recall@1 0.412 / @5 0.941 / @10 0.941 unchanged, MRR 0.613 → 0.608 (one query moving one place); `D2` is
still the known miss at rank 46.

### Mutation results — 2 of 3, and the survivor is honest

No header room reserved (the cap test **alone**) and a packing target that ignores the budget (the cap test + the recursive
fallback test) fired; dropping the `+1` for the newline `embed_text` puts between header and text fired nothing (the reserve is
pessimistic enough that one character of slack never shows). **Kept as correctness in principle and recorded as untested.**

### The other xfail stays

`test_an_archive_we_accept_must_be_able_to_reach_us` stayed `xfail(strict=True)` (`MAX_ARCHIVE_BYTES` 50MB against a ~10MB body
limit; choosing which number moves was slice 7's decision). *Closed 2026-09-28: both limits are 10MB now.*

## Slice 4, steps 3-5 — first measurement, and its conclusion was WRONG

> **OVERTURNED the same day. Read [the corrected measurement](#the-index-question-remeasured--2026-09-05-hnsw-wins-at-real-repo-size)
> first.** The numbers are real; the *inputs* were not. Both the corpus size (1,000 rows) and the vectors (uniform random) were
> unrepresentative, and each one alone was enough to invert the answer.

*Step 3 ("partition per artifact + HNSW") was built on a throwaway schema, not put in `schema.sql` (an index needs a fixed width,
which would have chosen the embedder slice 8 owns).*

### The numbers, on 10,000 rows across 10 artifacts, `vector(1536)`

Exact (B-tree on `artifact_id`, then sort) **8.0 ms**, recall 1.00 by definition · shared HNSW over every artifact 8.0 ms, **ignored by
the planner** (76 s to build, 57 MB) · partial HNSW per artifact, **ignored** · the same forced with `enable_sort = off` 1.2 ms,
recall **0.82** · **partitioned + HNSW per partition 1.4 ms, recall 0.82**. The decision then: ship exact, build no index.

### Why, in the order the reasons actually weigh

(1) 8 ms is already fast and exact (the plan guessed ~160 ms: 18x cheaper than estimated); (2) cost follows rows **per artifact**,
not corpus size (1,000 chunks 8.0 ms · 2,000 16.1 ms · 5,000 40.3 ms), and the filter is always `WHERE artifact_id = $1`;
(3) the only variant the planner uses costs 18% of recall (0.941 × 0.82 = 0.77); (4) Postgres refuses the index on its own
(sorting 1,000 rows is cheaper than walking a graph and discarding 90% of it; partitioning is the only shape that gets used because
pruning removes the predicate); (5) partitioning costs **216 ms of DDL per ingest**, a lock and lifecycle. **The index was never the
question; "how many rows does one query actually touch?" was.** Revisit around 20,000 chunks in one artifact.

### Two measurement mistakes, both mine, both caught before they were believed

(1) **Every row had the same vector**: the generator's inner subquery never referenced `i`, so Postgres evaluated it once; caught by
a sanity check (distances `min 0.000 avg 0.000 max 0.000`), fixed with a correlated `LATERAL`. (2) **A recall of 1.00 that could not
have been anything else**: truth was computed *after* the index was created, comparing the index against itself; truth is now taken
**before any vector index exists** (the same measurement then reported 0.82). **A benchmark is code and fails the same way tests do.**
The generator bug also voids the "10 of 10 overlap" claim of the 2026-08-28 gate. Fixture note: uniform `random()` puts every vector
in the positive orthant (all pairs near 0.75 cosine); `random() - 0.5` spreads them over the sphere.

### What this does NOT decide

The embedder: `schema.sql` is untouched and `v` is still an undimensioned `vector`. If a 3072-dim model wins and an index is ever
wanted, the `(v::halfvec(3072))` expression index is the route.

## The index question, remeasured — 2026-09-05: HNSW wins at real repo size

*The first pass was wrong for two independent reasons, both in the fixture. Re-run on a local `pgvector/pgvector:pg17` container so a
free-tier instance was never the variable.*

### What a real artifact actually holds — measured on real repositories

**FastAPI 24,364 chunks (14.7 MB of text)**, Django **REFUSED** (over our own 20 MB `MAX_TOTAL_BYTES`), requests 924. So 1,000 chunks
is the small case, not the normal one.

### The corrected numbers, on CLUSTERED vectors, `vector(1536)`

| chunks in one artifact | exact | HNSW | speedup | recall@10 |
|---|---|---|---|---|
| 1,000 | 6.7 ms | index not used | 1x | 1.00 |
| 5,000 | 30.7 ms | **0.55 ms** | **56x** | 1.00 |
| 15,000 | 75.8 ms | **1.24 ms** | **61x** | 1.00 |
| 30,000 | 144.3 ms | **1.38 ms** | **104x** | 0.98 |

### Why the first answer was wrong — the fixture, twice

(1) **Uniform random vectors are DEGENERATE, not merely hard**: in 1,536 dimensions they are nearly orthogonal and equidistant, so the
"true" top-10 is a set of near-ties (30,000 rows: recall@10 **0.04** uniform vs **0.98** clustered; 0.04 measures noise, and the
earlier 0.82 came from the same family and must not be quoted). (2) **The corpus was sized at the small end**: exact is 6.7 ms at
1,000 rows and 144 ms at 30,000 locally, and **10,019 ms** at 30,000 on the Supabase free tier, where 184 MB of vectors stop fitting
the cache. **A benchmark answers the question its fixture asks.**

### The operational lesson, learned the expensive way

Building the 30,000-row HNSW on the real project with `maintenance_work_mem = 512MB` **took the instance down** (the index built in
176 s; the connection died during the `ANALYZE` after it) and it did not come back on its own. **Never size a benchmark to the
machine you wish you had; run this class of work on a local container.**

### What this changes, and what it does not

An index is now expected to be worth building; `schema.sql` is unchanged (an index needs a fixed width, still slice 8's choice). The
shape to build is the one the planner actually uses: a partition or partial index per artifact, since a shared graph is skipped
in favour of a B-tree.

## THE INDEX DECISION — settled 2026-09-05 on five real repositories

*The user refused a synthetic answer and asked for five real repositories of 10k-25k chunks: **81,493 chunks really embedded** with
`mistral-embed` (1024-dim, 22.7M tokens, ~45 minutes) into a local container.*

### Speed and recall: HNSW wins, and it is not close

pytest 9,929 chunks: exact 33.7 ms vs HNSW 0.53 ms (64x) · dask 11,527: 33.7 vs 0.44 (76x) · pydantic 13,153: 34.2 vs 0.40 (86x) ·
scikit-learn 22,520: 55.6 vs 1.86 (30x) · **FastAPI 24,364: 107.9 vs 0.98 ms (110x)**; recall@10 1.00 on all five.

### The query shape decides recall, and the default `ef_search` is too low

Those 1.00s used queries that were **copies of stored rows** (already nodes in the graph). With a **blend of two chunks** (the fair
proxy) recall was 0.94 / 0.98 / **0.86** (pydantic / scikit-learn / FastAPI); chunk + random noise (0.58 / 0.40 / 0.50) is unfair
because noise pushes a vector off the embedding manifold. **`hnsw.ef_search` recovers it:** FastAPI at 40 (default) 1.37 ms, recall
0.86; at **100** 1.93 ms, recall **1.00**; at 200 3.61 ms. **A default is not a measurement** (pgvector's 40 quietly cost 14% of
recall).

### The cost nobody had priced: the index is bigger than the table

The index is ~1.5x the table (FastAPI: table 136 MB + index 200 MB = 336 MB; ×1.5 at 1536-dim = **504 MB, the entire Supabase free
tier**, and LabPilot compares **two** artifacts: two 24k repos ~408 MB exact fits, ~1008 MB with HNSW does not).

### The decision

**HNSW with `ef_search = 100`, and storage must be solved first** (the lever is `halfvec`, 0 of 10 overlap lost, which halves table
and index). *This was then overturned by "THE FINAL DECISION" below.* **The right question was never "is HNSW faster"; it is "what
runs out first".**

### A real bug this found in our own embedder

Three of five repos failed to embed: HTTP 400 code 3210 "Too many tokens overall, split into more batches" (dask, fastapi) and HTTP
429 `backend_out_of_capacity` (scikit-learn). `MAX_BATCH_SIZE = 96` is `floor(50,000 / 510)` from the **per-minute** limit, but Mistral
also enforces a **per-request** limit and our `chars / 3` estimate under-counts badly enough to cross it (the refused batch
estimated **46,162** tokens while an accepted one measured **59,466** real tokens). **An estimate is not a budget.** **FIXED the same
day: `embed/batching.py`.** `embed.embed_batches()` sends one request per yielded batch, halves and re-sends on a refusal that names
*tokens* and **remembers the smaller size** (going back would earn the same refusal and every refusal costs a request); any other
failure is raised at once. It matches the word *token*, not Mistral's code 3210, so it holds for the other providers; proven on the
batch that failed (`embed()` alone refused, `embed_batches()` returns all 96 vectors in two requests of 48).

## The slice 4 closing review — 2026-09-05

*Across the whole system, asking only: **which real failure is still unprotected?** Two gaps, two tests, one candidate rejected, one
future bug recorded. **559 passed.***

### Gap 1 — the entire API-quota gate rested on a decorator

`tests/conftest.py` skips by marker alone, so a smoke test written without `@pytest.mark.smoke` runs on every push and spends real
quota, with nothing to report it. `test_every_smoke_test_carries_the_smoke_marker` parses `tests/smoke/` (module `pytestmark` or
decorators). **A cost gate that depends on remembering is not a gate.**

### Gap 2 — nothing stopped a default-run test from loading real credentials

`load_dotenv` appears only in `tests/integration/conftest.py` and `tests/smoke/`; `test_no_default_test_loads_real_credentials`
fails if a file under `tests/unit/` or `tests/api/` loads `.env`. It pins a property the suite already had.

### Rejected — and the reason is worth more than the test would have been

A test "every name in a package's `__all__` is importable" was written and deleted on the claim that ruff's F822 covers it. **FALSE
(measured 2026-09-13): ruff EXEMPTS `__init__.py` from F822**, so the deleted test was the only thing holding that rule, and
`labpilot/rerank/__init__.py` listed `RERANK_MAX_TOKENS` in `__all__` without importing it while the suite and both ruff commands
stayed green. Fixed 2026-09-13; the test is now `tests/unit/test_public_api.py` over **every** package (plain modules like
`tokens.py` are covered by F822 and need no duplicate). `test_every_public_name_is_importable` in `unit/llm/` was deleted with it
(mutating `llm/__all__` fires both, so the scoped one can never fire alone). **Before adding a test, ask what already fails when
the rule is broken, then prove it fails on a file of the kind you actually have; a linter rule is not a linter rule everywhere.**

### Recorded, not fixed — the boundary slice 7 will break

`api/services.py` caught `LoaderError`, `NotUtf8Text`, `LooksGenerated`, `OSError` and `AllFreeTiersExhausted` and knew nothing of
`StoreError` or `EmbeddingError`, so the moment slice 7 wired the store they would reach the 500 handler as *our* bug (the third
predictable occurrence of this shape). **When you add an error type, walk every boundary that already catches errors.** Slice 7's
checklist, since done: `NotConfigured` / `ConnectionFailed` → **503** (`StorageUnavailable`; our infrastructure is down),
`EmbeddingError` → 503 `EmbeddingUnavailable`, and once `search()` got a caller (slice 7) `UnknownArtifact` → **404**
`UnknownArtifactId` and `ModelMismatch` → **409** `ArtifactChanged`; the earlier `ALLOWED_TO_ESCAPE` excuse list shrank as each was mapped.

## THE FINAL DECISION — exact search ships, 2026-09-05

> **Exact search ships. HNSW is on the shelf with its numbers. Slice 8 re-measures both on real artifacts. TIME is the only thing
> that can overturn this — not recall, and not storage.** *(Confirmed by slice 8: exact is 2.9 / 6.1 / 11.3 ms at 335 / 729 / 1,387
> rows on the real instance, against a 350 ms round trip and a 52,700 ms report. CLOSED.)*

### Why exact wins at OUR size

The target is **1,000-10,000 chunks per artifact**: exact is 6.7 ms at 1,000 chunks (the planner refuses the index there), 30.7 ms at
5,000 and 33.7 ms at 9,929 real chunks; recall 1.00 by definition; storage 8 KB per row vs 20 KB with HNSW (2.5x). (1) 34 ms
against a ~50 s report is 0.07%; (2) recall 1.00 needs no tuning (default `ef_search = 40` silently lost 14% on FastAPI, and five
embedders would mean five tunings); (3) storage is 2.5x cheaper; (4) below ~1,000 rows Postgres will not use the index anyway.
Published guidance agrees: under ~50k vectors the gap is negligible.

### The ONE condition that reopens it

Slice 8 measures exact vs HNSW on real artifacts inside the full RAG system; if exact is genuinely too slow, the answer becomes
HNSW or a platform with more RAM. **Time is the only admissible reason** (recall cannot overturn it, exact is 1.00 by definition;
storage cannot, exact is cheaper). If it ever flips, the shape is already measured: partition per artifact, `ef_search = 100`,
`halfvec`.

### Four things I had WRONG, and the user corrected every one

(1) "The index changes speed, not correctness": **false**, recall below 1.00 means different chunks reach the model. (2) "The index
decision belongs to slice 8 with the embedder": **false**, slice 8 ranks embedders but all five stay, so the index was our call
today and deferring it was avoidance dressed as sequencing. (3) "The index costs 1.5x": it costs **2.5x and never stops** (per row
at 1536-dim: vector 8 KB + graph 12 KB = 20 KB; ~8.2 KB of index per row whether one graph or one per artifact). (4) Storage is per
ROW, not per artifact (2 × 10,000 chunks = 5 × 4,000). **An index is a trade, never a saving: spend storage, buy time.**

### And one constraint I mis-attributed

**Render's 512 MB is the API process's RAM, not the database's** (the HNSW graph would live in Postgres).

## Free vector-database platforms — verified 2026-09-05

*Every row from the provider's OWN pricing page (blog lists burned this project three times: Beam, Cerebrium, Saturn Cloud).*
**Supabase** (ours): 500 MB storage, **500 MB RAM**, paused after 1 week idle, 2 projects · **Neon**: 0.5 GB/project, **up to 8 GB RAM**, no
credit card, permanent, 100 projects, sleeps after 5 min · **Qdrant Cloud**: 4 GB disk, 1 GB RAM, 0.5 vCPU · **Pinecone**: 2 GB, 5
indexes · **Zilliz**: ~1M vectors @768-dim · **Upstash Vector**: 1 GB, **max 1,536 dim**, card on upgrade.

### Three findings that outrank the storage numbers

(1) **Supabase's binding limit is RAM, not disk** (a 30k-row exact query took 10 s there and 150 ms on a local container); Neon offers
up to 8 GB RAM at the same 0.5 GB storage. (2) **Leaving Postgres means losing exact search**: Pinecone, Zilliz and Upstash are
ANN-only; only Qdrant exposes an exact flag. (3) **Upstash is disqualified** (max 1,536 dimensions; `gemini-embedding-001` is 3072).

### The migration target, if slice 8 ever calls for one

**Neon** (Postgres + pgvector, so `store/` works unchanged with a one-line `DATABASE_URL` change; no card; 16x the RAM). Qdrant is the
only one worth its 4 GB and costs rewriting `store/` plus a client dependency. **NOT verified: the credit-card question for Qdrant,
Pinecone and Zilliz** (their pages do not say; the actual signup flow has not been run) — do not record any as no-card until it is.

## Slice 8's job grew — three measurements, not one

*Recorded 2026-09-05. Slice 8 was "decide the embedder and the reranker order".
It now also owns the search decision, because that is the first place the whole
RAG system exists on real artifacts.*

| # | Measure | Decides |
|---|---|---|
| 1 | embedder ranking on a new fixture, several repos, more than one language | which model leads `MIGRATION` |
| 2 | **reranker ranking — never measured at all** | which model leads chain 3 |
| 3 | **exact vs HNSW, on real artifacts, inside the full pipeline** | whether the 2026-09-05 decision holds |
| 4 | **END-TO-END TIME, never measured** - embed + search + rerank + generate, on a real artifact | `WARN_MINUTES` and `INGEST_MINUTES_BUDGET`, both GUESSES until this runs |
| 5 | **MERGED vs PER SIDE reranking** | whether coverage can be left to the selector - and note merged hands Voyage 50 documents, which it refuses |
| 6 | **`SEARCH_LIMIT` and `VECTOR_TOP_N` SWEPT JOINTLY** - the window 10 to 100 per side, and the cut anywhere from 1 to the whole window | all three of `SEARCH_LIMIT`, `VECTOR_TOP_N`, `RERANK_TOP_N`. Only their ORDER is a rule; `N/2` is a default nobody measured |
| 7 | **WHERE THE CUT GOES** - before the reranker as shipped, or after it | whether the reranker may RESCUE from below the cut, against Voyage reachability and half the rerank tokens |

**For measurement 3, what to record and what may not count:**

```
record   query latency at the REAL artifact sizes seen in practice
record   the same on SUPABASE, not only a local container - 500 MB RAM is the variable
record   whether latency is even noticeable against a ~50s report
IGNORE   index recall as a reason to switch TO hnsw   - exact is 1.00 by definition
IGNORE   storage as a reason to switch TO hnsw        - exact is 2.5x cheaper
```

**If it does flip, the shape to build is already measured** — partition per
artifact, `hnsw.ef_search = 100`, and `halfvec` to halve both table and index.
None of that work is wasted; it is a decision with numbers behind it.

**The one measurement still missing today:** exact at ~10,000 rows **on
Supabase**. Every latency number in the 1k-10k range came from a local
container, and the free tier has 500 MB of RAM. It is cheap, and it is the only
number that could change the answer before slice 8.

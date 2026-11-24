# Full text: Slice 4, first half — DONE 2026-09-04: the table and the write path

[Docs home](../../README.md)

## Slice 4, first half — DONE 2026-09-04: the table and the write path

*Steps 1 and 2 of the five-step decision order. **533 passed, 28 skipped,
2 xfailed, ruff clean. 10 of 10 mutations verified real.** Branch `feat/store`,
not merged. Nothing here calls a model, so no ISP probe was needed — the network
precondition is narrow on purpose, and a database is not a model.*


### The connection: the direct string is dead from here, and the dashboard says why

The plan said *"port 5432, never 6543"*. That rule survived. What did **not**
survive is the assumption that we would use the **direct connection**:

```
db.<project-ref>.supabase.co   ->  does not resolve, IPv4 OR IPv6
supabase.com                   ->  resolves
<project-ref>.supabase.co      ->  resolves
aws-0-eu-central-1.pooler...   ->  resolves, and CONNECTS
```

DNS is healthy; only that one hostname is missing. The dashboard states the
cause plainly — *"Direct connections use IPv6 by default"*, with a **paid**
IPv4 add-on as the fix. So the answer is the **session pooler**:

```
postgresql://postgres.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

**Three things about that string are easy to get wrong.** The port must be
**5432** (session mode); 6543 is transaction mode and rejects the prepared
statements psycopg3 uses by default, failing as `prepared statement "_pg3_0"
already exists` — which reads like a bug in our code. The **user is not
`postgres`** but `postgres.<project-ref>`, because one pooler serves many
projects and the username is how it routes. And the region is not guessable: it
was found by probing, since a wrong region answers `Tenant or user not found`.

> **Read the connection string, never the tab label.** The Connect dialog's
> default tab is a JavaScript SDK page with no Postgres string on it at all.


### What was measured, and it settles the schema

Every claim slice 4's theory marked UNVERIFIED was run against the real project
(PostgreSQL **17.6**, pgvector **0.8.2**, already installed — no
`CREATE EXTENSION` needed):

| probe | result |
|---|---|
| `create table (v vector)` — no width | works, and really holds a 3-dim and a 5-dim vector in one column |
| `<=>` on that column | works |
| **hnsw on it** | **fails** — `column does not have dimensions` |
| hnsw on `vector(3072)` | **fails** — `cannot have more than 2000 dimensions` |
| hnsw on `(v::halfvec(3072))` | works — the 2026-08-28 workaround holds |
| `idle_in_transaction_session_timeout` | **0 — no limit** |
| `statement_timeout` | **2 min**, per statement |
| a column literally named `text` | parses |

**So Shape A is real: one table, one undimensioned column, no index.** That is
exactly right for steps 1–2, because exact search needs no index — and it keeps
slice 8 free to choose the embedder, which a `vector(1536)` column would
silently decide for it.

**The timeout row is what makes the write path legal.** With
`idle_in_transaction_session_timeout = 0`, one transaction may stay open while
we wait on the embedder between batches. Had it been 60 s, the streaming design
would have had to change. *It was worth two seconds to check.*


### pgvector is float4 — vectors do NOT come back unchanged

Slice 4's stated goal is *"~2,000 chunks go in and come back out unchanged"*.
Measured:

```
sent 0.3333333333333333  ->  read back 0.33333334
sent 0.1234567890123456  ->  read back 0.12345679
max absolute error ~6.7e-9
```

**Text comes back exactly. Vectors come back to about 7 significant digits**,
because the `vector` type is float4. This is harmless for ranking — the
2026-08-28 gate showed even *16-bit* `halfvec` cost 0 of 10 in ranking overlap,
and float4 is far more precise — but it must never be asserted as equality, and
it was recorded nowhere. `test_the_vectors_survive_only_to_float4_precision`
now pins it, **including an assertion that it is NOT exact**, so a future
session cannot "fix" a bug that does not exist.


### What shipped

| module | holds |
|---|---|
| `store/contracts.py` | `ArtifactRecord`, `ChunkRecord`, `Vector`, `Side` |
| `store/errors.py` | `StoreError` · `NotConfigured` · `ModelMismatch` · `ConnectionFailed` |
| `store/defaults.py` | `CONNECT_TIMEOUT`, `INSERT_BATCH_SIZE` |
| `store/schema.sql` | the two tables, Shape A |
| `store/connection.py` | `database_url`, `connect`, `create_schema` |
| `store/writer.py` | `write_artifact` — one transaction, streamed |


### `store/` may not import `embed/` or `ingest/`, and that shaped everything

`store/` is an **adapter**, so `test_architecture.py` lets it import only
`tokens` and `_text`. It therefore cannot accept an `ingest.Chunk`, and cannot
import `Vector` from `embed.contracts` — a sibling adapter.

That is the rule working, not an obstacle. Two adapters that know each other's
types are welded together, and then neither can be replaced. `embed()` already
obeys it: it takes `Sequence[str]`, never `Chunk`.

So the store owns its own record types, and **`api/services.py` does the
translation**, because entry is the only layer allowed to import both:

```
bytes -> str -> Chunk -> vector -> ChunkRecord -> Postgres
                            ^ embed(chunk.embed_text)
```

`Vector = tuple[float, ...]` is **duplicated** rather than promoted to the
shared layer. The precedents for promotion (`truncate`, `estimate_tokens`) were
**behaviour**, where two copies drift apart and cause a bug. A structural type
alias cannot drift into a bug, so a shared module holding one alias would buy
no protection.


### The schema, and the three columns that are absent on purpose

`embedding_model` and `dim` sit on **`artifacts`**, not on `chunks` — the
change slice 4's theory made, now built. One artifact has one model, so its
rows *cannot* disagree and there is nothing left to detect.

> **Put a rule where it cannot be broken, not where it can be checked.**

**No `side` column**: one artifact has one side, so `artifact_id` decides it and
the side filter *is* the artifact filter — one predicate, not two.
**No `chunk_count`**: `count(*)` gives it, and a second copy of the truth
drifts. **No index on `artifact_id`**: it is the primary key's leading column,
so `where artifact_id = $1` already uses that B-tree; a second index would be a
second copy of the same thing.

`on delete cascade` is load-bearing, not decoration — it is what makes
re-ingest **idempotent**, because the writer's leading `delete from artifacts`
clears the chunks with it.


### Streaming and atomicity are not in conflict — and indentation is the boundary

The write path has two requirements that read like opposites. **Memory:** 2,000
vectors of 1,536 floats as Python lists is ~73 MB against a 512 MB box that is
also serving the API, so we hold `INSERT_BATCH_SIZE = 96` at a time
(~4.7 MB peak) and every one of the 2,000 is still stored. **Atomicity:** dying
at chunk 1,200 must leave nothing, because half a corpus answers confidently and
raises nothing.

They only look opposed because they are about different things:
**streaming is about Python objects; the transaction is about the database.**
So the batches run *inside* one `conn.transaction()`.

**And this was not theoretical.** The loop was first typed **outside** the
`with` block. The symptom was lucky — `psycopg.InterfaceError: the cursor is
closed`. Had the cursor stayed open, every chunk would have committed
separately, atomicity would have been gone, and **nothing would have raised**.

> **Four spaces of indentation decided whether the write was atomic.** A
> correctness property with no error message attached needs a test, not care.

`INSERT_BATCH_SIZE = 96` matches `embed`'s `MAX_BATCH_SIZE` numerically and is
**derived independently**, from the same memory budget — `store/` cannot import
`embed/`, and the two limits answer different questions.


### How a vector crosses the wire

Four forms were tested and all four work, including a plain Python list and
scientific notation — which normalized vectors need. We use `str(list(vector))`:
stdlib only, no numpy, and it is what the `pgvector` package would have produced
anyway. **Reading back returns a `str`, not a list**, so search must parse if it
ever needs the vector itself — it should not.


### Testing: a new cost class, and a gap named rather than hidden

Database tests cost **no API quota** but need a live Postgres, so `--run-smoke`
is the wrong gate. They carry a `database` marker and **skip on a missing
`DATABASE_URL`**, and `.env` is loaded **inside the fixture only** — five
`tests/unit/embed/` files manipulate env vars, and a global `load_dotenv()` in
`conftest.py` would change what they see.

They run in their own `labpilot_test` **schema**, dropped at teardown, so real
data is never touched. **That sentence was FALSE when it was written, and it
took a week to notice — see
[the flaky suite](../../step1/vector-store.md#the-flaky-suite-and-the-three-causes-behind-it--2026-09-0405).**
The fixture connection is **autocommit**, because
otherwise one deliberate `CheckViolation` poisons the transaction and every
later test dies with *"current transaction is aborted"*. `conn.transaction()`
was verified to still begin and roll back under autocommit, so the atomicity
test is real and not decorative.

**One file was typed into `tests/unit/store/` and moved.** `unit/` means no
network and no database; a test hitting Supabase is not a unit test whatever it
covers.

> **The gap, stated rather than hidden: CI has no `DATABASE_URL`, so all ten
> database tests always skip there.** A test that never runs is close to a test
> that does not exist. Add the repository secret before slice 4 closes.


### The flaky suite, and the three causes behind it — 2026-09-04/05

*The user reported it plainly: **"every time I run the full test, one test
fails... after running 4 or 5 times all pass, without doing anything."** That is
the worst kind of suite — one that is not telling you the truth. Two independent
causes, both in the test fixture, neither in `store/`.*

**The instrument that found it: log `pg_backend_pid()` on every connection.**
12 separate client connections across 6 full runs all reported **one** backend,
`pid=833757`. Supabase puts a pooler (Supavisor) in front of Postgres and
recycles one server process, resetting session state between checkouts.

#### Cause 1 — session state is not a place to keep isolation

The fixture isolated itself with a runtime `set search_path to labpilot_test,
public`. Measured on the real project:

```
runtime SET     -> after RESET ALL: '"$user", public, extensions'   LOST
startup option  -> after RESET ALL: 'labpilot_test,public'          KEPT
```

A pooler reset throws a runtime `SET` away and **restores a startup option**.
So the fix is to send the search path as a libpq **startup parameter**
(`options=-c search_path=...`), which is part of establishing the session.

**And the loss was SILENT**, because `public.artifacts` and `public.chunks`
existed — left behind by an earlier session. When the path was lost, bare
`artifacts` resolved to the **real** schema. The proof was sitting in the
database: `public.chunks` held exactly `w1/0, w1/1, w1/2`, the three rows from
the test that had reported **0 rows**. The write went to `public`, the read to
`labpilot_test`.

Those stale tables were dropped, so a future loss fails loudly with *"relation
does not exist"* instead of writing to the real schema.

> **Isolation that lives in session state is isolation a pooler can revoke.**
> Put it in the connection's startup parameters, where a reset restores it
> rather than discarding it.

#### Cause 2 — a pooled connection is not a durable resource

With cause 1 fixed the suite still failed about 1 run in 10, but now **loudly**:

```
psycopg.OperationalError: server closed the connection unexpectedly
db = <psycopg.Connection [BAD] at 0x...>
```

The fixture was **module-scoped**, so it held one connection across a whole
module. When the pooler dropped it, every later test in that module inherited a
dead connection. Three changes:

| change | why |
|---|---|
| **pre-ping** — check the connection before handing it out, reopen if dead | reopening per test is also correct but costs **~2s each** on this link; the ping costs ~0.3s |
| **one retry** on the first statement of each test | the connection can die *between* the ping and the next statement |
| **`delete from artifacts`** per test, never `truncate` | truncate needs ACCESS EXCLUSIVE, conflicts with even a SELECT, and blocked on a pooled lock until the 2min `statement_timeout` — the folder went **28s -> 238s** |

**Measured after: 20 full runs, 0 failures**, and the folder is back to ~35s.

#### Cause 3 — one schema name shared by every run, found 2026-09-05

**The user reported the flake again after causes 1 and 2 were called fixed.**
That call was wrong: twenty green runs *in one terminal* proved nothing about
two runs at once, and the suite was still being run from the VS Code Testing
panel at the same time as the terminal.

The signature is unmistakable once seen — two statements on **one** connection
landing in different worlds:

```
insert into artifacts ('cas')   -> OK
insert into chunks    ('cas')   -> relation "chunks" does not exist
```

plus writes that read back empty, and `duplicate key (id)=(s1)`. Every run used
the **same hardcoded `labpilot_test`**, and every run began with
`drop schema ... cascade`. So run B deleted run A's tables mid-test, between
its `create schema` and its `create_schema(conn)`.

**Reproduced on demand**, which is what turned it from a ghost into a bug:

```
two concurrent pytest processes, shared schema name -> 2 failed / 4 failed
the same two, one schema per run                    -> 39 passed / 39 passed
three at once                                       -> all green, no leftovers
two FULL suites at once                             -> 544 passed, twice
```

The fix is one line: `labpilot_test_{pid}_{token_hex(3)}`, so no run can name,
or drop, another run's schema. Teardown removes only what it created.

> **"It passes on my machine, twenty times" is not evidence about
> concurrency.** Every one of those runs tested the same single-writer case.
> The bug lived in the case never exercised.

> **A shared mutable name is a shared mutable resource.** `labpilot_test` was a
> global variable with a `DROP` attached, and it read like a constant.

**This is the same defect CI was already protected from** — the workflow gives
each job its own container precisely so two pushes cannot fight over one
database. The reasoning was applied to CI and not to the machine it was written
on.

#### Two mutations, both verified

```
runtime SET instead of the startup option -> test_the_test_schema_survives_a_session_reset  (1 failed, 28 passed)
pre-ping always claims healthy            -> test_a_dropped_connection_is_reopened
search path never applied                 -> RuntimeError "Refusing to touch the real schema"
```

The third is a **refusal guard** in the fixture: if `current_schema()` is not
`labpilot_test` after setup, it raises instead of creating the tables somewhere
else. Without it the tests write to the real schema and still report green.

#### Three lessons

> **A flaky test is not a weak test — it is a test whose environment you have
> not modelled.** The pooler was invisible in every green run.

> **A wrong hypothesis costs nothing if you test it.** Two of mine died on
> contact: `create table if not exists` binding to `public` (it respects the
> target schema), and the pooler dropping `SET` between cursors (it does not —
> only a reset does). Both were disproved by one probe each.

> **Fixing a silent failure often reveals a second one.** Cause 2 was always
> there; it only became visible once cause 1 stopped hiding it behind wrong
> answers.


### Mutation results — 10 of 10 real

```
M1  schema: drop ON DELETE CASCADE       -> test_deleting_an_artifact_deletes_its_chunks
M2  schema: pin the column to vector(3)  -> test_one_vector_column_holds_two_different_widths
M3  schema: drop IF NOT EXISTS           -> test_applying_the_schema_again_keeps_the_data
M4  schema: drop the side CHECK          -> test_the_database_refuses_a_side_that_is_not_a_or_b
M5  connection: put the URL in the error -> test_our_error_never_repeats_the_url_we_were_given
M6  connection: drop `from exc`          -> test_a_driver_failure_..._keeps_the_cause
M7  contracts: delete the side guard     -> test_a_side_that_is_not_a_or_b_is_refused
M8  writer: drop the leading DELETE      -> test_writing_the_same_artifact_twice_replaces_it
M9  writer: loop outside the transaction -> test_a_failure_midway_leaves_nothing_behind
M10 writer: drop the width check         -> test_a_vector_of_the_wrong_width_is_refused
```

M5 printed the exact leak it prevents:

```
could not reach postgresql://postgres.abc:hunter2SECRET@host.example:5432/...
```

**But note what that test does and does not claim.** It pins that *we* never
repeat the URL. Whether **psycopg** leaks a password was measured separately and
live — it does not, on a bad password or a bad host — which is why no scrubbing
code exists. *Check the threat before writing the guard*, the same lesson
`zipfile` taught in slice 2.

M2 is the one that guards a **decision** rather than a behaviour: if anyone
later writes `v vector(1536)`, that test goes red and forces the conversation
about which embedder won, instead of the choice being made silently by an edit.


### One small defect the new dependency exposed

`test_every_package_labpilot_imports_is_pinned` split each requirement on `==`
and never learned about **extras**, so `psycopg[binary]==3.2.12` was stored
under a name the import `psycopg` could never match. `.split("[")[0]` fixes it,
and check C of the mutation run confirmed the looser parser did **not** make the
test blind — deleting the dependency still fails it.

> **Loosening a parser can quietly kill a test's ability to fail.** Always
> re-run the case the test exists to catch, not only the case you just allowed.


### What the first half deliberately did NOT do

- **No index.** Step 3, and it must not come before the exact baseline that
  scores it.
- **No search.** Step 2 of the order and the next task; `SearchHit` is
  deliberately absent from `contracts.py` until its consumer exists.
- **No wiring into `services.py`.** `write_artifact` is reachable only from
  tests — scaffolding with a scheduled consumer, exactly as `chunk_source` was
  after slice 2.
- **No connection pool.** `psycopg_pool` is a separate package; one connection
  per operation is right until something measures otherwise.

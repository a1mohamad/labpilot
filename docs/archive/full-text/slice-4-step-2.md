# Full text: Slice 4, step 2 — DONE 2026-09-05: exact search

[Docs home](../../README.md)

## Slice 4, step 2 — DONE 2026-09-05: exact search

*The baseline, and the **instrument** that will score HNSW in step 4. There is
no index and that is deliberate: exact search is the correct answer **by
definition**, so there is nothing else to grade an approximate index against.*
**544 passed, 28 skipped, 2 xfailed, ruff clean. 5 full runs, 0 failures.**

| module | added |
|---|---|
| `store/search.py` | `search(conn, artifact_id, query, *, model, limit)` |
| `store/contracts.py` | `SearchHit` — the hit plus its `score` |
| `store/errors.py` | `UnknownArtifact` |
| `store/defaults.py` | `SEARCH_LIMIT = 50` — retrieve wide, rerank to ~10 |


### `<=>` is DISTANCE, so `order by` takes no `desc`

Cosine distance: **smallest is nearest**. `score = 1 - distance` flips it back
to similarity for the reader. The two agree — the smallest distance *is* the
biggest score — so sorting either way returns the same rows.

**We sort the distance anyway, and the reason is step 3.** pgvector recognises
exactly one shape:

```sql
order by v <=> q            -- an index CAN serve this
order by 1 - (v <=> q) desc -- it CANNOT; silent full scan
```

Wrapping the distance in `1 - (...)` hides it from the planner. Same answers,
no error, no warning — and 5x slower at 2,000 rows already (measured
2026-08-28). **So `score` is a label that rides along, never a sort key.**


### The guard that matters: two embedding spaces do not compare

`search` takes `model: str` and refuses when it differs from the artifact's
`embedding_model`. Without it a codestral corpus searched with a Gemini query
returns confident nonsense and **raises nothing**. `store/` may not import
`embed/`, so the model arrives as a plain string — the layering rule doing its
job.

`UnknownArtifact` exists for the same reason: returning `()` for a corpus that
was never stored is indistinguishable from *"nothing matched"*.


### The `::vector` cast is NOT required — and I claimed it was

The comment in an earlier draft said the cast was load-bearing: the vector
crosses the wire as text, and unlike the writer there is no `vector` column to
infer from. **The mutation disproved it.** Removing both casts: **10 passed.**
psycopg3 sends the parameter as `unknown` and Postgres coerces it.

The casts stay as belt-and-braces — a driver that ever typed the parameter as
`text` would make `vector <=> text` fail to resolve — but the comment now says
so, and **no test pretends to pin it**.

> **A mutation that survives is not always a bad test. Sometimes it is a false
> claim in a comment.** The test suite was right; the explanation was wrong.


### Mutation results — 7 real, 1 survivor, 3 broken mutations

```
order by ... DESC                  -> 4 order-dependent tests    (nearest-first, scores, citation, limit)
score = raw distance               -> test_the_scores_fall_as_the_chunks_turn_away   ALONE
filter matches every artifact      -> test_only_the_named_artifact_is_searched       ALONE
model guard disabled               -> test_a_query_from_a_different_model_is_refused ALONE
missing artifact returns ()        -> test_an_unknown_artifact_is_refused...         ALONE
width check disabled               -> test_a_query_of_the_wrong_width_is_refused     ALONE
limit guard disabled               -> test_a_limit_that_returns_nothing...           ALONE
::vector removed                   -> NOTHING. The claim was wrong, not the test
```

**Three mutations were themselves broken, and each looked like a result.**
Deleting the `where` line left 4 parameters for 3 placeholders, so it failed on
a parameter-count error. Replacing it with `%s is not null` failed on
`IndeterminateDatatype`. And a guard mutation written with 8 spaces of
indentation where the code has 4 **never applied at all** — the anchor was not
found, the suite passed, and it read exactly like a surviving mutation.

> **Assert the anchor before trusting a mutation.** `s.replace(old, new)` on a
> string that is not there is a silent no-op, and a silent no-op is
> indistinguishable from a test that cannot fail.


### The fixture geometry is arithmetic, not a guess

Four chunks placed by hand against the query `[1, 0, 0]`:

| chunk | vector | distance | score |
|---|---|---|---|
| 0 | `[1, 0, 0]` | 0.0 | **1.0** |
| 1 | `[0.9, 0.436, 0]` | ~0.1 | ~0.9 |
| 2 | `[0, 1, 0]` | 1.0 | 0.0 |
| 3 | `[-1, 0, 0]` | 2.0 | **-1.0** |

The expected order is `0, 1, 2, 3` and a stray `desc` returns exactly
`3, 2, 1, 0`. **Nothing here is a magic number** — every value follows from the
angle, so the test says what it means.


### What step 2 deliberately did NOT do

- **No index.** Step 3, and it must not come before the baseline that scores it.
- **No hybrid keyword search.** Slice 5.
- **No caller.** `search` is reachable only from tests until slice 7 wires
  `api/services.py`, which is the only layer allowed to import both `ingest/`
  and `store/`.

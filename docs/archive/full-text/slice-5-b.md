# Full text: Slice 5 — DONE 2026-09-08

[Docs home](../../README.md)

## Slice 5 — DONE 2026-09-08

*The measuring was session 18's; this is the code. **595 passed, 28 skipped,
1 xfailed, ruff clean. 27 mutations, every one verified real.** Nothing calls
any of it — that IS "off by default": no flag, no setting, because a flag
nobody reads is dead configuration.*


### What shipped

| file | holds |
|---|---|
| `store/schema.sql` | one generated `tsvector` column + one GIN index |
| `store/keyword.py` | `keyword_search()` (ts_rank) and `bm25_search()` (ours) |
| `retrieval/fusion.py` | `weighted_rrf()` — pure, no database |
| `store/defaults.py` | `BM25_K1 = 1.2`, `BM25_B = 0.75` |

`store/` is now eight modules; `retrieval/` is the first **core** package to
gain something that outlives the throwaway selector.


### Probing the real database first found THREE defects, all silent

*The plan said to build the query the way the benchmark built it. That would
have shipped two crashes and a silent recall loss. **Every one was found by
handing the expression adversarial input before writing a line of product
code**, and none of them could ever have appeared in the measurement — its 62
queries are hand-written English sentences, while a real query is the user's
prompt and may contain anything.*

| input | what the benchmark's expression did |
|---|---|
| `api.github.com:443` | **CRASH** — one lexeme, and `to_tsquery` reads `:` as a weight marker → `SyntaxError` |
| `http://x.com/p?a=1&b=2` | **silent AND** — re-parses to `'1' & 'b'`, putting back the AND that scored 0 of 17 |
| `please` | **silent miss** — see below |

**The fix is two words, and each is load-bearing:**

```
to_tsquery('simple', array_to_string(array(
    select quote_literal(lexeme)
    from unnest(tsvector_to_array(to_tsvector('english', %s))) as lexeme
), ' | '))
```

**`quote_literal`** stops both crashes. A quoted lexeme is not re-read for
operators, so `:` and `&` inside a token are inert.

**`'simple'`, never `'english'`** — and this one was found while testing the
first fix. These lexemes are **already stemmed** by `to_tsvector('english',…)`.
Stemming them a second time can change them, and the changed lexeme then no
longer matches what is stored:

```
stored lexeme   english re-stem   simple re-stem
pleas           plea              pleas
```

```
to_tsvector('english','please read this') @@ to_tsquery('english','plea')   False
to_tsvector('english','please read this') @@ to_tsquery('simple','pleas')   True
```

Measured on 11 words, only `please` drifted — about 1 in 11, silent, and free
to avoid. The stored side stays `'english'`, because that is what the column
holds.

> **A query builder proven on your benchmark is proven on your benchmark.**
> The measurement's inputs were sentences someone wrote. Production input is
> whatever the user types. Probe the edge before promoting a script to a module.

**One edge deliberately left alone:** a URL token still re-parses into a
*phrase* (`<->`) inside its own term. It is not an AND across concepts, and the
stored side tokenizes identically, so it still matches. Removing it would mean
dropping `tsquery` entirely — which also drops the GIN index and makes
`ts_rank` impossible.


### What the keyword channel costs in storage, measured

Storage is what runs out first on this project, and nothing had priced a
column plus an index. Measured on **1,090 real chunks** of this repository, in
a scratch schema on the real project:

| | bytes | per chunk |
|---|---|---|
| text + header | 688,128 | 631 |
| **+ tsv column** | 679,936 | **624** |
| **+ GIN index** | 434,176 | **398** |
| **total** | 1,802,240 | **1,653** |

**Keyword search adds ~1,022 bytes per chunk — +162% on the text alone.** But
the text is not what dominates a row; the vector is:

```
1536-dim   8,831 -> 9,853 bytes/row  (+11.6%)   two 10k artifacts: 177MB -> 197MB
1024-dim   4,831 -> 5,853 bytes/row  (+21.2%)   two 10k artifacts:  97MB -> 117MB
```

**Affordable against the 500 MB free tier**, and worth re-checking at slice 8
alongside the exact-vs-HNSW decision, where the same 500 MB is the binding
constraint.

*A first run on 304 chunks reported 1,401 bytes/chunk. That was page rounding
on too small a table — 30 pages. **Re-measured at 1,090 before the number was
written down**, which is the rule this file already states about fixtures.*


### The tests, and what mutation testing found

**36 new tests. 27 mutations, all real; after two fixes every invariant fires
alone.**

| file | tests | cost |
|---|---|---|
| `tests/unit/retrieval/test_fusion.py` | 17 | free, every push |
| `tests/integration/test_store_keyword.py` | 15 | `database` marker |
| `tests/integration/test_store_schema.py` | +2 | `database` marker |
| `tests/unit/test_error_boundaries.py` | 2 | free, every push |

**No API test and no smoke test, deliberately.** No route reaches keyword
search, and it calls no provider — a test at either door would exercise nothing
and, at the smoke door, would spend quota to prove it.

#### Mutation testing found two of my own tests were wrong

**1. A fake test.** `test_..._when_scores_tie` fused `[3,1,2]` with `[3,1,2]` —
three *different* scores, so there was no tie at all. Removing the tie-break
changed nothing. The name promised the invariant and the fixture never built
it. **The same shape as `test_a_word_is_never_cut_in_half`**, which checked one
end of the thing its name claimed.

**2. A test hidden by a second filter.** Defeating the artifact filter inside
`_MATCHES` broke nothing, because `_HITS` filters by artifact as well. The
defect is real — foreign chunks get **scored and ranked**, pushing real answers
out of the `limit` — and the fixture hid it twice: no limit pressure, and both
artifacts numbered from 0, so a leak landed on an index that existed anyway.
Fixed by making the other artifact score **higher** and start at index 10.

> **A second guard downstream can make a broken guard upstream look fine.**
> Test the one you mean to test, with the downstream one unable to save it.


### The review pass — one guard added, one weakness recorded

**The predicted slice 7 bug now breaks the build instead of a request.**
`tests/unit/test_error_boundaries.py` reads every import and every `except` in
`labpilot/api/`, and fails when an adapter the API imports can raise something
nothing catches. Verified: adding `from labpilot.store import UnknownArtifact`
to `services.py` turns it red, alone.

It also found that this is **already true of `sources/`** — six error types
(`SourceTooLarge`, `UnsafeArchive`, …) that nothing in `api/` catches. Latent,
not live: `chunk_source` has no caller. They are listed by name in
`ALLOWED_TO_ESCAPE` with the reason, following the `OUTPUT_TOO_SMALL` pattern —
a deliberate gap is documented, an accidental one is red. A second test deletes
the excuse when the package stops being imported.

**A weakness in slice 4's own tests, found by a mutation.**
`test_store_search.py` numbers its chunks `0..3` — which are also valid **row
positions**. So vector search could return a position instead of a
`chunk_index` and every one of its tests would still pass. Proven: replacing
`select chunk_index` with `select row_number() - 1` leaves that whole file
green. The only thing that catches it is the new
`test_the_two_channels_rank_the_same_id_space_and_fuse`, whose indexes start at
**100** — and it fires **alone**.

> **A fixture numbered from zero cannot tell an id from an index.** Offset the
> ids in any test where the two could be confused.


### What slice 5 deliberately did NOT build

- **No caller.** Slice 7 wires it; slice 8 decides whether it stays.
- **No `avg_tokens` column.** Measure first — and the measurement above says
  the per-query aggregate is affordable at our size.
- **No `ts_rank_cd`.** It lost on every run of the sweep.
- **No flag.** Unreachable code is off; a setting nobody reads is not.


### Honest limits

- **`ts_rank` is shipped as the loser**, kept only so slice 8 can compare
  against it in product code rather than in a script. All nine safe fusion
  settings used BM25.
- **`bm25_search` costs 4–5 round trips** against `keyword_search`'s one,
  because Postgres cannot do IDF. Unmeasured against a real corpus; if it
  proves slow, `ts_rank` is the fallback that already exists.
- **`_CORPUS_CACHE` is unbounded.** Each entry is tiny (two numbers keyed by id
  and timestamp), so 10,000 artifacts is a few MB — recorded, not fixed.
- **The generated column is computed on every insert**, so ingest is slightly
  slower. Not measured.

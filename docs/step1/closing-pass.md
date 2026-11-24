# Step 1: the closing pass

[Docs home](../README.md)

## THE STEP 1 CLOSING PASS — 2026-09-19, and it asked one question

*Run across the whole RAG system rather than across the newest code, asking
only the standing question: **which real failure is still unprotected?** Four
answers, each mutation-verified, and one of the four was DELETED for being a
second copy of a guard that already existed.*
**871 passed, 4 skipped, 0 xfailed, ruff clean.**

### 1. THE WEEKLY RUN WAS WATCHING A BUILDING WE HAD MOVED OUT OF

`tests/smoke/test_pipeline_answers.py` drove `chunk_file` -> `select` ->
`build_prompt` -> `LLMClient`. **Slice 7 replaced that pipeline.** So the store,
the ask ladder, the assembled rerank chain and both doors — four whole layers —
had **no live coverage at all**, and telling us a free provider died in the
night is the entire reason smoke exists.

`tests/smoke/test_ask_answers.py` now drives `ingest_artifact` -> `ask()`
against a real corpus in Postgres, on the SEARCH branch (the committed pair is
28,246 tokens against a 26,000 budget, so it cannot stuff). It asserts which
path ran rather than assuming it, and it resolves the model's own citations
back to lines on disk.

**And the baseline was cut from four generation calls to one.** FULL, CORE and
CORE-stuffed are templates this file already calls *"frozen baselines we no
longer use"*; at 119-497s per report that was ~20 minutes a week proving nothing
about what ships. `REPORT` stuffed stays, because stuffing removes retrieval as
a variable and keeps its score comparable with every saved baseline.

### 2. NOTHING CHECKED THAT THE PAGE READS FIELDS WE SEND

The one drift with **two** incidents behind it. Slice 7 changed `/compare` to
take ids and `web/app.js` kept posting files — the page was broken for a week
with a green suite. And `embedding_minutes` -> `ingest_minutes` touched
contracts, schemas, the router and `app.js`; missing the last would have
rendered `~undefined min to ingest` with no error anywhere.

Neither is catchable at the API boundary: Pydantic renames happily, every
`api/` test updates with it, and the only consumer that disagrees is written in
another language and imported by nothing.
`tests/unit/test_frontend_contract.py` reads `app.js` as text and checks the
names against the models that produce them — the same move `test_packaging.py`
makes for `requirements.txt`.

> **Mutation: renaming `finish_reason` across `schemas.py` AND
> `routers/compare.py` — a complete, correct server-side rename that misses
> `app.js` — fires it ALONE out of 880 tests.**

*A first draft reported `payload.error` as drift. That was the test being
wrong: `app.js` parses the JSON once and branches on `response.ok`, so the same
name holds either the success model or the error envelope.*

### 3. THE SKIP GATE WAS WIRED AND NOTHING PROVED IT

`SKIP_MARGIN` is `None`, so `should_rerank` always answers True and **deleting
the call from `_best` changes no behaviour whatever**. That is precisely the
condition under which a component quietly stops being connected, and this
project has shipped that failure twice:

```
slice 6   the rerank chain BUILT AND NEVER BOUND - the ask path used only the
          cross-encoders and never the four tiers that beat them
slice 8   score fusion DECIDED AND NEVER APPLIED for three sessions, while
          RESULTS.md claimed "it now has a caller"
```

Both were invisible because the unwired component still returned something
plausible. A test now forces the gate to answer NO and asserts no tier is
asked; deleting the call fires it alone.

> **A component that is tested in isolation and never asserted to be CALLED is
> the most repeated defect in this project.** Three now have a wiring test:
> fusion, the rerank chain, and the gate.

### 4. FUSION WAS PROVEN IN HALVES, NEVER AT THE SEAM

`test_store_keyword.py` runs `bm25_search` against a real database.
`test_fusion_is_on.py` runs the wiring with both channels stubbed. **Nothing
ran the real query builder against really-ingested rows** — so a keyword
channel returning nothing on real data would take `_fused`'s
`if not sparse: return dense` branch, make every answer vector-alone, leave
both files green, and quietly undo a decision measured over 20 corpora and 423
queries.

Not hypothetical: slice 5 probed this same builder and found **three** silent
defects, two of which return zero rows rather than raising.

> **Mutation: turning the OR back into an AND — the defect that scored 0 of 17
> — fires the new test ALONE.**

#### THE BOUND THIS TEST DISCOVERED, and it is new knowledge about what we ship

The first fixture buried the answer at the **bottom** on cosine and the test
failed. The keyword channel was healthy the whole time — BM25 returned exactly
the planted chunk, score 6.39. **The fixture was impossible:**

```
min-max puts the worst dense hit at 0.0 and the best at 1.0
alpha = 0.85 caps the keyword channel's whole contribution at 0.15
```

$$
0.85 \times 0.0 + 0.15 \times 1.0 = 0.15
\quad<\quad
0.85 \times 1.0 + 0.15 \times 0.0 = 0.85
$$

> **A chunk ranked LAST by cosine can never be lifted past one ranked FIRST, at
> ANY keyword score. Score fusion rescues the MIDDLE, never the floor.**

And that matches the measurement it was built for: `D2` sits at place **46 of
82** on codestral — mid-pack — not at place 82. Verified numerically: a graded
21-chunk corpus with the answer at place 12 fuses to place **9**; the same
answer at last place stays last.

### THE FOURTH CANDIDATE WAS DELETED

*"the fused window never exceeds `SEARCH_LIMIT`"* was written, and mutating the
cut fired `test_the_fused_window_never_exceeds_what_search_returns` in `api/`
and **not** the new one. **A new corpus is not a new invariant** — re-asserting
a rule you already test, on different data, buys a number and no protection.

### One refactor this needed

`tests/integration/conftest.py` moved **whole and unchanged** to
`tests/conftest.py`. The database fixtures sat in `integration/` while only that
folder needed a live Postgres; `smoke/` needs one now, because the shipped ask
path reads its corpus from the database and a smoke test that cannot store an
artifact cannot exercise what we ship. pytest resolves fixtures upward, so
integration kept working by inheritance — verified, 94 tests, before anything
else was written. `load_dotenv` stays **inside** the fixture, because five
`tests/unit/embed/` files manipulate env vars and a module-level load would
change what they see.


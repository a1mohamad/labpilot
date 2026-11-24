# Full text: Step 1 — the plan, recorded 2026-08-20

[Docs home](../../README.md)

## Step 1 — the plan, recorded 2026-08-20

*Decided in session 12, before any Step 1 code was written. Step 0 was five
slices. **Step 1 is nine** — it was planned as eight, and `1b` was inserted on
2026-08-20 once slice 1 showed we had never called a second platform.*

Two of the nine exist only because the input edge is wider than Step 0 ever
admitted, and `1b` exists because slice 1 shipped on a single platform.


### Why Step 1 cannot be measured on today's fixture

The sample pair is ~20,400 tokens, the lean instructions ~2,000, and
`PROMPT_BUDGET` is 26,000. **It fits.** That is why every measurement since
slice 4 says *stuffed*, and it means retrieval currently changes nothing at all.

> **A retrieval layer cannot be proven on a corpus that fits.** Reading a
> repository is therefore not an extra feature — it is what makes Step 1
> measurable in the first place.


### The nine slices

| # | Slice | What it must prove | Teaching load |
|---|---|---|---|
| 1 | **Embed one chunk, and settle the model** | a vector comes back, and `codestral-embed` vs `mistral-embed` is decided **by measurement** | **heavy** — embeddings, cosine similarity, normalization |
| **1b** | **More embedders** | Google and one open-weights model scored on `queries.json`; real rate limits recorded; `base.py` earned | medium |
| 2 | ~~**Read a repository**~~ ✅ **DONE 2026-08-28** | folder, zip and git URL all become chunks, streamed | light — engineering already known |
| 3 | **Read a document** | PDF, Word, notebook and other languages get real boundaries | medium |
| 4 | **pgvector** | ~2,000 chunks go in and come back out unchanged | **heavy** — vector databases, ANN indexes |
| 5 | **Cosine + keyword search** | a query returns the right chunks, the `side` filter works, and BM25 catches identifier queries like `D2` | medium |
| 6 | ~~**Reranking**~~ ✅ **DONE 2026-09-11** | built, measured across NINE configurations, and **NOT switched on**: `bge-reranker-base` made retrieval WORSE on all four runs, and the best gate is the one that never reranks | **heavy** — bi-encoder vs cross-encoder |
| 7 | **The new selector** | `select()` is deleted; A fills before B; the outline lists **files** | light |
| 8 | **Measure** | the same fixture, then a **second** fixture in another domain — **the embedder order, the reranker order, AND exact-vs-HNSW are all settled here, on real numbers** | none — it is scoring |

**The ordering rule is unchanged from Step 0: only one thing may be wrong at a
time.** Three placements carry real weight:

- **Slice 1 needs no database.** 96 chunks, a few hundred embed calls, cosine in
  plain Python. That settles the **dimension** (1536 vs 1024) *before* any table
  exists. A schema is expensive to change once rows exist; an in-memory test is
  free.
- **Slice 2 before slice 4**, so the database is filled with a real corpus rather
  than with 96 chunks.
- **Slice 3 before slice 4**, for the permanence reason below.

**Slices 2 and 3 are the same idea — *turn whatever arrived into text* — and are
still split**, because one is **many files of one kind** and the other is **one
file of many kinds**. Different failures, so different slices.


### What the input edge actually accepts today — read from the code 2026-08-20

| Input | What happens now | Good? |
|---|---|---|
| `.md`, `.markdown` | header splitter | ✅ |
| `.py` | AST splitter — functions and classes | ✅ |
| `.txt` | recursive splitter | ✅ acceptable for prose |
| `.pdf`, `.docx` | **422 — "is not UTF-8 text"** | refused, and that is honest |
| **`.ipynb`** | **accepted, then cut blindly as raw JSON** | ❌ **silent downgrade** |
| `.js`, `.cpp`, `.java`, `.r` … | accepted, cut blindly | ❌ silent downgrade |

`SPLITTERS` in `labpilot/ingest/chunker.py` holds exactly three entries.
Everything else falls to `split_recursive`.

**Two defects this exposed, both real:**

1. **The notebook case breaks this file's own rule.** A `.ipynb` is JSON, so it
   decodes as UTF-8, passes the upload gate, and is then chunked as text — giving
   chunks full of `"cell_type": "code"` and escaped newlines. Slice 5 wrote the
   rule it violates: *"refuse the input you cannot handle well — a silent
   downgrade is worse than a rejection, because nobody ever learns it happened."*
   And the notebook splitter (*split on cells*) was **designed in the chunking
   section and never built**.
2. **`MAX_UPLOAD_BYTES` is 1,000,000.** A real paper PDF is usually 1–5MB, so the
   limit alone would refuse most papers. It must rise in slice 3;
   `MAX_REQUEST_BODY_BYTES` follows it automatically.

> **A designed-but-unbuilt splitter is invisible, because the fallback always
> answers.** The same shape as *"recording a limit is not enforcing it"*.


### Loaders and splitters are two different jobs

| Job | Question it answers | Layer | Where it lives |
|---|---|---|---|
| **Source** | "give me the **files**" — folder, zip, git URL | **adapter** | `labpilot/sources/` (slice 2) |
| **Loader** | "give me **text** from these bytes" | core | **`labpilot/ingest/`, a `LOADERS` dict** (slice 3) |
| **Splitter** | "give me good **boundaries** in this text" | core | `labpilot/ingest/`, the `SPLITTERS` dict |

PDF, Word and notebooks need the last two. A repository needs only the first.
Keeping the two **jobs** apart means one PDF loader plus one prose splitter —
never a PDF-shaped chunker.

**`sources/` is a top-level package, not a subpackage of `ingest/`.** It runs
`git clone`, extracts archives and walks the filesystem — it talks to the
outside world, so it is an **adapter** and belongs beside `llm/` and `embed/`.
Putting a subprocess call inside a pure-logic package is exactly what
`test_architecture.py` exists to prevent.

#### Loaders live INSIDE `ingest/` — corrected 2026-08-28

*An earlier draft of this section planned a separate `labpilot/loaders/`
package. **The user rejected it and was right.** The correction is recorded
here because the reasoning generalises.*

**The layer argument does not apply.** It correctly separates `sources/`
(adapter) from `ingest/` (core). But `loaders/` would be **core too** — the same
layer as `ingest/` — so the rule that decides the `sources/` question decides
nothing here. A rule reused outside the case it was made for is not evidence.

**And this file's own layout rule settles it the other way:**

> *"Two modules always edited together — they are one module."*

Every new format touches both jobs at once. There is no `.pdf` loader without a
`.pdf` splitter decision, and this file already states the pairing as a rule:
*add each new suffix to `READABLE_SUFFIXES` **and** `SPLITTERS` together.* It is
already true of the code, too — `chunk_file` reads and then splits in one
function, so the loader is simply the half that `path.read_text()` occupies now.

**The shape, which keeps the distinction and drops the folder:**

```
labpilot/ingest/
    chunker.py      LOADERS dict  +  SPLITTERS dict, side by side
    _notebook.py    load_notebook()  +  split_notebook()
    _pdf.py         load_pdf()
    _markdown.py    _python.py    _recursive.py   (existing)
```

**Two dicts, one per job, in one package.** Loading and splitting stay separate
*jobs* — a loader may fail in ways a splitter cannot, and PDF extraction is
lossy where text splitting is not — but they stop being separate *folders*.

> **A folder is for things that change apart. Two jobs that always change
> together belong in one package, however different the jobs are.**

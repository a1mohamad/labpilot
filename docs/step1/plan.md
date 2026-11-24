# Step 1: the plan

[Docs home](../README.md)

## Step 1 — the plan, recorded 2026-08-20

*Decided in session 12 before any Step 1 code. Step 0 was five slices; **Step 1 was nine** (planned as eight, and `1b`
was inserted on 2026-08-20 once slice 1 showed we had never called a second platform). **ALL NINE ARE DONE
(closed 2026-09-19).***

### Why Step 1 cannot be measured on today's fixture

The sample pair is ~20,400 tokens, the lean instructions ~2,000 and `PROMPT_BUDGET` 26,000: **it fits**, so every
measurement since slice 4 says *stuffed* and retrieval changes nothing. **A retrieval layer cannot be proven on a corpus
that fits.** Reading a repository is therefore not an extra feature; it is what makes Step 1 measurable.

### The nine slices

| # | Slice | What it had to prove |
|---|---|---|
| 1 | Embed one chunk, settle the model | a vector comes back; `codestral-embed` vs `mistral-embed` decided **by measurement** |
| **1b** | More embedders | Google and an open-weights model scored on `queries.json`; real rate limits; `base.py` earned |
| 2 | Read a repository (**DONE 2026-08-28**) | folder, zip and git URL all become chunks, streamed |
| 3 | Read a document | PDF, Word, notebook and other languages get real boundaries |
| 4 | pgvector | ~2,000 chunks go in and come back unchanged |
| 5 | Cosine + keyword search | the `side` filter works and BM25 catches identifier queries like `D2` |
| 6 | Reranking (**DONE 2026-09-11**) | built and measured across nine configurations |
| 7 | The new selector | `select()` deleted; the outline lists **files**; (A-before-B was later overturned) |
| 8 | Measure | a second fixture in another domain; embedder order, reranker order and exact-vs-HNSW settled on real numbers |

**The ordering rule is unchanged from Step 0: only one thing may be wrong at a time.** Three placements carried
weight: **slice 1 needs no database** (96 chunks, cosine in plain Python, settles the dimension before any table exists —
a schema is expensive to change once rows exist); **slice 2 before slice 4** (the database is filled with a real corpus);
**slice 3 before slice 4** (chunk boundaries are permanent: a corpus embedded with bad boundaries must be re-chunked AND
re-embedded). Slices 2 and 3 are both "turn whatever arrived into text" but are split because one is *many files of one
kind* and the other *one file of many kinds*.

### What the input edge actually accepts today — read from the code 2026-08-20

At that date only `.md`, `.py` and `.txt` had real splitters; `.pdf` and `.docx` were refused with a 422 ("not UTF-8"),
which is honest; but **`.ipynb` and every other language were accepted and then cut blindly** — a silent downgrade that
broke this file's own rule (*refuse what you cannot handle well*). Two defects followed: the notebook splitter (*split on
cells*) had been designed and **never built**, and `MAX_UPLOAD_BYTES` (1,000,000) would refuse most real papers (1-5MB).
**A designed-but-unbuilt splitter is invisible, because the fallback always answers.**

### Loaders and splitters are two different jobs

A **source** ("give me the files": folder, zip, git URL) is an **adapter** in `labpilot/sources/` — it runs `git clone`,
extracts archives and walks the filesystem, so it belongs beside `llm/` and `embed/`, not inside pure-logic `ingest/`
(`test_architecture.py` exists to stop a subprocess call inside a core package). A **loader** ("give me text from these
bytes") and a **splitter** ("give me good boundaries in this text") are core and live in `labpilot/ingest/` as two dicts,
`LOADERS` and `SPLITTERS`. One PDF loader plus one prose splitter, never a PDF-shaped chunker.

#### Loaders live INSIDE `ingest/` — corrected 2026-08-28

An early draft planned a separate `labpilot/loaders/` package; **the user rejected it and was right.** The layer argument
(adapter vs core) does not apply, because `loaders/` would be core like `ingest/`, and this file's layout rule settles it:
*two modules always edited together are one module* — every new format touches both jobs. **A folder is for things that
change apart; two jobs that always change together belong in one package, however different the jobs are.**

### Cost per slice — this is what sets the pace

Generation quota spent: slices 1-4 none; slice 5 almost none (a query embed is ~20 tokens); slice 6 careful (Cohere is 1,000 per **month**, shared with embed); slice 7
a few; slice 8 the expensive one (full reports, and Flash models give 20 per day).

### Slice 8 decides the embedder AND the reranker — recorded 2026-08-28

> **It later decided a third thing: exact vs HNSW** (added 2026-09-05, see [slice 8's job grew](vector-store.md#slice-8s-job-grew--three-measurements-not-one)). All three were then settled: see
> [SLICE 8 — MEASURED](measurements.md#slice-8--measured-2026-09-16-step-1-is-complete) and `docs/slice8v3/DECISIONS.md`.

*Written at the user's request before the second fixture existed, so the rule could not be bent after the numbers arrived.* Every embedder number then came from **17 hand-written
queries over one Python file** — enough to pick a **default**, not a **policy**. Slice 8 needed: a new query set (~50+, several projects), several real repositories in more than one
language, the same 5 embedders **plus `gemini-embedding-2`**, and **all four rerankers plus the skip case** (the reranker order had never been measured: chain 3 was ordered by
*quota shape*, a good tie-breaker and no evidence they rank alike).

**Decision rules, fixed so a later number cannot bend them:** (1) **rank the embedder on recall@10, not @5** (the pipeline retrieves 50 and reranks to 10; reranking fixes ordering, it
can never recover a chunk retrieval did not return); (2) **a model that cannot be indexed is not a candidate**, whatever it scores (the pgvector 2000-dimension ceiling is a hard
gate); (3) **rank by the resource that runs out**, not only by the score; (4) **a query must never contain the identifier it is looking for** (or the test measures string
matching and everything scores ~100%); (5) **score with the answer key, never write the queries from it** (scoring is not leakage; adding a target because a model missed it is).
**Cohere is a backup for embedding — a decision, not a finding** *(the user, 2026-08-28)*: `embed-v4.0` wins MRR and ties perfect recall@10 and still must not hold a corpus (its
1,000 calls/month is one bucket shared with rerank, and Cohere is the reranker primary). The `MIGRATION` order was not rewritten on one 17-query fixture: Google's *storage*
question belonged to slice 4, its *ingest speed* to the routing rule, its *ranking* to slice 8 — **three questions, three slices; collapsing them is how a default becomes a
policy without anyone deciding it.**

### A parallel track, not a slice

Both are data, not code, and block nothing: (1) **the second sample pair** (a different domain and language; it must exist **before slice 8** or Step 1 ends without knowing
whether the system is quora-shaped — built as `requests_http` and `golang_geo`); (2) **the impact column in `EXPECTED.md`**, owed from Step 0, costs no requests.

### Explicitly not Step 1

Claim extraction, the planner, per-capability query sources, the correspondence gate, LangGraph, MCP, web search: **all Step 2.** Keeping them out is what lets Step 1 finish.

### Time estimate, honestly

Step 0 took **eleven sessions for five slices**; Step 1 had nine, three with heavy teaching (the first of the four gaps, so go **slower**). Expected 10 to 14 sessions; eight was the
*shape*, not a promise (Step 0 stayed five slices but each grew larger than planned).

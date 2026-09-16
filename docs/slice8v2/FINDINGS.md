# Slice 8, second run — findings log

Written as they happen, with the evidence beside each one. A finding with no
run behind it is a guess and says so.

---

## G0 — the instrument is sound (control)

Before anything new, the three recorded corpora were re-scored through the
**rebuilt, data-driven loader**:

```
quora    / codestral   r@1 0.412  r@5 0.941  r@10 0.941  r@50 1.000  MRR 0.608
requests / codestral                                                  MRR 0.646
geo      / codestral                                                  MRR 0.526
```

Every number matches what was recorded on 2026-09-07 and 2026-09-16 to three
decimals, so a disagreement later is a finding and not a drifted scorer.

**The embedding cache was validated rather than trusted.** Chunk counts match
the current chunking on all three corpora, and re-embedding three real chunks
agrees with the cached vectors to `|1 - cos| = 3.0e-10`. Reusing paid-for
vectors is therefore evidence-based, not convenience.

---

## G1 — our own exclusion patterns did not exclude, and a corpus was 2x too big

**Status: fixed, and it had already corrupted a fixture.**

`scripts/corpora.py` filtered files with `fnmatch`, which translates `**` to
`.*` — so `**/*_test.go` **requires a slash** and silently keeps every test
file sitting at the top of a repository.

```
fnmatch("completions_test.go", "**/*_test.go")   ->  False    <- kept
fnmatch("s2/cellid_test.go",   "**/*_test.go")   ->  True     <- excluded
```

Measured consequence on `cobra`:

```
before   408 chunks, 30 files   INCLUDING its test suite
after    193 chunks, 19 files
```

`websocket` went 167 -> 78 the same way. **`geo` was unaffected** — every one
of its files lives in a subdirectory, so every path had a slash. That is
exactly how a bug like this survives its first corpus and is found by its
fourth.

It was not caught by reading the code. It was caught because the drafter wrote
questions about `completions_test.go`, and a test file in a retrieval corpus
is visible in a way a missing exclusion is not.

`PurePosixPath.full_match` has the semantics the pattern implies, and is what
ships now.

> **A glob library that accepts `**` is not a library that implements `**`.**
> Check an exclusion against a path at the TOP of the tree, not only a nested
> one.

---

## G2 — `split_recursive` packs to the cap, and it is 2x the AST splitter

**Measured across eight corpora**, all through the real chunker:

| corpus | language | splitter | chunks | mean tokens |
|---|---|---|---|---|
| quora | Python | AST | 82 | 217 |
| requests | Python | AST | 335 | 244 |
| notebooks | Python + MD | notebook cells | 382 | 235 |
| docs | Markdown | headers | 463 | 293 |
| **cobra** | **Go** | **recursive** | 193 | **481** |
| **websocket** | **Go** | **recursive** | 78 | **466** |
| **log** | **Rust** | **recursive** | 146 | **477** |
| **jq** | **C** | **recursive** | 693 | **430** |
| **gson** | **Java** | **recursive** | 750 | **458** |
| **zod** | **TypeScript** | **recursive** | 1,160 | **468** |
| **papers** | **PDF** | **page** | 404 | **430** |
| **docx** | **Word** | **recursive** | 85 | **453** |

The first run of slice 8 saw this on ONE Go corpus and read it as a property
of Go. It is not: it is a property of **having no AST splitter**. Every
language without one lands at 430-481 tokens, because `split_recursive` fills
to `MAX_CHARS` and stops, while an AST splitter stops at a function.

Two consequences, and both are measured elsewhere in this run:

- **A rerank tier's usable window is set by chunk SIZE**, so a tier that
  serves 50 Python chunks can refuse 30 Java ones.
- **Python is the unrepresentative case.** Every retrieval number this project
  recorded before this run came from a corpus with the small-chunk splitter.

---

## G3 — a PDF anchor cannot be matched on exact text

**Status: fixed. Found while building the fixture, not while scoring.**

Ground truth is produced by deterministic quoting: the drafter copies one line
out of the chunk, and we resolve that line to a line NUMBER. Matching on the
stripped line works for code and fails for PDF:

```
papers   23 of 36 drafts DROPPED on "anchor not in chunk"
log       1 of 36
```

The anchors were really there. PDF extraction carries the spacing of the
**page**, not of a sentence — runs of spaces inside and between words — and a
model copying such a line quietly collapses them. Normalising whitespace on
both sides fixes it and changes nothing about what the ground truth means.

> **A format's text is not its content.** The same matcher is exact on code,
> lossy on prose extracted from a page, and nothing raises either way.

---

## G4 — Mistral's `backend_out_of_capacity` is a wait, not a refusal

Two corpora died mid-embed on the first warm-up pass:

```
HTTP 429 code 3505  "Not enough capacity available for this request,
                     please retry later."  type: backend_out_of_capacity
```

`embed_batches` only halves and re-sends on a refusal that names **tokens**;
this one names capacity, so it raised and the corpus was lost. The five-way
rule applies to embedding as much as to generation — a 429 that clears in
seconds is a busy tier, not a spent pool — so the warmer now waits it out.

This is the same shape as F1 from the first run one level down: a refusal was
classified by the wrong feature of its message.

---

## G5 — a real Word document is larger than our own upload limit

`genai_intro.docx`, an ordinary Word report with images, is **12.3 MB**
against `MAX_UPLOAD_BYTES` and `MAX_FILE_BYTES` of **5 MB**. It loads fine
through `load_docx` — the guard that matters for a `.docx` is
`MAX_DOCX_XML_BYTES`, and its uncompressed XML is well under that — so the
refusal would come from the door, not from the loader.

So the door's limit, chosen for PDFs in slice 3, is **too small for the Word
documents people actually have**. Recorded, not fixed: moving it is a product
decision that also moves `MAX_REQUEST_BODY_BYTES`.

---

## G6 — the drafter chooses categories badly, and balance has to be selected

Left to choose freely, the drafter's first `cobra` run came back:

```
behaviour 11 · error 4 · structure 3 · constant 2 · api 0
```

Every routing finding in this project is a per-category comparison, and a
category with two queries cannot support one. Forcing a category per extract
is worse — a chunk with no constant in it would get an invented question about
a constant — so the pipeline **over-drafts 1.8x and selects for balance**.

It helps and it does not cure: a corpus whose pool is genuinely lopsided stays
lopsided (`gson` has one `api` question because only one was drafted). The
per-category claims in this run are therefore made on the POOLED count across
twelve corpora, never on one corpus's five.

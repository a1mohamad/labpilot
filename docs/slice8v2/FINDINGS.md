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

---

## G7 — EXACT SEARCH STANDS, and the crossover is ~700 rows, not ~1,000

**Measured 2026-09-16 on the REAL Supabase instance, twelve artifacts, real
embedded questions, every plan asserted with `EXPLAIN ANALYZE`.** The 2026-09-05
decision named exactly one condition that could overturn it — TIME on real
artifacts — and this is that measurement, on twelve sizes instead of three.

| rows | exact ms | hnsw ef40 | speedup | recall@10 | plan |
|---|---|---|---|---|---|
| 18 | 0.25 | 0.23 | 1.1x | 1.000 | **index NOT used** |
| 78 | 0.71 | 0.78 | 0.9x | 1.000 | **index NOT used** |
| 82 | 0.73 | 0.81 | 0.9x | 1.000 | **index NOT used** |
| 85 | 0.81 | 0.83 | 1.0x | 1.000 | **index NOT used** |
| 146 | 1.31 | 1.40 | 0.9x | 1.000 | **index NOT used** |
| 193 | 1.67 | 1.79 | 0.9x | 1.000 | **index NOT used** |
| 335 | 2.83 | 3.07 | 0.9x | 1.000 | **index NOT used** |
| 382 | 3.05 | 3.33 | 0.9x | 1.000 | **index NOT used** |
| 404 | 3.31 | 3.56 | 0.9x | 1.000 | **index NOT used** |
| 463 | 3.86 | 4.16 | 0.9x | 1.000 | **index NOT used** |
| **693** | 5.54 | **0.93** | **6.0x** | **0.990** | **INDEX** |
| **729** | 5.88 | **1.02** | **5.8x** | **0.990** | **INDEX** |
| **750** | 5.98 | **0.99** | **6.0x** | **1.000** | **INDEX** |
| **1,160** | 9.34 | **1.08** | **8.6x** | **0.870** | **INDEX** |
| **1,387** | 12.25 | **1.25** | **9.8x** | **0.940** | **INDEX** |

### Four things, and three of them are new

**1. Exact search is LINEAR and tiny.** 8.8 microseconds per row, straight
through fifteen sizes: `0.25 ms` at 18 rows, `12.25 ms` at 1,387. A
10,000-chunk artifact extrapolates to about **88 ms**.

**2. The crossover is ~700 rows.** The first run saw the index refused at 335
and 729 and used at 1,387, and read that as "below ~1,000 rows Postgres
refuses the index". With twelve sizes the line is visible and it is lower: the
planner refuses at 463 and uses it at **693**. That is inside the range this
project actually targets, which the old reading put outside it.

**3. Recall does not degrade smoothly - it degrades WITH SIZE, and by a lot.**

```
693    0.990        1,160   0.870      <- 13% of the answers lost
729    0.990        1,387   0.940
750    1.000
```

The only setting the planner will choose is `ef_search = 40`, and that is
where the loss is. **At `ef_search = 100` the planner stops using the index on
every single artifact**, so "raise ef_search to buy the recall back" is not
available: it buys the recall back by not using the index at all. The first
run found this tension at one size and called it new; it holds at every size
above the crossover.

**4. The index is 43% of total storage** - 59 MB of 136 MB for ~5,400 rows -
on a 500 MB free tier that must hold two artifacts per comparison.

### The decision

**Exact search ships, and the question is closed rather than deferred.**

The trade at a real artifact size is: save about **11 ms** of an answer that
takes **90-250 seconds**, and pay **6-13% of recall** for it. Retrieval is
already 4-7% of the wall clock and the database is 0.01% of it. We are not
short of database time.

> **An index is a trade, never a saving: spend storage and recall, buy time.
> If you are not short of time, you are paying for nothing.**

**Revisit at ~20,000 chunks in one artifact**, where exact extrapolates past
160 ms and the free tier's RAM cliff starts to matter. Nothing below that
moves it, and this run covers everything below it.

---

## G8 — FUSION RAISES THE CEILING AND DAMAGES THE ORDER, and no setting is safe on all thirteen

**63 wRRF settings x 13 corpora, measured 2026-09-16.** Free: no provider is
called, the sweep is arithmetic over cached vectors and Postgres's own lexemes.

### The headline, and it overturns both earlier readings

```
slice 5   "NOT ONE fusion setting improved recall@50 on any run"
slice 8v1 "EVERY one of 30+ wRRF settings improved r@50"
this run   4 of 13 corpora improve. 9 cannot: they are already at 1.000
           or fusion does not move them.
```

Both earlier statements were true **of the corpora they were measured on**.
Slice 5 had two saturated Python corpora and nothing to win; slice 8's first
run had one unsaturated corpus and read a universal law off it.

**Where fusion helps, it helps only where there is room:**

| corpus | vector r@50 | best r@50 | gain |
|---|---|---|---|
| geo | 0.867 | 0.956 | **+0.089** |
| gson | 0.923 | 1.000 | **+0.077** |
| jq | 0.900 | 0.950 | **+0.050** |
| papers | 0.950 | 1.000 | **+0.050** |
| the other nine | 0.950-1.000 | unchanged | **+0.000** |

### The mechanism, and this is the part worth keeping

**Fusion buys `r@50` and pays for it in `MRR`.** Every one of the twelve
best-by-`r@50` settings has a NEGATIVE mean MRR delta:

```
k=90 w=0.5    r@50 +0.0204   MRR -0.0573
k=30 w=0.3    r@50 +0.0187   MRR -0.0053   <- the least damaging
k=45 w=0.3    r@50 +0.0187   MRR -0.0166
```

and every one of the best-by-`MRR` settings gives up most of the `r@50` gain
and still hurts MRR somewhere:

```
k=5  w=0.3    MRR +0.0112, but WORSE on 5 of 13 corpora, worst -0.006
k=5  w=0.5    MRR +0.0092, worst -0.057
```

That is what a second, noisier channel fused BY RANK should do: it widens the
net, and it lets a keyword hit outrank a better semantic one.

### The rule this run can defend - CORRECTED

A first reading of this grid said "not one of 63 settings is never-worse on
both metrics, zero". **That used a zero tolerance and it is misleading.** On a
20-query corpus one query moving from rank 1 to rank 2 changes MRR by 0.025,
so a loss of 0.006 is a fraction of a single query and is not a loss at all.

With a tolerance that matches what the fixture can resolve:

```
never worse by more than 0.000   ->  0 settings
never worse by more than 0.005   ->  4 settings
never worse by more than 0.010   ->  7 settings
```

**So the shape slice 5 reported does survive, and the user's memory of it was
right.** What changes is WHICH setting, and by how much:

| | `k=5 w=0.15` (shipped) | **`k=5 w=0.3`** | `k=30 w=0.3` |
|---|---|---|---|
| mean `r@50` | +0.0115 | **+0.0136** | **+0.0187** |
| worst `r@50` on 13 | 0.000 | **0.000** | 0.000 |
| mean MRR | +0.0026 | **+0.0112** | -0.0053 |
| worst MRR on 13 | -0.006 | **-0.006** | -0.025 |

**If fusion is switched on, the setting is `k=5 w=0.3`.** It never loses
recall on any of the thirteen, gains four times the MRR of the setting slice 5
shipped, and its worst single loss is smaller than one query.

`k=30 w=0.3` buys more ceiling (+0.0187) and pays for it in ordering
(-0.0053 mean). It is the right choice ONLY if a reranker runs afterwards to
repair the order - which is exactly what measurement B4 tests.

### And it makes the next measurement sharp rather than vague

CLAUDE.md asks whether fusion's gain "survives reranking" and slice 6 answered
it once, with the reranker that makes retrieval worse. The mechanism above
turns that into a real hypothesis:

> Fusion damages ORDER and improves the CEILING. A reranker repairs order and
> cannot improve the ceiling. **They should be complementary**, and the pairing
> should beat either alone on a corpus with headroom.

That is measurement B4, and it now has a prediction to be wrong about.

---

## G9 — RERANKING HELPS, on 10 of 13 — and the three it HURTS have a pattern

**`gemini-3.5-flash-lite`, window 50, 13 corpora, 286 queries.** `r@50` did
not move on a single run, so the instrument is sound on all thirteen.

| corpus | vector MRR | + rerank | delta |
|---|---|---|---|
| log | 0.662 | **0.960** | **+0.298** |
| geo | 0.526 | 0.759 | +0.233 |
| quora | 0.608 | 0.804 | +0.196 |
| docx | 0.756 | 0.944 | +0.188 |
| notebooks | 0.528 | 0.698 | +0.170 |
| papers | 0.581 | 0.747 | +0.166 |
| cobra | 0.634 | 0.794 | +0.161 |
| requests | 0.646 | 0.791 | +0.145 |
| jq | 0.607 | 0.736 | +0.129 |
| websocket | 0.668 | 0.717 | +0.049 |
| **zod** | 0.802 | 0.775 | **-0.027** |
| **docs** | 0.864 | 0.816 | **-0.048** |
| **gson** | 0.658 | 0.580 | **-0.078** |

**Helped 10, hurt 3, mean +0.122.** The first run reported "+75% of headroom,
not one negative category" from two corpora. The direction survives; the
absolute claim does not.

### The three losses are not random

```
correlation(baseline vector MRR, rerank gain) = -0.584
correlation(corpus size,         rerank gain) = -0.512
```

**Every one of the seven corpora with vector MRR at or below 0.646 was
helped - 7 of 7, by +0.129 to +0.233.** Two of the three losses are the two
corpora where vector search was already best (docs 0.864, zod 0.802).

That is slice 6's own mechanism, measured across thirteen corpora instead of
asserted from one: *when the first stage is already right at #1, reranking has
no upside and all the downside.* It cannot promote what is already top; it can
only push it down.

### The routing signal STILL does not reproduce, in a third form

Pooled over every run, per question kind:

```
structure  +0.148    error      +0.128    api        +0.128
constant   +0.114    behaviour  +0.109
```

**Every category has a positive mean**, and every category also has a negative
case. Slice 6 measured `structure` at **-0.534** and built a routing rule on
it; here `structure` has the HIGHEST mean of the five. The variance is across
CORPORA, not across question kinds, which is the opposite of what was recorded.

---

## G10 — THE SKIP GATE IS WORTH HAVING, and `SKIP_MARGIN = None` is overturned

`SKIP_MARGIN = None` has been "confirmed" three times - slice 6, then twice in
slice 8's first run - each time on one or two corpora. On thirteen it is wrong.

| tau | mean MRR | vs always rerank | worse on | rerank calls skipped |
|---|---|---|---|---|
| 0.000 (never rerank) | 0.657 | -0.122 | 10 of 13 | 286/286 |
| 0.02 | 0.775 | -0.003 | 7 of 13 | 139/286 |
| **0.03** | **0.790** | **+0.011** | 5 of 13 | **90/286 (31%)** |
| **0.05** | 0.784 | **+0.005** | **2 of 13** | **52/286 (18%)** |
| 0.10 | 0.779 | +0.001 | 0 of 13 | 13/286 |
| *always rerank* | *0.779* | — | — | 0 |

**The gate rescues the corpora reranking hurts.** On `zod`, always-rerank
scores 0.775 and the gate at `tau = 0.02` scores **0.883** - better than
reranking AND better than not reranking, because it reranks the queries where
the top hit is uncertain and leaves the ones where it is not. On `docs` and
`gson` the gate correctly chooses "never", recovering the whole loss.

**`SKIP_MARGIN = 0.05` is the defensible setting**, by this project's own rule
- judge a method by how many independent ways it was shown better, never by
its best single number. `tau = 0.03` has the higher mean and loses on five
corpora; `0.05` is positive on the mean and loses on **two**, while still
skipping **18% of all rerank calls**.

That saving is not cosmetic. Step 2's `verify` needs one rerank call per
claim, and the rerank budget is the tightest renewing one in the project.

> **A threshold measured on one corpus is a property of that corpus.** Three
> separate runs agreed the gate was worthless, and all three were looking at
> corpora where reranking helped every query.

---

## G11 — THE CHUNKING KNOBS, measured for the first time

CLAUDE.md calls chunking "the highest-leverage decision in RAG", pins
`s = 500`, `o = 50` from a formula, and instructs: *"do not tune s by feeling.
Change it, re-run, and look at whether the right chunk comes back."* Nobody
had. This is that run, and it is only possible because ground truth is stored
as LINE NUMBERS - re-chunking moves every boundary and every index, and the
line that answers a question does not move.

### Chunk size: 500 is right, and it was a guess until now

Four corpora, five sizes, vector search only:

| size | mean MRR | cobra | log | jq | papers |
|---|---|---|---|---|---|
| 250 | 0.507 | 0.502 | 0.385 | 0.539 | **0.600** |
| 375 | 0.554 | 0.566 | 0.551 | 0.602 | 0.497 |
| **500 (shipped)** | **0.621** | 0.634 | **0.662** | 0.607 | 0.581 |
| 750 | 0.609 | **0.707** | 0.577 | 0.592 | 0.560 |
| 1000 | 0.561 | 0.680 | 0.429 | **0.642** | 0.493 |

**`s = 500` wins the pool**, and the curve has the shape the dilution argument
predicts: small chunks lose context, large chunks bury the answer. The project
chose it from `alpha = f/s` reasoning and it survives measurement.

**But the best size is CORPUS-DEPENDENT and the spread is large** - cobra
peaks at 750 (+0.073 over 500), jq at 1000, papers at 250. A per-corpus size
is a real gain being left on the table, and it is the kind of thing an ingest
could choose from the mean line length of a file.

### Overlap: 50 is NOT optimal, and more is worse

| overlap | mean MRR | cobra | log | jq |
|---|---|---|---|---|
| 0 | 0.623 | 0.631 | **0.675** | 0.563 |
| **25** | **0.660** | 0.597 | 0.669 | **0.715** |
| 50 (shipped) | 0.634 | **0.634** | 0.662 | 0.607 |
| 100 | 0.603 | 0.585 | 0.589 | 0.635 |

`o = 25` beats the shipped `o = 50` by +0.026, and **`o = 100` is the worst of
the four**. More overlap is not safer: it manufactures near-duplicate chunks
that compete with each other, so the right one is diluted rather than
protected.

**Recorded as a CANDIDATE, not a decision** - three corpora, and the per-corpus
ordering disagrees. The useful half is the direction: the overlap formula in
CLAUDE.md argues only that `o` must exceed the longest unsplittable fact, and
it says nothing about a cost to raising it. There is one.

### The free context header EARNS ITS PLACE

Six corpora, the same chunks embedded with and without `[file - label - lines]`:

| | mean MRR | cobra | log | jq | papers | notebooks | docs |
|---|---|---|---|---|---|---|---|
| **+header** | **0.646** | **0.634** | 0.662 | **0.607** | **0.581** | 0.528 | 0.864 |
| bare | 0.624 | 0.569 | 0.665 | 0.598 | 0.483 | **0.562** | 0.866 |

**+0.022 mean, and it costs nothing** - no LLM call, no extra token budget
beyond the header itself. It is largest exactly where a chunk is least
self-describing: `papers` (+0.098, a PDF page fragment) and `cobra` (+0.065, a
recursive-split Go fragment with no function label).

It is slightly NEGATIVE on `notebooks` (-0.034), where the header competes with
a cell that already says what it is.

This is "contextual retrieval" with no model in the loop, assumed useful since
slice 3 and never once embedded without. It is useful.

---

## G12 — THE BEST `k` AND `w` DEPEND ON CORPUS SIZE, and the reason is mechanical

The previous session built `--ladder` for exactly this and never ran it: slice
5 and slice 8's first pass both varied size **by accident**, because the
corpora happened to be 82, 335 and 729 chunks. That confounds size with
language and with domain.

The ladder holds everything still and slices ONE corpus:

**`geo`, sliced — same language, same domain, only size changes**

| chunks | vector `r@50` | best wRRF | its `r@50` | vector MRR |
|---|---|---|---|---|
| 100 | 1.000 | `k=5 w=0.15` | 1.000 | 0.733 |
| 200 | 1.000 | `k=5 w=0.1` | 1.000 | 0.613 |
| 300 | 1.000 | `k=5 w=0.1` | 1.000 | 0.558 |
| **400** | **0.929** | **`k=60 w=0.7`** | **1.000** | 0.539 |
| **600** | **0.872** | **`k=60 w=0.7`** | **0.974** | 0.508 |

**`jq`, sliced**

| chunks | vector `r@50` | best wRRF | its `r@50` |
|---|---|---|---|
| 200 | 1.000 | `k=10 w=0.7` | 1.000 |
| **300** | **0.917** | **`k=90 w=0.7`** | **1.000** |
| **400** | **0.938** | **`k=90 w=0.7`** | **1.000** |
| 600 | 0.947 | `k=5 w=0.05` | 0.947 |

### The rule, and it is not a tuning curve - it is a change of failure mode

```
SMALL corpus   vector r@50 is already 1.000
               -> keyword can only DISTURB the order
               -> best setting is a SMALL weight, 0.05-0.15

LARGE corpus   vector r@50 falls below 1.000 - answers are outside the window
               -> keyword has something real to ADD
               -> best setting is a LARGE k and a LARGE weight, k=60-90 w=0.7
```

At `k=60 w=0.7` on `geo` at 400 chunks, `r@50` goes **0.929 -> 1.000** and MRR
goes **0.539 -> 0.429**. It buys the ceiling and pays in ordering, at a much
higher exchange rate than the gentle settings do.

**So the aggressive setting only makes sense if something repairs the order
afterwards** - which is a reranker, and which is why this finding and the
fusion-plus-reranking measurement have to be read together rather than
separately.

### What this corrects

The pooled 13-corpus answer (`k=5 w=0.3`) is the best **single** setting for a
system that does not know how big the corpus is. It is NOT the best setting
for either end of the range, and on a 400-chunk corpus it leaves most of the
available recall on the table.

> **A hyperparameter swept across corpora of different sizes is measuring two
> things at once.** Slice 5 swept `k` and `w` on corpora of 82 and 335 chunks
> and concluded a small weight was "safe"; on a 400-chunk slice of the same
> language, a small weight is simply weak.

---

## G13 — HOW MANY CHUNKS TO SEND: more is better, and it flattens near 50

The one question retrieval cannot answer, because `recall@N` only rises with
N. CLAUDE.md states it as a product of two terms:

$$
P(\text{good report}) \approx
\underbrace{P(\text{the answer is in the } N)}_{\text{rises with } N}
\times
\underbrace{P(\text{the model uses it})}_{\text{assumed to fall with } N}
$$

The right factor has **never been measured in this project**, and
`VECTOR_TOP_N = 25` and `RERANK_TOP_N = 10` were chosen without it.

**Five reports, `gemini-3.6-flash`, the lean `REPORT` template, the same
question, `quora_siamese` - the only fixture with an answer key. Every run
finished (`STOP`).**

| sent | prompt tokens | seconds | findings | of the 5 that carry the story | citations |
|---|---|---|---|---|---|
| top-5 | 10/100 | 6,718 | 63.8 | **2/19** | 1/5 | 48/48 |
| top-10 | 20/100 | 9,511 | 45.5 | 5/19 | 3/5 | 39/41 |
| top-20 | 38/100 | 13,460 | 52.0 | 5/19 | 2/5 | 44/44 |
| **top-50** | **68/100** | 21,152 | 69.4 | **11/19** | **4/5** | 69/69 |
| **stuffed** | **100/100** | 24,275 | 54.9 | **11/19** | **4/5** | 50/51 |

### There is NO dilution penalty in this range

The assumed right-hand term does not appear. Sending 68 chunks scores exactly
what sending 100 scores, and everything below 20 collapses. The curve rises
and then flattens; it does not turn over.

**So `VECTOR_TOP_N = 25` and `RERANK_TOP_N = 10` are very likely too small.**
The 20-chunk run found 5 of 19 findings and 2 of the 5 that matter; the
68-chunk run found 11 and 4.

### How this was graded, and why the absolute number is not 13

A **mechanical screen** of 19 markers, then read to confirm. CLAUDE.md's rule
is that pattern matching is a screen and never a score, so the screen's
`stuffed = 11/19` is not comparable with the hand-scored `13/19` baseline of
2026-08-17 - a different grader counts differently.

**The COMPARISON is valid**, because all five runs were graded by the same
screen, and the one claim spot-checked by reading held up: the top-50 report
really does name the flagship finding with a citation -
`[B-27 "# Pool from the projected features (not original lstm_output)"]`.

### Honest limits

- **One fixture.** `quora_siamese` is the only corpus in this project with an
  answer key, and it is machine-learning Python.
- **One run per N**, at `temperature 0`. The top-10 vs top-20 inversion (3 vs
  2 story findings) is within what one run can wobble.
- **One model.** Section 11.9's separate question - whether a cheap tier can
  write the report - is measured elsewhere and is not this.

---

## G14 — THE INSTRUMENT WAS BROKEN FOR LISTWISE RERANKERS, and it voided five corpora

**Found 2026-09-17, before any new measurement was trusted.** It is the same
class of defect as slice 4's identical-vectors bug: the numbers were confident,
well-formatted and produced by code that had a guard against exactly this.

### The mechanism

A cross-encoder returns a **score** per document. An LLM reranker returns an
**order** and no scores at all. `PairScores` papered over the difference by
synthesising a score from the place:

```
scored = ranking.scores or tuple(len(order) - place for place in range(len(order)))
```

So **every call produced the same numbers**: a 50-document call scored its
documents 50, 49, 48 … 1, and so did the next one. The cache was keyed
`query:chunk` with no record of which call a score came from, and `fetch()`
split anything larger than `SEARCH_LIMIT` into batches. Two calls covering
different candidate sets for one query therefore collided — the union held two
documents scored 50.0, two scored 49.0 — and the "merged" order was arithmetic
rather than anything the model had said.

### It was reachable three ordinary ways, and all three happened

| route | what makes the sets differ |
|---|---|
| `--fusion` | the fused top-50 is not the dense top-50, so the union crosses 50 |
| `--window=100` | the candidate set is larger than one call |
| a re-run | a second window adds a second call to an existing cache |

### The audit

Every cache file, checking whether one query's synthesised scores repeat:

| listwise cache | queries recoverable as ONE call |
|---|---|
| cobra, docs, docx, log, notebooks, requests, websocket, zod | **all — clean** |
| **geo, gson, jq, papers** | **0 — every one a `--fusion` run** |
| **quora** | **0 — also run at window 30 in slice 6** |
| **all three `merged_*`** | **0** |

The pattern is exact: **the four corpora run with `--fusion` are four of the
five void ones**, and the fifth is the one corpus that had been scored twice at
different windows. No non-fusion, single-window corpus is affected.

### The guard named the hazard and then assumed it away

`verify_pointwise` skips a listwise reranker, correctly, and explains why — and
then says:

> *"It is scored per call, and the per-pair cache is only ever asked for the
> order it stored."*

**Nothing enforced that.** The sentence is a description of how the cache was
expected to be used, written beside code that made the other use trivially
easy. This is the third time in this project a rule has lived in prose and been
broken by ordinary work.

### `bench_merged` had a second bug in the same family

Per-side A and per-side B both indexed their candidates from zero, so the two
sides **shared a cache key space**. Side B's ranking was served from side A's
entries, and the merged pool's side-A half was served from the per-side call —
so **the merged call for side A never happened at all**. With both surviving
calls synthesising their own 50…1, the top ten came out as exactly five per
side on **all forty queries**, across two unrelated corpus pairs.

That is not an unlikely result. It is an identity:

```
side A candidates scored 50..1   in its own call
side B candidates scored 50..1   in its own call
top 10 of the union              = 50,50,49,49,48,48,47,47,46,46
                                 = five from each side, always
```

The recorded finding — *"merged gave side A 50% of the slots, min 50%, max
50%, starved a side on 0 of 20"* — was this identity wearing a measurement's
clothes.

### Does this reach what we SHIP? No — and that was checked, not assumed

The first question a reader should ask. Measured by grepping the package:

```
.scores read anywhere in labpilot/ outside rerank/contracts.py   ->  nothing
```

`api/services.py` uses `ranking.order` and `ranking.model`; the shipped
`rerank()` makes **one call per tier** over the documents it was handed, keeps
no cache, and never synthesises a score. So the defect lives entirely in
`scripts/`, and the production path was never capable of it.

That is not luck. The synthesis existed only because a *cache* needed a
sortable number per pair, and production has no cache. **The bug was created by
the measurement's own optimisation** — which is the thing to watch for, because
a script written to make a run repeatable is exactly where nobody looks.

### The fix is structural, not remembered

A listwise entry is now keyed by the **candidate set itself**, an unseen set
**raises** instead of being stitched together, and a listwise call is **never
split**. Fetch is per candidate set rather than over the union: a pointwise
cache does not care, and a listwise one cannot survive it.

Every call in `bench_merged` now indexes into the merged document list, so no
two candidate sets can share a key.

### What survived, and what had to be paid for again

The 13 clean listwise caches were **migrated** rather than re-run: their scores
are exactly `n…1` with no duplicates, so they came from one call and the order
is exactly recoverable. **211 rankings kept, 0 calls spent.** Verified by
re-scoring `cobra` end to end — **MRR 0.634 → 0.794, reproducing the recorded
number to three decimals with `calls: 0`.**

The 5 void corpora were re-run.

> **A guard that skips a case must say what protects that case instead.**
> `verify_pointwise` proves the pointwise cache is sound on every run. Nothing
> proved anything about the listwise one, and the comment that stood in for a
> proof was wrong.

---

## G15 — HOW MANY CHUNKS TO SEND: dilution is REAL, it peaks at 20, and N is a COUNT

**This supersedes G13 entirely.** G13 ran on `quora_siamese` alone — 100 chunks,
so "send 68" meant sending 68% of the whole corpus — and concluded *"there is
no dilution penalty in this range"*. The user rejected that fixture and was
right. This is **13 whole corpora, 78 to 1,160 chunks, 286 questions**, graded
mechanically against each fixture's own ground truth.

### Both terms of the product are now measured

CLAUDE.md states the question as a product and calls the right-hand term
unmeasurable from retrieval:

$$
P(\text{good report}) \approx
\underbrace{P(\text{the answer is in the } N)}_{\text{rises with } N}
\times
\underbrace{P(\text{the model uses it})}_{\text{never measured}}
$$

The fixtures carry ground truth, so the split is free. A question is
**answerable** when a chunk holding its answer is in the set we sent; **USED**
is `correct / answerable` — of the questions whose answer really was in the
prompt, how many the model got right.

**Balanced panel — the 10 corpora that answered at every N**, so the only thing
changing across a row is N:

| N | mean share | mean tokens | answerable | **USED** | correct/asked | fits gemma |
|---|---|---|---|---|---|---|
| 5 | 1% | 2,505 | 27 | 0.889 | 0.099 | 10 of 10 |
| 10 | 3% | 4,382 | 55 | 0.964 | 0.219 | 10 of 10 |
| **20** | 5% | 8,170 | 117 | **0.983** | 0.475 | **10 of 10** |
| 30 | 8% | 12,333 | 143 | 0.881 | 0.521 | 7 of 10 |
| 50 | 14% | 20,099 | 166 | 0.904 | 0.620 | 2 of 10 |
| 100 | 27% | 40,121 | 201 | **0.851** | 0.707 | **0 of 10** |

**DILUTION IS REAL AND IT PEAKS AT 20** — but this pooled figure OVERSTATES
it, and the correction is immediately below. The model uses **98.3%** of the
evidence it is handed at N=20 and **85.1%** at N=100; on a fixed question set
the fall is to 90.6%, and it is a step rather than a slope. `correct/asked` keeps climbing anyway, because retrieval adds answers
faster than the model loses the ability to use them.

> **A run that measured only the total would have concluded "more is always
> better" and missed the cost entirely.** That is what G13 did, on one fixture
> where the two terms could not be separated at all.

### CORRECTION — the size of the dilution effect was overstated, and the shape was wrong

*Written the same session, after testing a confound in my own claim.*

The table above says USED falls 0.983 → 0.851 and calls that dilution. **It is
confounded.** A question only *becomes* answerable at N=100 when its answer
chunk was ranked 51st to 100th by retrieval — which is to say, the questions
that enter the pool late are **the hard ones**. So a falling ratio may be
measuring the changing difficulty mix rather than the length of the prompt, and
the pooled number cannot tell those apart.

**Hold the questions still.** `scripts/dilution.py` restricts to the questions
whose answer was in the prompt at **every** N, and compares them **pairwise** —
question by question, because the same question under two prompt lengths is a
paired observation and averaging throws the power away.

```
                    N=20    N=30    N=50    N=100
unrestricted USED   0.983   0.881   0.904   0.851      -13 points
FIXED SET, n=117    0.983   0.915   0.932   0.906       -8 points
```

**Most of the apparent collapse was the difficulty mix.** The real effect is
about eight points, not thirteen.

### And it is a STEP at 20, not a slope

Two-sided sign test over the questions that changed:

| pair | right→wrong | wrong→right | net | p |
|---|---|---|---|---|
| N=20 → N=30 | 9 | 1 | −8 | **0.021** |
| N=20 → N=50 | 7 | 1 | −6 | 0.070 |
| **N=20 → N=100** | **10** | **1** | **−9** | **0.012** |
| N=30 → N=50 | 5 | 7 | +2 | 0.774 |
| N=30 → N=100 | 9 | 8 | −1 | **1.000** |
| N=50 → N=100 | 6 | 3 | −3 | 0.508 |

Leaving N=20 costs questions, and the direction is lopsided — ten lost against
one gained. **Past 30, nothing moves at all.** So the curve is a step down after
20 followed by a plateau, not the progressive decay the first table suggested
and not the smooth turn the theory predicts.

### What this does and does not change

**Unchanged:** N=20 is the optimum, and it is still the largest N that fits
Gemma on every corpus. The count-versus-coverage answer is unaffected, because
it compares where peaks sit and not how deep the valley is.

**Changed:** the *reason* to stop at 20. It is not that the model progressively
drowns — it does not. It is that leaving 20 costs about eight questions in a
hundred and buys nothing back, while the token cost triples and every cheap
tier disappears.

**Still not established:** that dilution exists at all beyond N=30. The
N=30→N=100 comparison is 9 against 8, which is as close to nothing as a
measurement gets.

> **A ratio whose denominator changes with the treatment is not a measurement
> of the treatment.** I wrote "dilution is real and costs thirteen points"
> from a pooled ratio, and the pooled ratio could not have told me otherwise.
> The fixed set was free, sitting in the same saved replies.

### The panel has to be balanced, and that is not a detail

Only a corpus of 100+ chunks can be asked for N=100, so an unbalanced N=100 row
is computed over systematically **larger** corpora than the N=5 row. It
confounds *"more chunks help"* with *"big corpora are harder"*, and those
predict opposite things.

### Is N a count, or a share of the corpus?

The question DECISIONS.md posed before the run, with both answers named in
advance:

```
flat across corpus sizes  ->  it is about the COUNT
tracks a percentage       ->  it is about COVERAGE, and 50 is far too few
                              on a repository
```

Per corpus, over a **15× range** of sizes:

| | median | range | **cv** |
|---|---|---|---|
| best N as a **COUNT** | **20** | 10–50 | **0.41** |
| best N as a **SHARE** | — | 2%–37% | 1.03 |

**The count is two and a half times the more stable description, and it is 20
on nine of thirteen corpora. N is about the COUNT.**

### The denominator floor is load-bearing

`USED` is a ratio, and at N=5 the whole panel holds **under three answerable
questions per corpus**. Without a floor, eight corpora score a perfect 1.000
from two of two and the same table reads *"the best N is 5"* — a measurement of
the fixture, not of the model. Cells below eight answerable questions are
hidden and print their denominator instead, so the reader can see why.

### What this decides

**`RERANK_TOP_N = 10` is vindicated and `VECTOR_TOP_N = 25` is too large.** The
constants are **per side**, so 10 per side is 20 in the prompt — exactly the
measured optimum — while 25 per side is 50, past the peak, where USED has
fallen from 0.983 to 0.904.

This **corrects a correction**: `RESUME.md` recorded *"10 is too small"*, which
came from G13's single fixture.

**Three independent lines land on 20:** the pooled USED peak, the per-corpus
median, and the token cost — 20 chunks is 8,170 tokens, the largest N that
still fits Gemma's 14,400-calls-a-day tier on **every** corpus measured. At
N=50 only 2 of 10 fit; at N=100, none.

> **The real trade is not quality against dilution. It is quality against how
> many models can still serve the prompt.**

### Honest limits

- **One model** wrote every answer (`gemini-3.5-flash-lite`). A stronger model
  may dilute later; a weaker one sooner.
- **`correct/asked` still rises at N=100.** If the product's objective is total
  questions answered rather than efficient use of evidence, the answer is
  different — and that is a product decision, not a measurement.
- **One run per cell**, at `temperature 0`.

---

## G16 — THE HYBRID-SEARCH PREMISE IS TRUE IN DIRECTION AND FALSE IN MAGNITUDE

Every fixture labels each query `named` — it shares a word with the code — or
`paraphrase`, which deliberately avoids it. **Nothing had ever read the label**,
though the entire case for a keyword channel in this project is one sentence
built on it:

> *"Vectors are good at meaning. Keywords are good at names. Code is mostly
> names."*

### Pooling the absolute score cannot test it

```
vector alone, by wording       named 0.670   paraphrase 0.654   n = 171
```

A gap of 0.016, which says nothing about BM25 — an easy corpus lifts both
groups. So the comparison must be **paired**, per query, on the *difference*.

### Paired, 13 corpora

```
gain over vector alone (MRR)          named        paraphrase
  bm25                               -0.093          -0.176
  ts_rank                            -0.161          -0.205
  wRRF k=5 w=0.15                    +0.003          +0.003
  score a=0.85                       +0.012          +0.016
```

**BM25 loses on both groups — and it loses half as much on `named`.** Gap
**+0.082**. The mechanism is real: keyword search really is relatively better
when the query names the identifier. It is simply never good enough to win, on
either group, on any of thirteen corpora.

### The routing signal does not reproduce either

Slice 5 recorded *"keyword WINS on `constant` questions"* — 0.423 against
vector's 0.354 — from **one corpus**. Paired over thirteen:

```
bm25 over vector, by question kind
  claim      -0.048      constant   -0.089      behaviour  -0.145
  structure  -0.167      error      -0.171      api        -0.214
```

`constant` is indeed where BM25 is **least bad**, so the direction survives.
**The win does not.**

### The method nobody kept

`score a=0.85` — min-max score fusion — is positive on **five of seven**
question kinds and beats `wRRF` on both wording groups. Slice 5 discarded it
for having *"no mechanism"* and named `wRRF` the candidate instead.

> **Judge a method by how many independent ways it was shown better.** That
> rule retired score fusion on one corpus. On thirteen it is the best fusion
> method measured, and the rule now argues the other way.

---

## G17 — FUSION HELPS ONLY BELOW `r@50` ≈ 0.95, and the method should be SCORE FUSION

Slice 5 decided the keyword channel with this sentence:

> *"NOT ONE fusion setting improved `recall@50` on any run."*

It was measured on `quora` and `requests`. `quora` is at `r@50 = 1.000` and
`requests` at 0.978. **There was no room.** The sentence is true and it is a
statement about two saturated corpora, not about fusion.

### Split every corpus by whether it has headroom

Seven of thirteen sit at `r@50 = 1.000` and cannot show a recall gain by
construction.

| | SATURATED (7) | HEADROOM (6) |
|---|---|---|
| **`r@50`** wRRF k=5 w=0.15 | +0.000, 0 of 7 | **+0.025, 3 of 6** |
| **`r@50`** score a=0.85 | +0.000, 0 of 7 | **+0.032, 3 of 6** |
| **`r@50`** ADAPTIVE k=10 | +0.000, 0 of 7 | +0.029, 3 of 6 |
| **`r@50`** bm25 alone | −0.135 | −0.132 |
| **MRR** score a=0.85 | **+0.028, 5 of 7** | **+0.029, 3 of 6** |
| **MRR** wRRF k=5 w=0.15 | +0.002, 2 of 7 | +0.004, 4 of 6 |

**Two different effects, and slice 5 could see neither.**

Fusion's **recall** gain is real and it is confined to corpora with room.
Fusion's **ordering** gain is independent of saturation — score fusion is
+0.028 and +0.029 in the two groups, essentially the same number.

### Per corpus, sorted by how much room there is

```
corpus      r@50 vec     wRRF    score     MRR vec    wRRF    score
geo            0.867   +0.022   +0.067       0.526  +0.005   -0.004
jq             0.900   +0.050   +0.050       0.607  -0.006   -0.029
gson           0.923   +0.077   +0.077       0.658  +0.005   +0.105
cobra          0.950   +0.000   +0.000       0.634  -0.003   +0.054
papers         0.950   +0.000   +0.000       0.581  +0.004   +0.062
requests       0.978   +0.000   +0.000       0.646  +0.016   -0.015
docs .. zod    1.000   +0.000   +0.000         ...
```

**The threshold is visible and sharp.** Every recall gain lands on the three
corpora below `r@50 = 0.95`, and every corpus at or above it is **exactly
+0.000**. So:

> **Switch the keyword channel on when vector `r@50` is below about 0.95, and
> leave it off above.** Below that line it adds 0.02–0.08 of recall; above it,
> it adds nothing at all and can only cost ordering.

**Neither candidate ever LOSES `r@50`, on any of thirteen corpora.** That is
worth stating plainly, because slice 5's headline reads as though fusion were
dangerous. It is not; it was merely useless on the two corpora it was tried on.

### The method should be score fusion, not wRRF

| | worst `r@50` | worst MRR | best MRR | MRR wins |
|---|---|---|---|---|
| wRRF k=5 w=0.15 | +0.000 | −0.006 | +0.016 | 6 of 13 |
| **score a=0.85** | **+0.000** | −0.029 | **+0.111** | **9 of 13** |

**wRRF's entire MRR range lies inside one-query resolution.** On a 20-query
corpus one query moving one place is 0.025 MRR, so a method whose best case is
+0.016 and worst is −0.006 has not been shown to do anything.

Score fusion gains on nine of thirteen, wins the largest recall gain on the
corpus with the most headroom (`geo` +0.067 against wRRF's +0.022), and its
worst case is −0.029 — about one query.

**Slice 5 discarded score fusion for having "no mechanism" and named wRRF the
candidate.** On thirteen corpora the evidence points the other way, and the
project's own rule — *judge a method by how many independent ways it was shown
better* — now argues for the method it retired.

### Honest limits

- **One embedder.** Every number is `codestral-embed`; a different embedder
  changes the dense ranking and therefore what is left for keywords to add.
- **`a = 0.85` was never swept.** It is the value carried forward from slice 5's
  original sweep, and it is the one setting of score fusion measured here.
- **`r@50 ≈ 0.95` is read off thirteen points**, three of them below the line.
  It is a threshold with a mechanism behind it, not a calibrated constant.


---

## G18 — THE ROUTING SIGNAL IS DEAD, and the same denominator error produced it three times

### Judge a delta against what the fixture can resolve, not against zero

`RESUME.md` states the rule and nothing had applied it:

> *a tolerance must match what the fixture can resolve — on 20 queries, one
> query moving one place is 0.025 MRR*

The fixtures run from 12 to 45 queries, so one query is **0.042 MRR on `docx`
and 0.011 on `geo`**. A table printing "helped 10, hurt 3" against zero is
comparing a measurement with a wobble.

Each rerank delta divided by its own fixture's resolution:

| | corpora | range |
|---|---|---|
| **REAL gain** | **9** | +5.1 to +20.9 queries |
| **REAL loss** | **1** | `gson`, −2.7 queries |
| **nothing measurable** | **3** | `docs` −1.8q, `zod` −1.1q, `websocket` +1.5q |

> **"Helped 10, hurt 3" overstates both sides.** Two of the three losses are one
> or two queries and are not evidence of harm; `websocket`'s "gain" is not
> evidence of help either. Reranking helps decisively on nine corpora, hurts
> decisively on one, and does nothing measurable on three.

### And the routing signal does not survive the same lens

Slice 6 built a routing signal on `structure = −0.534`, from one model on one
corpus. Weighted by how many queries each corpus actually contributes to each
kind, over 286 queries:

| kind | queries | weighted gain | worst single corpus |
|---|---|---|---|
| claim | 10 | **+0.303** | — |
| error | 32 | **+0.228** | gson −0.259 (n=2) |
| **structure** | 46 | **+0.169** | **websocket −0.500 (n=1)** |
| checklist | 7 | +0.151 | — |
| constant | 59 | +0.108 | zod −0.104 (n=8) |
| behaviour | 86 | +0.107 | gson −0.104 (n=8) |
| api | 46 | +0.102 | docs −0.208 (n=8) |

**Every kind is positive.** `structure` — the one the routing signal was built
on — is third best.

And the worst `structure` case is **one query**, on `websocket`, scored
−0.500. That is exactly how a −0.534 is manufactured: a kind with a single
query in it has a resolution of 1.0, so the only values it can take are 0,
±0.5 and ±1.0.

> **There is no routing signal in the rerank data.** Reranking helps every
> question kind measured. Slice 6's finding was one model on one corpus, and
> its magnitude came from per-kind denominators of one and two.

### The same error, three times in one session

This is the through-line worth keeping, because each instance looked completely
different:

| where | the ratio | what it produced |
|---|---|---|
| **top-N** | `USED` at N=5 — under 3 answerable questions per corpus | eight corpora scoring a perfect 1.000 from two of two, and a table reading *"the best N is 5"* |
| **reranking** | MRR delta on a 13-query corpus | `gson −0.104` filed beside `requests +0.145` as though both were "one corpus" |
| **routing** | per-kind delta with one query in the kind | `structure −0.534`, which became a design principle |

All three are the same mistake: **a ratio over a denominator small enough that
the fixture, not the effect, decides the value.** None of them is visible in the
number itself — only in the count beside it.

> **Print the denominator next to every ratio.** Each of these was found by
> asking "how many questions is that?", and none of them was visible by reading
> the value.


# Full text: SLICE 5 MEASURED — 2026-09-07: vector ships, wRRF is a named candidate

[Docs home](../../README.md)

## SLICE 5 MEASURED — 2026-09-07: vector ships, wRRF is a named candidate

*The user refused a decision taken on one fixture and asked for a second corpus,
more queries, every algorithm, a parameter sweep, and BM25 by hand. This is what
came back. **Two corpora x two embedders = four runs, 62 graded queries, 82
fusion settings, and no generation quota spent.***

**Reproduce it:** `scripts/retrieval/score_hybrid.py`, committed for the same reason
`score_retrieval.py` is — *a measurement you cannot repeat is a number, not a
result.*


### What was built

| piece | what |
|---|---|
| **second corpus** | `psf/requests` at `dae7ef6`, `src/requests/*.py` — 19 files, 6,394 lines, **335 chunks**. Real, third-party, and not about machine learning |
| **45 new queries** | `data/samples/requests_http/queries.json`, **frozen before any measurement** |
| **two new labels** | `asks` (constant · behaviour · error · api · structure) and `wording` (**named** = shares a word with the code, **paraphrase** = deliberately avoids it) |
| **BM25 by hand** | Python, over **Postgres's own lexemes**, so the ranking formula is the only difference from `ts_rank` |
| **fusion** | RRF, weighted RRF, min-max score fusion, CombMNZ, and two new ones below |

**The query file needed a `file` field, and that is a finding, not a detail.**
`quora_siamese` is one file, so ground truth could be a bare line number. A
19-file corpus cannot: line 186 exists in most of them. Any future fixture must
carry the file.


### The result that decides it: recall@50 is already at the ceiling

The pipeline retrieves **50** and then reranks. So the number that gates what
the model can ever see is **recall@50**, not recall@5.

```
recall@50, vector search ALONE
  quora    / codestral   1.000    17 of 17
  quora    / gemini      1.000    17 of 17
  requests / codestral   0.978    44 of 45
  requests / gemini      1.000    45 of 45
```

**123 of 124.** And the single miss was not rescued by keyword search either:

```
R45  "how is the body handed back a piece at a time instead of all at once"
     vector 67  ·  bm25 NOT FOUND  ·  ts_rank NOT FOUND  ·  best fusion 67
```

**Across all 82 fusion settings, not one improved recall@50 on any run.** The
best of them tie at `0.994` average; the heavy ones lose it.

> **Before tuning a number, check how much room it has left.** Ours had none —
> which is exactly the saturation trap recorded the day before, arriving again
> in a different metric.


### The two fixtures gave OPPOSITE answers, which is the whole point

```
                     quora (17 q)      requests (45 q)
vector      MRR          0.608              0.646
RRF k=10    MRR          0.699  +15%        0.564  -13%
```

Same code, same method, same day. **On the old fixture hybrid search is a clear
win; on the bigger one it is a clear loss.** Deciding on the 17 queries alone
would have shipped it. This is the concrete proof behind
[the saturated-fixture rule](../../step1/keyword-search.md#the-fixture-is-saturated-so-it-may-reject-and-may-not-confirm--2026-09-07).


### The comparison table — averaged over all four runs

| method | r@50 | r@10 | r@5 | MRR | worst single run vs vector |
|---|---|---|---|---|---|
| **vector alone** | **0.994** | 0.930 | 0.871 | 0.645 | +0.000 |
| bm25 alone | 0.926 | 0.804 | 0.678 | 0.475 | **−0.267** |
| **wRRF k=5 w=0.15** | **0.994** | 0.935 | **0.891** | 0.655 | **+0.000** |
| wRRF k=10 w=0.1 | 0.994 | 0.930 | 0.876 | **0.657** | **+0.000** |
| wRRF k=20 w=0.05 | 0.994 | 0.930 | 0.876 | 0.656 | **+0.000** |
| wRRF k=5 w=0.2 | 0.994 | 0.941 | 0.896 | 0.652 | −0.005 |
| wRRF k=60 w=0.25 | 0.994 | 0.943 | 0.873 | 0.645 | −0.059 |
| wRRF k=60 w=0.5 | 0.994 | 0.943 | 0.830 | 0.644 | −0.118 |
| **wRRF k=60 w=1.0** | 0.978 | 0.915 | 0.797 | 0.621 | **−0.124** |
| score a=0.85 | 0.994 | 0.941 | 0.882 | **0.671** | −0.059 |
| RESCUE m=5 after=20 | 0.994 | 0.930 | 0.871 | 0.645 | +0.000 |
| RESCUE m=10 after=5 | 0.994 | **0.950** | 0.871 | 0.645 | −0.044 |

**Read the last column before the others.** It is the biggest loss against
vector on any *single* run. An average that hides a −0.124 is the same mistake
as a fixture that hides a blind spot.

**The first thing I tested was the worst row in the table.** `k=60, w=1.0` is
plain RRF, the textbook default, and it is the only setting that loses
recall@50. That is why the first report said *"hybrid search hurts"* — it was a
statement about one badly chosen setting, not about hybrid search.

> **A default is not a measurement, and a bad default is not a verdict on the
> method.** pgvector's `ef_search = 40` taught this in slice 4; RRF's `k = 60`
> taught it again here.


### Nine settings are never worse than vector, anywhere

`wRRF k=5 w=0.1` · `k=5 w=0.15` · `k=10 w=0.1` · `k=20 w=0.05` · `k=30 w=0.05` ·
`RESCUE m=3 after=20` · `m=3 after=30` · `m=5 after=20` · `m=5 after=30`

**The safe region is small `k` with a small keyword weight — roughly 0.05 to
0.2.** Best of them, `wRRF k=5 w=0.15`: `r@5 +0.020`, `MRR +0.010`,
`r@50 +0.000`, and never below vector on any run or any metric. That is about
**one query per fixture** — real, repeatable, and small.


### BM25 beats both Postgres rankers, measured

| | r@1 | r@5 | r@50 | MRR |
|---|---|---|---|---|
| **bm25 (ours)** | **0.400** | **0.533** | **0.911** | **0.479** |
| `ts_rank` | 0.311 | 0.511 | 0.867 | 0.416 |
| `ts_rank_cd` | 0.178 | 0.578 | 0.911 | 0.327 |

*(requests corpus; the keyword rankers do not depend on the embedder.)*

So the missing IDF is a real, measured cost and not an argument. **Every one of
the nine safe fusion settings uses BM25, not `ts_rank`.** But BM25 alone still
loses to vector on every metric on every run.


### Where keyword search actually wins: `constant` queries, and only those

```
MRR by question kind -- requests corpus, codestral

                vector    bm25
constant         0.354   0.423    <- keyword WINS
error            0.600   0.612    <- level
behaviour        0.787   0.657
api              0.456   0.175
structure        0.926   0.426
```

`constant` is the `CLIP_NORM` shape — *"what is this value set to"*. Keyword
search wins there on both corpora and both embedders, and loses everywhere
else. **That is a routing signal, not a fusion signal**, and it lines up with
this file's existing rule to route by question type.


### Two fusion methods invented here

**RESCUE — keyword may PROMOTE, never DEMOTE.** RRF punishes a chunk that only
one list found. Measured: quora `D14` sat at place 5 under vector alone, BM25
never returned it, and RRF pushed it to **27**, because rival chunks collected
points from both lists and it could not. RESCUE keeps the vector order above a
cut and only lifts the keyword top-m into the gap below, so recall@1..cut
cannot fall. **It works exactly as designed: it never hurts, and it never
helps.** Worth knowing; not worth shipping alone.

**ADAPTIVE RRF — weight the keyword list by how SELECTIVE it was.** Motivated
by a real observation: for `D2` the keyword query matched 7 of 82 chunks and
was right; for `D6` it matched 73 of 82 and was noise. Weighting by
`1 - matched/N` costs nothing. It won on quora (best MRR, 0.730) and was
middling on requests, so it is **not** carried forward as a candidate.


### Corrections this run produced

- **`gemini-embedding-001` is NOT clearly better than `codestral-embed`.** It
  wins on the old fixture (MRR 0.674 vs 0.608) and is level on the new one
  (0.650 vs 0.646) — while being **worse at recall@10** there, 0.844 against
  0.933. It does win recall@50, 1.000 against 0.978. Slice 8 still owns this.
- **The `D2` argument for hybrid search is weaker than it looked.** `D2` sat at
  place 46 of 82 — *inside* the top 50 the pipeline already retrieves. The
  motivating example never actually fell out of the window.


### THE DECISION — 2026-09-07, the user's call

1. **Vector search alone is the retrieval path for now.** No fusion, no keyword
   column on the query path.
2. **BM25 is the keyword algorithm if a keyword channel is ever switched on.**
   Not `ts_rank`, and not `ts_rank_cd`.
3. **`wRRF` with a small `k` and a small weight is a NAMED CANDIDATE for slice
   8, allowed to replace vector search if it wins there.** Its numbers tell a
   better story than one fixture can settle, and `RESCUE` and the other safe
   settings stay on the list with it.
4. **Nothing here is decided by this experiment.** One experiment, two corpora
   (both Python), 62 queries, one author, small corpora, and **no reranker**.

**What slice 8 must do before this becomes a policy:**

```
MANY corpora      not two, and not all in one language
MANY models       the fusion weight may move with the embedder
WITH the reranker the gain measured here is all INSIDE the top 50,
                  which is precisely what the reranker re-orders
LARGE corpora     at 10,000 chunks a top-50 window is 0.5% of the corpus,
                  not the 15-61% it was here. recall@50 will fall, and that
                  is the number that could overturn everything above
ALL FOUR knobs    k and weight were swept; k1 and b NEVER were. --sweep-bm25
ALL FIVE methods  score fusion, CombMNZ and ADAPTIVE were restored 2026-09-07
```

> **The gain is real, small, and in the region slice 6 overwrites.** That is not
> a reason to delete it — it is a reason not to claim it yet.



### The four hyperparameters, and the three methods that were lost — 2026-09-07

*Raised by the user right after the decision above, and both halves were right.
The sweep looked exhaustive at 82 settings. It varied half the knobs, and the
committed script had kept fewer than half the methods.*

#### Two of the four knobs were never swept

| # | knob | belongs to | swept? | value we use |
|---|---|---|---|---|
| 1 | `k` | RRF rank constant | ✅ 5, 10, 20, 30, 60 | **5** |
| 2 | keyword weight | RRF | ✅ 0.05 … 1.0 | **0.15** |
| 3 | **`k1`** | **BM25 saturation** | ❌ **never** | 1.2 — a textbook guess |
| 4 | **`b`** | **BM25 length normalisation** | ❌ **never** | 0.75 — a textbook guess |

`K1, B = 1.2, 0.75` was a module constant in `score_hybrid.py`, not a loop
variable. So the BM25 channel that **every** winning fusion setting depends on
was scored at its default and never tuned.

**And the textbook has already been wrong here once.** RRF's own `k = 60,
w = 1.0` is the worst row in our own table — the only setting that loses
recall@50. That is a reason to check knobs 3 and 4, not to assume them.
**`--sweep-bm25` now varies them.**

#### The first result, preliminary on purpose

quora / codestral, over `k1` in {0.9, 1.2, 1.6, 2.0} and `b` in {0.0, 0.3, 0.75}:

```
bm25 alone        MRR 0.465 -> 0.492     k1 moves it, about +0.027
wRRF k=5 w=0.15   MRR 0.619 -> 0.624     the WINNER moves about +0.005
RESCUE            MRR 0.610 -> 0.610     flat
recall@50         unchanged everywhere
```

**Tuning the keyword channel moves the keyword channel, and barely moves the
fused result.** That is the expected shape — the gain from fusion is small to
begin with, so a better BM25 can only ever be a fraction of a small number.
And 0.619 against 0.624 is far under one query on a 17-query fixture, so this
is a direction and not a finding.

*One prediction of mine was wrong, and it is corrected here.* I expected `b` to
be nearly flat, because our chunks are capped near 510 tokens and are fairly
uniform, so there is little length variation left for it to normalise. The
**lowest** `b` values gave the best fused MRR. On one saturated fixture that
may well be noise — but it is not the flat line I predicted, and the prediction
is written down so slice 8 tests it instead of inheriting it.

#### Five methods were measured; the script had kept two

| method | ours? | verdict |
|---|---|---|
| **vector alone** | — | **ships today** |
| **wRRF** | standard | **named candidate for slice 8** |
| **RESCUE** | **invented here** | **on the shelf — never hurts, never helps** |
| score fusion (min-max) | standard | best MRR on a run, lost recall@50 on another |
| CombMNZ | standard | not a contender |
| ADAPTIVE RRF | invented here | won quora, middling on requests |

`rankers()` built only wRRF and RESCUE. **Score fusion, CombMNZ and ADAPTIVE
lived in a session scratchpad and were lost** — exactly as `score_retrieval.py`
was lost before it was committed. Three rows of the table this file reports
could not be reproduced by the repository that reported them. **Restored
2026-09-07**, and each one re-derives its recorded number.

**A correction the restoration produced.** This file said ADAPTIVE *"won on
quora (best MRR, 0.730)"* and did not name the embedder. It is **0.732 on
quora/google** and only **0.700 on quora/codestral**. The number was right; the
run it belonged to was missing.

> **Name the corpus AND the embedder beside every number.** Without both, a
> faithful reproduction looks like a contradiction.

#### The rule this produced, and it outranks the numbers

> **Judge a method by how many independent ways it was shown better, never by
> its best single number.**

**BM25 is the worked example on the winning side.** It beat both Postgres
rankers on **every** metric, on **both** corpora, **and** there is a mechanism
that explains why: `ts_rank(tsvector, tsquery)` is handed one document, so it
cannot know document frequency and has no IDF at all. Three independent
supports, all pointing the same way.

**Score fusion is the example on the losing side.** The best average MRR of
anything measured, one run where it lost recall@50, and **no mechanism**. That
is a number, not evidence.

**So the effort goes to `vector`, `wRRF` and `RESCUE`.** The other three stay
in the script so their claims stay reproducible, and none of them is a
candidate. This matters because the instrument here is weak — the fixture is
saturated at recall@50, and both corpora are Python — so convergent evidence
has to do the work that a single metric cannot.

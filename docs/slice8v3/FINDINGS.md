# SLICE 8 v3 — FINDINGS

The zoo is now **20 corpora, 10 Python (50%)**, against v2's 3 of 13 (23%).
Every finding states its **Python share**, per rule 5 of the run, and every
ratio states its **denominator**, per G18.

`scripts/zoo.py` computes the share rather than leaving it to be counted by
hand, because hand-counting denominators is how the G18 errors were made.

---

## H0 — THE ZOO, and what it cost

| corpus | chunks | queries | window@50 | Python |
|---|---|---|---|---|
| websocket | 78 | 15 | 64.1% | — |
| quora | 82 | 17 | 61.0% | **PY** |
| docx | 85 | 12 | 58.8% | — |
| smsspam | 89 | 20 | 56.2% | **PY** *(own)* |
| disaster | 108 | 20 | 46.3% | **PY** *(own)* |
| titanic | 118 | 20 | 42.4% | **PY** *(own)* |
| log | 146 | 20 | 34.2% | — |
| cobra | 193 | 20 | 25.9% | — |
| requests | 335 | 45 | 14.9% | **PY** |
| notebooks | 382 | 20 | 13.1% | **PY** |
| papers | 404 | 20 | 12.4% | — |
| docs | 463 | 19 | 10.8% | — |
| lung | 628 | 17 | 8.0% | **PY** *(own)* |
| jq | 693 | 20 | 7.2% | — |
| geo | 729 | 45 | 6.9% | — |
| gson | 750 | 13 | 6.7% | — |
| zod | 1160 | 20 | 4.3% | — |
| click | 1585 | 20 | 3.2% | **PY** |
| pytest | 6714 | 20 | 0.7% | **PY** |
| **pydantic** | **9846** | **20** | **0.5%** | **PY** |

**423 queries.** The 7 new corpora cost **19,088 chunks / 4.6M tokens on
`codestral-embed`, embedded in ~11 minutes**, plus ~60 Gemma drafting calls.
Nothing old was re-run: the aggregates glob `.logs/results/`, so every table
below is a 20-corpus table built by scoring only the 7 new corpora.

`.logs/results_v2_snapshot/` holds the 88 v2 result files, taken before the
first v3 write.

---

## H1 — SIZE DOES NOT CREATE `r@50` HEADROOM, and the mission's premise for P6/P7 is false

The mission's reason for building a 10,000-chunk corpus:

> *"At 10,000 chunks the top-50 window is 0.5% — the real production ratio —
> and `r@50` will fall a long way below the saturation ceiling."*

**It did not fall.** Measured, with the denominator printed:

| corpus | chunks | window | `r@50` | as queries |
|---|---|---|---|---|
| **pydantic** | **9,846** | **0.5%** | **1.000** | **20/20, missed 0** |
| pytest | 6,714 | 0.7% | 0.900 | 18/20, missed 2 |
| click | 1,585 | 3.2% | 1.000 | 20/20, missed 0 |
| zod | 1,160 | 4.3% | 1.000 | 20/20, missed 0 |
| **geo** | **729** | **6.9%** | **0.867** | **39/45, missed 6** |
| lung | 628 | 8.0% | 0.882 | 15/17, missed 2 |

**The largest corpus in the zoo is saturated and the worst corpus is 13× smaller.**
Across the whole zoo: **423 queries, 16 missed at `r@50` — 3.8%.**

So the top-50 window being 0.5% of the corpus does **not** mean the answer
falls out of it. Retrieval at 10,000 chunks still puts the answer in the top 50
essentially always; what degrades is **where in the 50 it lands**.

**What size does hurt is ORDERING:**

| | MRR |
|---|---|
| pytest (6,714) | **0.446** — the worst in the zoo |
| pydantic (9,846) | 0.530 |
| click (1,585) | 0.577 |
| small Python corpora (89–118) | 0.594 – 0.753 |

> **The large corpora are not a recall instrument, they are an ORDERING
> instrument.** That is reranking's question, not fusion's — which changes what
> the remaining quota should be spent on.

### The honest limit on this finding

A drafted fixture is **biased toward findability**: the drafter is shown a
chunk and writes a question answerable by it, so the question shares that
chunk's semantics by construction. It never filters on whether retrieval
succeeds (that rule is enforced), but the *generation* process still favours
findable questions. `geo` missing 6 of 45 shows the bias is not total, and all
20 fixtures were built the same way so the comparison between them is fair —
but an absolute `r@50` of 1.000 should not be read as "retrieval never misses".

---

## H2 — GEMMA SERVES EVERY PYTHON CORPUS, and v2 concluded the opposite

v2, on 13 corpora with 3 Python:

> *"At `SEARCH_LIMIT = 50` Voyage serves 0 of 13 corpora and both Gemma tiers
> serve 4 of 13 … so the working budget is the two Flash-Lite keys, 1,000 calls
> a day."*

On 20 corpora with 10 Python, the split is **perfect by language**:

| | corpora | Python |
|---|---|---|
| Gemma **serves** at window 50 | **11 of 20** | **10 of 10** |
| Gemma **refuses** | 9 of 20 | **0 of 10** |

The only non-Python corpus Gemma serves is `docs` (Markdown). Every refused
corpus is Go, Rust, C, Java, TypeScript, PDF or Word.

**The mechanism was already in `tier_reach.py`'s own docstring** — no AST
splitter → `split_recursive` packs to the cap → chunks ~2× larger → one
50-document call is ~2× the tokens:

```
Python (AST splitter)         200-280 tokens/chunk   -> ~11,000-14,000 per call
everything else (recursive)   430-477 tokens/chunk   -> ~22,500-24,800 per call
Gemma's ceiling                                          16,000 per MINUTE
```

**So for LabPilot's target language the rerank budget is 28,800 Gemma calls a
day, not 1,000 Flash-Lite calls.** v2 was correct about its own zoo and wrong
about the product.

**This finding was only reachable after a code fix.** `tier_reach.py` held a
hardcoded tuple of the 13 v2 corpus names — the one place the project's
"a corpus is DATA, not code" rule was broken — so the 7 new corpora were
silently absent while every other script picked them up automatically.

---

## H3 — SCORE FUSION CONFIRMS as the best method, on 20 corpora

v2's G17 concluded the method should be **score fusion**, not wRRF. It holds
with the Python half in place — `20 corpora, 10 Python`, MRR against vector:

| ranker | wins | ties | losses | worst | mean |
|---|---|---|---|---|---|
| **score a=0.85** | **14** | 0 | 6 | −0.036 | **+0.026** |
| wRRF k=5 w=0.15 | 9 | 6 | 5 | −0.007 | +0.004 |
| RESCUE m=5 after=20 | 3 | 17 | 0 | −0.001 | +0.000 **never worse** |
| ADAPTIVE k=10 | 9 | 0 | 11 | −0.126 | −0.018 |
| CombMNZ | 6 | 0 | 14 | −0.447 | −0.087 |
| bm25 alone | 1 | 0 | **19** | −0.654 | −0.183 |
| ts_rank alone | 0 | 0 | **20** | −0.664 | −0.210 |

`score a=0.85` is the only method with a positive mean and a bounded worst
case. `ts_rank` loses on **all 20** — the Postgres ranker has now lost on every
corpus this project has ever measured.

---

## H4 — THE HYBRID-SEARCH PREMISE, on 423 paired queries

The claim this project has carried since slice 5: keyword search wins where the
query shares an identifier with the answer (`named`), and on `constant`
questions like *"what is `CLIP_NORM` set to"*.

Paired, query by query, MRR of bm25 against vector:

| | n | bm25 − vector |
|---|---|---|
| `named` | 101 | **−0.156** |
| `paraphrase` | 305 | **−0.201** |

**The direction is right and the magnitude is not.** bm25 does relatively
better on `named` by **+0.045** — exactly as predicted — while still being
0.156 worse than vector there. It never wins; it only loses less.

And the `constant` case, which is the motivating example for the whole keyword
channel, does **not** reproduce:

| kind | n | bm25 − vector | score fusion − vector |
|---|---|---|---|
| api | 63 | −0.226 | −0.029 |
| behaviour | 128 | −0.164 | **+0.044** |
| **constant** | **90** | **−0.226** | **−0.010** |
| error | 56 | −0.136 | **+0.043** |
| structure | 69 | −0.202 | **+0.022** |

`constant` is bm25's **joint worst** category on 90 queries. Score fusion helps
on `behaviour`, `error` and `structure`, and is flat-to-negative on `api` and
`constant` — the opposite of the story the keyword channel was built on.

---

## H5 — TWO FIXTURES WERE MEASURING DUPLICATED MATERIAL, and one query was garbage

Found by reading the drafted queries before spending anything on embedding,
which is the only moment any of this is cheap to fix.

**Duplicated material.** `lung` was **34.8% duplicate chunks, one chunk
repeated 16 times**: `**/mlflow/artifacts/**` holds the same `utils.py` copied
under a different run hash each time. `pydantic` was 6.6%, because
`tests/mypy/outputs/` is a machine-written copy of `tests/mypy/modules/`
re-checked under each mypy config.

Not cosmetic: **4 of `lung`'s 20 drafted queries and 1 of `pydantic`'s were
anchored inside a duplicated file.** Such a query is unanswerable by fair
retrieval — a dozen identical chunks are equally good answers and only one
scores — so it would have depressed recall on two Python corpora for a reason
that has nothing to do with retrieval.

```
lung       958 -> 628 chunks    duplicates 34.8% -> 4.5%
pydantic 10470 -> 9846 chunks   duplicates  6.6% -> 1.8%
```

**A degenerate query, and the validator gains a seventh check.** `titanic`
TI03 was **2,069 characters of "the-the-the-…"** — the drafter fell into a
repetition loop. It passed every existing check: not generic, no leaked
identifier, anchor resolves. A degenerate query embeds to nonsense, so it fails
for every method and costs rerank tokens on every run. `degenerate()` now
catches it, and across all 423 queries it fires **exactly once**.

**Stale metadata, found by `zoo.py`.** `cobra` recorded 408 chunks against a
real 193 and `websocket` 167 against 78 — both the numbers from *before* the
`fnmatch` fix in G1. A size column built from that metadata would have printed
denominators twice the truth. Corrected, and `zoo.py --measure` now re-chunks
to catch drift.

> Three separate instrument defects, all found by looking at the fixture rather
> than at the numbers. G14's lesson holds: a measurement script is exactly
> where nobody looks.

---

## H6 — RERANKING NEVER HURTS, and its benefit COLLAPSES as the corpus grows

**16 corpora, 10 Python, `gemini-3.5-flash-lite` listwise at window 50, 137
new calls.** Each delta divided by what its own fixture can resolve — one query
is 0.050 MRR on a 20-query corpus and 0.022 on the 45-query ones.

| corpus | chunks | q | vector | rerank | delta | queries | |
|---|---|---|---|---|---|---|---|
| requests | 335 | 45 | 0.646 | 0.791 | +0.145 | **+6.5** | PY |
| log | 146 | 20 | 0.662 | 0.960 | +0.298 | **+6.0** | — |
| quora | 82 | 17 | 0.608 | 0.848 | +0.240 | **+4.1** | PY |
| smsspam | 89 | 20 | 0.653 | 0.833 | +0.180 | **+3.6** | PY |
| notebooks | 382 | 20 | 0.528 | 0.698 | +0.170 | **+3.4** | PY |
| cobra | 193 | 20 | 0.634 | 0.794 | +0.161 | **+3.2** | — |
| disaster | 108 | 20 | 0.753 | 0.875 | +0.122 | **+2.4** | PY |
| docx | 85 | 12 | 0.756 | 0.944 | +0.188 | **+2.3** | — |
| pytest | 6,714 | 20 | 0.446 | 0.527 | +0.081 | **+1.6** | PY |
| websocket | 78 | 15 | 0.668 | 0.717 | +0.049 | +0.7 | — |
| click | 1,585 | 20 | 0.577 | 0.585 | +0.008 | +0.2 | PY |
| pydantic | 9,846 | 20 | 0.530 | 0.532 | +0.002 | +0.0 | PY |
| lung | 628 | 17 | 0.587 | 0.584 | −0.004 | −0.1 | PY |
| zod | 1,160 | 20 | 0.802 | 0.775 | −0.027 | −0.5 | — |
| titanic | 118 | 20 | 0.594 | 0.562 | −0.032 | −0.6 | PY |
| docs | 463 | 19 | 0.864 | 0.816 | −0.048 | −0.9 | — |

**9 real gains, 0 real losses, 7 below resolution.** `declined: 0` everywhere,
so no corpus is hiding an abstention. That is a *stronger* result than v2's
"9 gains, 1 loss, 3 nothing" — reranking with flash-lite never measurably hurt
any of the 16.

### But sort the same table by SIZE and it says something else

| | corpora | mean MRR gain |
|---|---|---|
| **under 500 chunks** | **11** | **+0.134** |
| **500 chunks and over** | **5** | **+0.012** |

$$
r\big(\log_{10}\text{chunks},\; \Delta\text{MRR}\big) = -0.493 \quad (n = 16)
$$

**Not one corpus at or above 500 chunks shows a real gain.** lung −0.1q,
zod −0.5q, click +0.2q, pytest +1.6q, pydantic +0.0q. The mean gain on the
large half is **+0.012 MRR — about a quarter of one query**, which is below
what any of these fixtures can resolve.

> **Reranking is measured to help on corpora 10–100× smaller than the artifacts
> LabPilot actually targets, and to do nothing measurable on the ones it does.**

**The v2 zoo could not have seen this.** Its largest corpus was `zod` at 1,160,
and it held only 4 corpora at or above 500 chunks. The whole large half of this
trend is new material, and 4 of the 5 large corpora are the Python ones added
in v3.

### What this does NOT establish

- **n = 5 on the large side.** The correlation is moderate, not decisive.
- **It is confounded with kind.** Every large corpus is a packaged library or
  application; the small half includes prose, Word, and notebooks.
- **It is not saturation.** pydantic's vector MRR is 0.530, so there is ample
  room for a reranker to improve it. It simply does not.
- The honest phrasing is *"no measurable gain at or above 500 chunks"*, not
  *"reranking stops working"*.

### The mechanism this suggests, and the experiment it generates

A plausible reading: on a 9,846-chunk corpus the top 50 are **all plausible** —
a large library repeats its own idioms — so a listwise reranker has no easy
discriminations to make. On a 90-chunk corpus the top 50 contain obviously
wrong candidates, and removing those is most of the measured gain.

If that is right, a **narrower window should help the large corpora**, because
it hands the reranker fewer near-identical candidates. That is measurable, and
it is the one question v2 flagged as having **0% Python** behind it
(`SEARCH_LIMIT` 30 vs 50 — its four w30 corpora are geo, gson, jq and papers,
every one of them non-Python).

**Running now: window 30 on lung, click, pytest, pydantic, zod and smsspam —
6 corpora, 5 Python (83%).**

---

## H7 — THE RERANK WINDOW SHOULD BE 30, NOT 50, and it is the run's clearest decision change

H6's mechanism predicted that a narrower window would help the large corpora,
because it hands the reranker fewer near-identical candidates. **Measured on 6
corpora, 5 Python (83%)** — against v2's `SEARCH_LIMIT` evidence, which was
**4 corpora, 0 Python**.

| corpus | chunks | q | vector | w50 | w30 | w50 queries | w30 queries | better |
|---|---|---|---|---|---|---|---|---|
| smsspam | 89 | 20 | 0.653 | 0.833 | **0.887** | +3.6 | **+4.7** | **w30** |
| lung | 628 | 17 | 0.587 | 0.584 | **0.618** | −0.1 | **+0.5** | **w30** |
| zod | 1,160 | 20 | 0.802 | 0.775 | **0.861** | −0.5 | **+1.2** | **w30** |
| click | 1,585 | 20 | 0.577 | **0.585** | 0.577 | +0.2 | +0.0 | w50 |
| pytest | 6,714 | 20 | 0.446 | 0.527 | **0.569** | +1.6 | **+2.5** | **w30** |
| pydantic | 9,846 | 20 | 0.530 | 0.532 | **0.563** | +0.0 | **+0.7** | **w30** |

**w30 wins on 5 of 6, and on 4 of the 5 corpora at or above 500 chunks.** The
one w50 win, `click`, is +0.2 queries against +0.0 — both below what a
20-query fixture can resolve, so it is a tie in everything but sign.

Two corpora **change sign**: `lung` −0.1 → +0.5 and `zod` −0.5 → +1.2.

### What it costs, measured rather than assumed

A 30-window cannot promote an answer ranked 31st–50th. Across these 6 corpora
and 114 queries:

| corpus | `r@30` | `r@50` | queries lost |
|---|---|---|---|
| click | 0.950 | 1.000 | 1 |
| pydantic | 0.950 | 1.000 | 1 |
| lung, pytest, smsspam, zod | — | — | **0** |

**Cost: 2 queries of 114 (1.8%). Gain: about +4.8 queries of ordering.**
Roughly 2.4 to 1 in favour of the narrower window.

### And it is better on three further axes, independently

```
QUALITY     better ordering on 5 of 6 corpora, 4 of 5 large ones
COST        30 documents instead of 50 - about 40% fewer tokens per call
REACH       Gemma   serves 11 of 20 at w50  ->  20 of 20 at w30
            Voyage  serves  0 of 20 at w50  ->  11 of 20 at w30
BUDGET      Gemma at every corpus is 28,800 calls/day against Flash-Lite's 1,000
```

> **Four independent reasons point the same way**, which is this project's own
> standard for believing a result — judge a method by how many ways it was
> shown better, never by its best single number.

**`RERANK_WINDOW` should be 30.** Note this is the rerank candidate count, not
`SEARCH_LIMIT`: search can keep returning 50, and the cut to 30 happens before
the rerank call. That also makes v2's per-tier window machinery largely
unnecessary — at 30 every tier serves every corpus, so there is nothing left
for a per-tier rule to arbitrate.

### Limits

- 6 corpora, and only two windows were compared. 20 and 40 are unmeasured, so
  30 is *better than 50*, not *optimal*.
- `r@30` vs `r@50` is measured on the vector path; a fused candidate set would
  differ.
- The two windows were compared on one reranker, `gemini-3.5-flash-lite`.

---

## STILL UNMEASURED at this point in the run

| | why it matters |
|---|---|
| reranking on the 7 new corpora | H1 says ordering is the real question, so this is now the priority |
| `SEARCH_LIMIT` 30 vs 50 with Python | 0% Python in v2 |
| Cohere vs flash-lite with Python | 0% Python in v2; 1,000 calls a MONTH |
| the fusion `r@50` threshold | H1 complicates it: almost nothing has `r@50` headroom now |
| `RERANK_TOP_N` | never measured in v2 either |
| merged vs per-side with a Python+Python pair | |
| end-to-end time / `WARN_MINUTES` | still a guess |

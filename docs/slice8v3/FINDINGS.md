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
but an absolute `r@50` of 1.000 should not be read as "retrieval never
misses".

**H8 later MEASURED this bias and found it smaller than feared.** The zoo's
query-answer word overlap is 0.460 on average, and at matched overlap a
hand-written fixture scores the same as a drafted one. So H1 stands as a
statement about questions asked at that overlap; what is unknown is the
overlap real users ask at.

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

## H8 — QUERY DIFFICULTY IS MEASURABLE, and it explains the drafted-vs-hand gap ENTIRELY

**This finding was written once, wrongly, and then overturned by its own
control.** Both the error and the correction came from the user pushing: first
*"maybe your queries are too easy"*, then *"maybe now you made them too
strict"*. Both were right.

### The instrument this was missing

`scripts/query_difficulty.py` measures, per fixture, the share of a query's
content words that also appear in the chunk answering it. Identifiers are split
first (`GenerateJsonSchema` → generate / json / schema), because without that a
question about a json schema scored 0.00 against the class that builds one.

**The drafted zoo, measured:**

```
mean overlap 0.460   sd 0.105   range 0.244 (jq) to 0.672 (docs)
```

The zoo's difficulty was never a known quantity before. It is now.

### The experiment, and the control that decided it

Three hand-written fixtures were built over **byte-identical corpora** —
verified by hashing every chunk's `embed_text`, so the vectors are copied, not
re-embedded. Each question was written **question-first** from what a user of
that project would want to know, then its answer located with `grep`. No model
was involved.

| pair | overlap | MRR | |
|---|---|---|---|
| pydantic drafted | 0.460 | 0.530 | |
| pydantic **hand** | **0.309** | **0.189** | overlap −0.151 → MRR −0.341 |
| pytest drafted | 0.422 | 0.446 | |
| pytest **hand** | **0.350** | **0.129** | overlap −0.072 → MRR −0.317 |
| **lung drafted** | **0.490** | **0.587** | |
| **lung hand** | **0.480** | **0.610** | **overlap −0.010 → MRR +0.023** |

**`lunghand` is the control, and it is the whole finding.** Its overlap happened
to land within 0.010 of its drafted twin — difficulty matched — and at matched
difficulty the hand-written queries score **the same or slightly better**.

> **So the drafted-vs-hand gap is DIFFICULTY, not provenance.** Who wrote the
> question adds nothing once vocabulary overlap is held still. My first two
> hand-written sets simply used fewer of the answer's words.

### What this RETRACTS

An earlier version of this section claimed *"H1 is dead"*, *"H6's causal claim
is overturned"* and *"H7 is weakened"*, all on the pydantic hand fixture before
a difficulty control existed. **All three retractions are withdrawn.** H1, H6
and H7 stand as measured, as statements about the drafted zoo at overlap ≈ 0.46.

### What survives, and it is more useful than the claim it replaces

Across all 22 fixtures:

$$
r\big(\text{query–answer word overlap},\ \text{MRR}\big) = +0.492,
\qquad
r\big(\text{overlap},\ r@50\big) = +0.420
$$

Moderate, not deterministic — `jq` has the lowest overlap in the zoo (0.244) and
a middling MRR of 0.607, so corpus size and domain matter too. Within a **pair**
on one corpus, though, overlap tracked MRR almost exactly, which is why the
control worked.

**The open question this leaves, which nothing here settles:** real users ask
at *some* overlap, and we do not know what it is. The drafted zoo sits at 0.460
and that is now a **documented assumption** rather than a hidden one. If real
questions turn out to sit near 0.30, every absolute number in v2 and v3 is
optimistic — and the pydantic and pytest hand fixtures show what that world
looks like (MRR 0.189 and 0.129).

### Rules this produced, and they bind the rest of the run

1. **A hand fixture is compared ONLY with its own drafted twin on the same
   corpus.** Never across corpora — its difficulty is not calibrated to the zoo,
   and comparing them would confuse provenance with language.
2. **Cross-corpus work uses the 20 uniformly-drafted fixtures**, which is what
   makes H2, H3, H4, H6 and H7 legitimate.
3. **Report a fixture's overlap beside its score**, the same way this project
   already reports the denominator beside a ratio.

### Limits

- Three pairs, one of them difficulty-matched. The control is **n = 1**.
- 20 queries each, so one query is 0.050 MRR.
- The hand questions are mine. A real pytest or pydantic user would write
  different ones, at an unknown overlap.

---

## H9 — RERANKING'S VALUE SCALES WITH QUERY DIFFICULTY, and the matched control is exact

The rerank delta on each paired fixture, same corpus and vectors either side:

| fixture | overlap | vector | + rerank | gain |
|---|---|---|---|---|
| **lung** drafted | 0.490 | 0.587 | 0.584 | **−0.1 q** |
| **lung HAND** | **0.480** | 0.610 | 0.606 | **−0.1 q** |
| pytest drafted | 0.422 | 0.446 | 0.527 | +1.6 q |
| **pytest HAND** | **0.350** | 0.129 | **0.441** | **+6.2 q** |
| pydantic drafted | 0.460 | 0.530 | 0.532 | +0.0 q |
| **pydantic HAND** | **0.309** | 0.189 | **0.320** | **+2.6 q** |

**At matched difficulty the rerank gain is identical to three decimals**
(−0.004 both ways on `lung`). H8's control therefore holds on a second,
independent metric, which closes the provenance question: who wrote the
question changes nothing once difficulty is held still.

And the other two rows give the law:

> **The harder the question, the more reranking is worth.** `pytesthand` at
> overlap 0.350 goes 0.129 → 0.441, a 3.4× improvement and **+6.2 queries —
> the largest rerank gain measured anywhere in this project.**

The mechanism is the obvious one: an easy query already has its answer at rank
1, so there is nothing to reorder. Reranking is paid for exactly when retrieval
is struggling.

**The consequence for the product, and it is the useful part:** if real user
questions are harder than the drafted zoo's 0.46 overlap, **reranking is worth
MORE than any number in v2 or v3 suggests, not less.** That strengthens the
decision that reranking ships.

### It also rescues H6 from a confound

H6 found rerank gain falling with corpus size. Difficulty could have caused
that, so it was tested rather than assumed — partial correlation over the 15
drafted corpora with a w50 run:

```
r(size, rerank gain)            = -0.445     H6 as reported
r(size, overlap)                = -0.217
r(overlap, rerank gain)         = +0.192
PARTIAL r(size, gain | overlap) = -0.421     difficulty held still
```

**H6 barely moves.** And large corpora have slightly *harder* queries, so the
confound worked against H6 rather than creating it. Both effects are real and
independent: gain falls with size, and gain rises with difficulty.

---

## H10 — THE ZOO IS NOT UNIFORM IN DIFFICULTY, and that is reported rather than fixed

Measured over the 19 drafted fixtures:

```
overlap   min 0.244 (jq)   max 0.672 (docs)   2.8x spread
          mean 0.460       sd 0.105
```

**This is inherited from v2, not introduced by v3.** It was never visible
before because nothing measured it.

**Why it does not invalidate the method comparisons.** Every cross-corpus
finding here is a **delta within one corpus** — method A against method B on
the same queries — so a corpus being easy or hard cancels. H9's partial
correlation demonstrates this on the finding most exposed to it.

**Where it does bite: ABSOLUTE numbers.** *"pydantic `r@50` = 1.000"* means
*"at overlap 0.46"*, not *"in general"*. Such a number must never be read
across corpora.

**The decision taken (the user's call): control for it and report it, rather
than re-draft ~400 queries to a target.** Re-drafting would mean drafting,
measuring, discarding and redrafting — and discarding queries by a
retrieval-adjacent metric is close to the one thing this project forbids,
building a fixture that agrees with our own embedder.

So `scripts/zoo.py --difficulty` prints the overlap range of any subset, and
**every row of `DECISIONS.md` carries the difficulty its evidence was measured
at**, beside its Python share.

A second non-uniformity, already handled: **query counts run 12 to 45**, so one
query is 0.083 MRR on `docx` and 0.022 on `geo`. That is resolution, not
difficulty, and every delta in this document is already judged against its own
fixture's resolution per G18.

---

## H11 — THE RE-OPTIMISATION PASS: searching, not validating

**Written after the user caught a real methodological failure.** Everything in
H1–H10 tested **v2's chosen values** on the new corpora. It never searched for
better ones. The user's objection: a zoo that went from 3 Python of 13 to 10 of
20, and from a 1,160-chunk ceiling to 9,846, may have moved the *optimum* and
not merely the score.

They were right. What I had actually run was `score_hybrid.py <corpus>
codestral` with **no flags**, which pins every knob at v2's winner:

```
wRRF k      5        (available: 5, 10, 20, 30, 60)
wRRF w      0.15     (available: 0.05 .. 1.0, eight values)
score alpha 0.85     (available: 0.7, 0.85, 0.95)
BM25 k1, b  1.2,0.75 (a whole grid, never swept on ANY corpus, ever)
window      30, 50   (a nine-point ladder exists)
embedder    codestral only
```

### Result 1 — FUSION: `score a=0.85` wins a 51-way search

20 corpora, 10 Python, every setting scored on all of them:

| setting | mean MRR | worst | win/loss |
|---|---|---|---|
| **score a=0.85** ← shipped | **+0.0289** | −0.029 | 14 / 5 |
| score a=0.95 | +0.0133 | −0.029 | 11 / 6 |
| wRRF k=5 w=0.3 | +0.0132 | −0.014 | 10 / 7 |
| *wRRF k=5 w=0.15* ← v2's other candidate | *+0.0044* | −0.008 | **ranks #11** |

**`CONFIRMED`, and for the first time earned rather than inherited.** One real
correction inside it: `wRRF k=5 w=0.15` was never the best wRRF — `k=5 w=0.3`
is three times better. Immaterial, since all wRRF loses to score fusion, but it
shows the sweep was doing work.

### Result 2 — BM25 `k1`/`b`: the knobs barely matter

Never swept on any corpus in this project's history. 20 corpora, 10 Python:

```
k1=1.2 b=0.75   fusion MRR +0.0256   <- shipped, best
k1=0.9 b=0.75              +0.0249
k1=1.2 b=0.30              +0.0229
k1=1.2 b=0.00              +0.0227
k1=2.0 b=0.75              +0.0222
k1=1.6 b=0.75              +0.0219
```

**All six settings span 0.0037 MRR** — far below any fixture's resolution
(one query is 0.022 to 0.083). So the honest verdict is *"indistinguishable,
and the textbook default is not beaten"*, **not** *"the default is best"*.
`CONFIRMED`, weakly, and the weakness is the finding.

### Result 3 — EMBEDDER: codestral beats mistral 19 of 20

| | mean MRR | mean r@50 |
|---|---|---|
| **codestral-embed** | **0.634** | **0.967** |
| mistral-embed | 0.514 | 0.934 |
| Python only (n=10) | **0.592** vs 0.466 | |

And the margin is **widest on the largest corpus**: `pydantic` +0.239,
`click` +0.147, `pytest` +0.101. `CONFIRMED` on the full new zoo.

**Scope limit, and it is a hard one rather than a choice.** Google's embedder
counts **one text as one request** against 1,000/day — v2's production defect
#2 — so embedding 19,088 new chunks there is **19 days**. Cohere is 198 calls
of a 1,000-a-MONTH tier shared with reranking. Both can therefore only be
measured on the small Python corpora, and that scope is stated on the decision
row rather than left to look fuller than it is.

### The rule this pass earned

> **Re-testing a chosen value is not measuring it.** A config inherited from a
> different corpus population is an assumption wearing a number's clothes, and
> the only way to tell the two apart is to search the space again on the
> population you actually have.

---

## H12 - THE WINDOW SWEEP FINISHES H7, and the answer moves from 30 to 20

H7 compared **two** windows and said so in its own limits: *"20 and 40 are
unmeasured, so 30 is better than 50, not optimal."* Six windows were then run,
on **5 corpora that are 100% Python**, spanning 89 to 9,846 chunks, flash-lite.

| corpus | chunks | w5 | w10 | w20 | w30 | w40 | w50 | best |
|---|---|---|---|---|---|---|---|---|
| smsspam | 89 | +0.147 | +0.222 | +0.264 | +0.234 | **+0.277** | +0.180 | w40 |
| lung | 628 | +0.011 | **+0.099** | +0.054 | +0.030 | +0.019 | -0.004 | w10 |
| click | 1,585 | -0.021 | -0.023 | **+0.011** | +0.000 | - | +0.008 | w20 |
| pytest | 6,714 | -0.013 | **+0.129** | +0.123 | +0.123 | +0.117 | +0.081 | w10 |
| pydantic | 9,846 | **+0.079** | +0.049 | -0.003 | +0.033 | -0.016 | +0.002 | w5 |

```
w10 +0.095   w20 +0.090   w30 +0.084   w50 +0.053   w5 +0.041
(w40 reads +0.099 on 4 corpora and is MISSING click - flattered, not compared)
```

**The shipped w50 is nearly half as good as the best**, and w10/w20/w30 are
indistinguishable: +1.84, +1.76 and +1.67 queries, a spread of **0.17 queries**
against a bar of 1.5. So H7's direction holds and its number does not.

**`RERANK_WINDOW = 20`** - the middle of the flat region, fewer tokens per call
than 30 so more tiers stay reachable, and within noise of the best.

**The per-corpus optimum is everywhere**: w5, w10, w20 and w40 each win
somewhere, and the spread WITHIN one corpus (pydantic +0.079 at w5 against
-0.016 at w40) is larger than the spread between the window means. A global
window is a compromise, and this is the measurement that says so out loud.

> **Two points make a direction, never an optimum.** H7 was right that 50 is
> wrong and wrong about where to stop, because a two-point comparison cannot
> see a flat region - it can only see which of the two points is higher.

### And `--window` is not `SEARCH_LIMIT`, verified in the source

`vector_candidates = dense[q.id][:window]` - it is what the **reranker sees**.

```
search             -> 50   SEARCH_LIMIT
top 20 of those 50 -> 20   RERANK_WINDOW   <- what H7 and H12 measured
reranked, sent     -> 10   RERANK_TOP_N    <- still unmeasured
```

---

## H13 - `SEARCH_LIMIT` IS A CEILING, and lowering it buys nothing we need

Never swept in v2 or v3. It deserves its own finding because it is not like the
other knobs: an answer outside `SEARCH_LIMIT` **can never be recovered** by
fusion, by reranking or by any later stage. Over **20 corpora, 423 queries**,
vector alone:

| `SEARCH_LIMIT` | mean recall | queries lost of 423 |
|---|---|---|
| 10 | 0.864 | **45** |
| 20 | 0.930 | 16 |
| 25 | 0.951 | 8 |
| 30 | 0.957 | 5 |
| **50** | **0.968** | **0** |

The only thing a smaller limit buys is database time, and exact search measures
**~11 ms at 1,387 rows** against a 350 ms VPN round trip and a ~50 s report.

**There is no trade to make. `SEARCH_LIMIT` stays 50.** Note this is not the
same question as H12: the window narrows what the *reranker* reads, which costs
provider tokens; the search limit narrows what *exists*, and costs answers.

**Going ABOVE 50 is the untested direction** and is not free - it is more
storage read, more fusion arithmetic, and a longer list for the window to cut.

---

## H14 - THE CHUNKER WAS RE-SEARCHED, and the HEADER is the biggest effect in it

Three sweeps, all free over cached vectors, all searched on the new zoo rather
than re-tested at v2's chosen values.

**Size** - re-run 2026-09-19 on **TWELVE corpora, 8 of them Python**, against
the first pass's 7 with 3 Python. It includes `pytest`, the run that died at
5,760 of 9,839 chunks on a Mistral 503 the first time it was attempted:

| setting | MRR | r@10 | r@50 | Python only, MRR |
|---|---|---|---|---|
| s=250 o=50 | 0.5352 | 0.8128 | 0.9675 | 0.5495 |
| s=375 o=50 | 0.5715 | 0.8272 | 0.9633 | 0.5803 |
| **s=500 o=50** | **0.6057** | **0.8540** | 0.9633 | **0.5982** |
| s=750 o=50 | 0.5929 | 0.8480 | 0.9766 | 0.5848 |
| s=1000 o=50 | 0.5841 | 0.8295 | **0.9826** | 0.5957 |

**`s=500` wins MRR and `r@10` on both scopes**, and the shape is unchanged from
the 7-corpus pass.

`pytest` alone mildly prefers 750 (0.4631 against 500's 0.4463), but everything
from 375 to 1000 sits inside 0.017 there - **a third of one query** on a
20-query fixture - while `s=250` is clearly worse at 0.3804. So it is one more
corpus agreeing that only the SMALL end is a real mistake.

**`s=500` is confirmed on 12 corpora, and it was searched rather than assumed.** But read the
last column before quoting the first: **MRR peaks at 500 while `r@50` keeps
climbing to 1000.** Bigger chunks FIND more and ORDER worse.

> That is the third time this run one shape has appeared - BGE on `lung` (r@50
> 0.941 against codestral's 0.882, MRR -0.200), Cohere, and now chunk size.
> **Recall and ordering are different axes, and a change that buys one
> routinely sells the other.** It also means `s=500` is only right *while a
> reranker runs*: with no reranker, ordering is all we have.

**Overlap** - re-run 2026-09-18 on **SEVEN Python corpora**, not the three the
first pass had:

| setting | MRR | r@10 | r@50 |
|---|---|---|---|
| s=500 o=0 | **0.6302** | 0.8381 | 0.9645 |
| s=500 o=25 | 0.6260 | 0.8608 | **0.9884** |
| s=500 o=50 | 0.6199 | **0.8640** | 0.9800 |
| s=500 o=100 | 0.6159 | 0.8608 | 0.9729 |

Every MRR sits inside **0.014** - below resolution, so overlap decides nothing
on ordering. The one real signal is `r@50`: `o=0` costs 0.024 against `o=25`,
roughly **3-4 queries** across these corpora. No overlap really does cut answers
in half. `o=25`, `o=50` and `o=100` are indistinguishable, so **`o=50` stays**,
because nothing measurable argues for moving it.

> **And look at the direction of the two columns.** MRR falls monotonically as
> overlap rises, 0.6302 -> 0.6159, while `r@50` peaks in the middle. More
> overlap means more near-duplicate chunks: easier to FIND the answer, harder to
> ORDER it. **That is the fourth appearance of one shape in this run** - BGE,
> Cohere, chunk size, and now overlap.

**The header** - the same seven corpora, chunk text with and without its
`[file - symbol - lines]` prefix:

| | MRR | r@10 | r@50 |
|---|---|---|---|
| **s=500 o=50 +header** | **0.6199** | **0.8640** | **0.9800** |
| s=500 o=50 bare | 0.5507 | 0.8472 | 0.9605 |

**+0.069 MRR, and it wins on 6 of 7 corpora** - the largest single effect in the
whole chunking pass, and far larger than anything size or overlap moved:

```
titanic  +0.210    disaster +0.085    smsspam +0.083    click +0.080
requests +0.033    lung     +0.027    notebooks -0.035
```

The header costs about 20 tokens a chunk and is built from metadata we already
hold.

> **The cheapest thing in the chunker is the one that matters most.** Both
> parameters people tune were worth less than the free string we prepend.

**The one loss is worth naming rather than averaging away.** `notebooks` is
−0.035, and `titanic` - the other notebook corpus - is **+0.210**, the largest
gain of the seven. Two corpora of the same format at opposite ends means the
header's value is not a property of the format, and n=2 cannot say what it is a
property of. Recorded, not explained.

---

## H15 - THE EMBEDDER GATE, and `MIGRATION` ordered by somebody else's numbers

Two production defects, both found by running into them rather than by reading.

**The gate could not see Google's real limit.** `Rate` modelled a token budget
and a call budget. Google's limit is **neither**: one TEXT is one request, so a
96-text `batchEmbedContents` call spends 96 of the day's 1,000.

```
embedding_minutes() predicted    163 minutes for a 20,000-chunk Google ingest
the truth                        twenty DAYS
```

So the walk chose Google, started, and died part way through an ingest that
cannot be resumed. **Measured twice the same day** - a `gemini-embedding-2`
warm failed on its SECOND corpus, and `001` exhausted after 943 chunks.

Fixed with a fourth field, `daily_text_budget`, and a gate in
`embedding_minutes()` that returns `inf` - which is what removes a model from
the walk. **An unknown is not a promise, and neither is a budget in the wrong
units.**

**`MIGRATION` was ordered partly on MTEB.** `mistral-embed` sat THIRD, above
three better models, inside a tuple whose own comment called it *"the strength
order"*; and `gemini-embedding-2` sat above `001` on Google's version number
and Google's MTEB mean. Measured on the 20-corpus zoo:

```
codestral 0.634 > gemini-001 0.602 > cohere 0.593 > gemini-2 0.563 > mistral 0.511
```

Head to head, mistral wins **1 of 7** against gemini-001, **3 of 13** against
cohere, **4 of 11** against gemini-2. And gemini-2 loses to 001 on 3 of the 4
corpora where both ran. Both were reordered, and both are now pinned by a test
so the order stays a decision somebody took on evidence.

> v2's G21 had already reached the gemini-2 verdict **and the code was never
> changed.** A finding written in a document and not in a test is a finding
> that will be re-derived.

---

## H16 - TOP-N, 18 CORPORA AND ONE MODEL - and Python gets less out of context

### FIRST, A CORRECTION TO THIS SECTION ITSELF — I read a stale result file

The first version of this writeup used `.logs/results/answers_flashlite.json`
and reported three "damaged cells" in it: `papers` N=30, `zod` N=30 and `geo`
N=10, each with `answered > 0` and `cited == 0`, so `correct` was 0 by
construction.

**They are not a defect in v2's measurement. They are a defect in the file I
chose.** The citation regex was fixed twice on the morning of 2026-09-17 —
`9e43ae4` at 11:42 and `b60e865` at 11:48 — and the run file was written at
11:49, mid-fix. A regrade pass eight minutes later produced
**`answers_regraded.json`**, and the two differ in **62 of 75 cells**, always in
the same direction:

```
websocket N=30   cited 12 -> 14    correct  8 -> 10
quora     N=50   cited 14 -> 17    correct 11 -> 14
docx      N=30   cited 10 -> 12    correct  8 ->  9
```

**The regraded file has ZERO damaged cells**, and it was the correct one all
along. The project had already found this bug, fixed it, and regraded; I picked
up the pre-fix artifact sitting next to the fixed one.

> **A results directory with two files for one run is a trap, and the newer
> name does not always win.** `answers_flashlite.json` reads like the canonical
> file and `answers_regraded.json` reads like a side experiment. It is the other
> way round.

`scripts/combine_topn.py` now points at the regraded file, and it **keeps** the
`answered > 0 and cited == 0` check — that check did its job here: it fired, and
what it was really detecting was that I was reading the wrong file.

**The three cells were also re-run live today, which is how the stale file was
caught.** Against the regraded values:

| cell | regraded | re-run today |
|---|---|---|
| papers N=30 | 10 correct | **10** |
| geo N=10 | 6 correct | **6** |
| zod N=30 | 8 correct | **14** |

Two of three reproduce exactly. The third moves by 6 questions of 20, which is
**run-to-run variance on one cell** and is the honest bound on how much a single
cell can be trusted.

### The result — 18 corpora, 8 Python, 383 questions, one model, regraded

```
correct / asked      N=10 0.245   N=20 0.462   N=30 0.512
per-corpus mean      N=10 0.278   N=20 0.490   N=30 0.535
corpora won          N=10 0       N=20 5       N=30 8      tied 5
```

**N=10 is eliminated outright** — it wins on **zero** corpora of 18 and loses on
every slice. **N=30 beats N=20** on the pooled share, the per-corpus mean, and
head-to-head wins.

### v2's 13 carry N=50 and N=100, and NOTHING turns over

Coverage and **precision** printed separately, because more context makes the
model decline less as well as answer better:

| N | correct/asked | answered/asked | **correct/answered** |
|---|---|---|---|
| 5 | 0.105 | 0.157 | 0.667 |
| 10 | 0.238 | 0.413 | 0.576 |
| 20 | 0.476 | 0.710 | 0.670 |
| 30 | 0.556 | 0.790 | 0.704 |
| 50 | 0.633 | 0.857 | 0.739 |
| **100** | **0.707** | **0.905** | **0.781** |

**Both columns rise to the end.** On this population there is no measurable
dilution penalty at all up to 100 chunks — precision *improves* with more
context, which is the opposite of "lost in the middle".

> An earlier version of this section claimed precision peaked at N=30 and called
> it the project's first measured dilution penalty. **That was the stale
> grading, and it is retracted.** On the regraded data the curve does not turn
> over anywhere on v2's 13 corpora.

### PYTHON SCORES LOWER AT EVERY N, and only Python shows dilution at all

| slice | N=10 | N=20 | N=30 | precision @30 |
|---|---|---|---|---|
| **10 non-Python** | 0.289 | 0.544 | **0.574** | **0.750** |
| **8 Python** | 0.196 | 0.369 | **0.441** | 0.541 |
| the 5 NEW Python corpora | **0.268** | **0.423** | 0.381 | 0.487 |
| above 5,000 chunks (2 corpora) | 0.275 | **0.375** | 0.250 | — |

At every N, **non-Python answers far more questions correctly and is ~0.21 more
precise at N=30**. The gap is the finding, and it survives the regrade
unchanged.

And the only slices where more context *hurts* are Python: the five corpora this
run added turn over at N=20 with precision falling monotonically (0.591 → 0.526
→ 0.487), and the two corpora above 5,000 chunks fall hardest (0.375 → 0.250).

> **v2's population and the large-Python population disagree about how much
> context to send, and neither is wrong.** A conclusion drawn from 3 Python
> corpora of 13 was a conclusion about Go, C, Java, TypeScript and prose.

### What this decides, and what it does not

**This experiment picks its chunks by VECTOR SEARCH ALONE** — `chosen()` reads
`dense_orders` and no reranker touches it — so it measures **`VECTOR_TOP_N`**
and says nothing directly about `RERANK_TOP_N`.

```
VECTOR_TOP_N = 25   CONFIRMED - it sits at the knee, between the 20 the large
                    Python corpora want and the 30+ everything else does. v2's
                    own unshipped "should be 10" is OVERTURNED: 10 is the worst
                    of the three values on every slice and wins nothing.
RERANK_TOP_N = 10   STILL UNMEASURED, by anyone.
```

**`RERANK_TOP_N` is untouched.** Reranked chunks are better ordered, so their
optimum is at most this one and may be lower — an argument, not a number.

### Limits

- **One model**, `gemini-3.5-flash-lite`, throughout.
- **N coverage is uneven.** 5..100 on v2's 13 corpora, 10..30 on the new 5, so
  the N=50 and N=100 rows are 13 corpora with 3 Python — the old skew, in the
  one place this run could not remove it.
- **13 of the 18 corpora are v2's cached run, deliberately re-used.** Same
  model, same script, same fixtures, and the grader is now the same too. Three
  cells were re-run as a spot check; two reproduced exactly.
- **One cell moved by 6 questions of 20 on a re-run**, so a single cell is not
  evidence. Only the pooled and per-corpus figures are.
- **The Python turn-over rests on 5 corpora and 97 questions**, driven by
  `pydantic` (9 → 5) against `lung` (7 → 10). The direction agrees with the size
  buckets; its size is not settled.

---

## H17 - THE CORPUS WE MEASURE IS NOT THE ONE THE PRODUCT BUILDS

Every corpus in the zoo is **one language** - `**/*.py`, `**/*.go`. That was the
right choice for comparing embedders, windows and fusion, because it holds the
material constant while one knob moves. It is **not what a user gets**:
`POST /artifacts` walks a repository with `sources.walk()`, which reads 58
suffixes and skips by directory, size, secret suffix and machine-written
content.

So the same queries were scored against the corpus **the product itself would
store** - the real walk, the real loaders, the real refusals.

**Re-run 2026-09-19 after the ingest gates shipped**, so the `real` column is
what the product stores today - junk directories skipped, duplicate chunks
dropped with the newest copy winning:

| corpus | what it is | chunks | MRR | delta | duplicates dropped |
|---|---|---|---|---|---|
| **pytest** | a library, code only | 6,714 → 10,039 | 0.446 → 0.443 | **−0.003** | 25 |
| disaster | personal ML app | 108 → 496 | 0.753 → 0.683 | −0.070 | 1 |
| click | a library | 1,585 → 1,995 | 0.577 → 0.477 | −0.100 | 2 |
| smsspam | personal ML app | 89 → 389 | 0.653 → 0.538 | −0.115 | 0 |
| **titanic** | **3 versions of ONE notebook** | 118 → 278 | 0.594 → 0.305 | **−0.289** | **67** |
| lung | — | **REFUSED** | — | — | — |

```
pooled, 5 scored corpora        MRR 0.605 -> 0.489   -0.116
without titanic                 MRR 0.607 -> 0.535   -0.072
before the gates shipped                             -0.136
```

**The gates buy +0.020 pooled, and all of it is on one corpus.** That is the
right shape rather than a disappointing one: `click` had 2 duplicate chunks and
`pytest` 25, so a clean library has almost nothing to drop. The notebook folder
had 67, and recovered a third of its gap.

**`pytest` gained 3,350 chunks and lost 0.004.** So "more content is worse" is
not the finding, and a first draft of this section that said *"every corpus is
worse, not one is better"* was **wrong and is retracted**. On a real library the
fixture is accurate.

### `titanic` IS NOT A NOTEBOOK FINDING, and that is the correction that matters

Notebooks are this product's main use case, so a −0.389 on the one notebook
corpus needed explaining rather than averaging. Three corpora were built from
the same repository:

| | chunks | MRR | r@10 |
|---|---|---|---|
| the fixture: one notebook | 118 | **0.594** | 0.950 |
| **the SAME notebook, via the real walk** | 118 | **0.594** | 0.950 |
| the whole real folder | 345 | 0.205 | 0.750 |

**Take the same notebook out of the real walk and the score is identical to the
fixture.** Notebook content, cell splitting, markdown prose and stored outputs
cost exactly nothing.

The folder holds **three versions of one notebook**, plus Jupyter's auto-save:

```
titanic_analysis.ipynb        126 chunks   an older version
titanic_analysisV2.ipynb      118 chunks   <- the answer key names THIS one
titanic_V2.ipynb               94 chunks   another version
.ipynb_checkpoints/...        118 chunks   auto-saved copy (now skipped)
```

Counting what outranks the correct chunk, across all 20 queries - **75
competitor slots**:

```
39   titanic_analysis.ipynb     a DIFFERENT VERSION of the same notebook
21   titanic_analysisV2.ipynb   the right file, a different chunk
13   titanic_V2.ipynb           another version
 2   README.md                  the only genuinely different content
```

And every query moves the same way - rank 1-2 becomes rank 3-6, the signature of
*two more copies of the answer sitting above it*.

> **Retrieval did not fail. The SCORE did.** The model found the right content
> every time; it found it in a file the answer key does not name, so a correct
> hit was recorded as a miss.

Removing Jupyter's checkpoint alone moved it only 0.185 -> 0.205, and dropping
every EXACT duplicate chunk took it to 0.305. **The last 0.289 is
near-duplicates**: the three versions differ by small edits, so a hash cannot
see them. MinHash or SimHash would, and is not built.

### The real risk behind the artifact, and it is worse than a number

> With three versions in one folder, LabPilot can retrieve the **old** notebook
> and compare the paper against code the user replaced months ago - confidently,
> with a citation.

For a tool whose entire job is explaining **why two things diverge**, comparing
against a stale version is the worst failure it has. The `.ipynb_checkpoints`
skip shipped today fixes Jupyter's auto-save and **does not fix this**:
`titanic_analysis.ipynb` and `titanic_V2.ipynb` are real files a user may want.

Two candidate designs, neither built:

1. **Prefer the newest** when two chunks are near-identical, breaking the tie on
   modification time.
2. **Say it out loud** - *"3 near-copies of this notebook were found; I used
   `titanic_analysisV2.ipynb`"* - which is this project's existing rule that a
   degraded answer must never be silent.

### THE PRODUCT REFUSES ONE OF THE USER'S OWN REPOSITORIES

`lung` has no row because it cannot have one:

```
sources.walk -> SourceTooLarge: lung holds more than 20,000,000 bytes
                of readable text
```

**`MAX_TOTAL_BYTES` is 20 MB and this repository is over it.** LabPilot refuses
the whole ingest, while our fixture has been scoring 628 chunks of it all run.
A product decision, not a measurement one, and recorded rather than fixed: the
limit exists for the 512 MB memory budget, and moving it is a Step 3 question
about where ingest runs.

**A refusal must never be pooled as a 0.000.** The first version of this script
did exactly that and dragged the pooled delta from −0.136 to −0.216 - a product
refusal masquerading as a bad score.

### What it does NOT overturn

**No comparison in this run changes.** Every knob - fusion, the embedder, the
window, chunk size, the header - was measured with the SAME material on both
sides, so a relative result survives a shift that moves both.

What moves is the **absolute** level, and honestly stated it is smaller than it
first looked: **about −0.07 MRR on personal projects, ~0 on a library**, plus one
corpus whose number was an artifact and one repository that cannot be ingested.

### Limits

- **5 corpora scored, one refused**, all Python.
- `smsspam` is the clean case and even there **51%** of what outranks the answer
  comes from files the fixture already had - so part of the shift is re-ordering
  rather than new competition.
- Ground truth survives because it is stored as **file + line**, and it was
  checked: 0 queries lost their target, 0 gained one, no basename clashes. A
  fixture keyed by chunk index could not have been re-scored at all.
- `scripts/score_real_ingest.py` repeats it. A widened `include` glob was tried
  first and is wrong twice over - globs know nothing about `SKIP_DIRECTORIES`
  (`disaster` came out at **400,497** chunks, almost all `node_modules`), and
  `corpora.chunks_for` lets `LooksGenerated` escape where the product counts it
  as a skip, so one minified file aborted a whole corpus.

---

## H18 - EXCLUDING TESTS BY DEFAULT WOULD DESTROY ANSWERS, and the data is not close

The obvious next ingest gate after junk directories and duplicates is *"drop
the tests and the docs, they are noise competing with the source"*. The user
refused it outright - *"maybe user wanna ask about them!"* - and asked for a
condition instead.

**They were right, and by more than anyone guessed.** Each kind was dropped from
the corpus the real walk builds and the same queries re-scored. Free: every
vector was already cached, and dropping chunks only removes rows.

| corpus | mix (source / test / doc / config) | without tests | without docs | without config |
|---|---|---|---|---|
| smsspam | 186 / 127 / 60 / 16 | **+0.069** | +0.019 | +0.000 |
| disaster | 446 / 0 / 45 / 6 | — | +0.035 | +0.003 |
| click | 753 / **831** / 384 / 29 | **−0.045, 11 QUERIES LOST** | +0.111, 1 lost | +0.000 |
| pytest | 2,507 / **4,170** / 3,327 / 60 | **−0.174, 11 QUERIES LOST** | +0.005 | +0.000 |

### "QUERIES LOST" is the whole finding

On `click` and `pytest`, **11 of 20 questions have their answer INSIDE a test
file.** Excluding tests does not make those questions harder - it makes them
**unanswerable**, and the tool would have to say *"not found"* about something
sitting in the repository it was given.

> **More than half the questions people ask about a library are answered by its
> tests.** That is not a surprise on reflection - a test is the executable
> statement of what the code is supposed to do, which is exactly what a
> divergence tool is looking for.

And the counter-example was already on the table and had been read past:
**`pytest` is a corpus that is mostly tests, and it lost 0.004 MRR on the real
walk** - the smallest drop of any corpus measured. If tests were noise, the
corpus made of them should have been the worst.

### Docs are a small real gain, and still not worth a default

`click` gains **+0.111** without its 384 doc chunks, which is the largest single
number in the table - and it loses a query doing it. The other three gain
+0.005 to +0.035. So docs are mild noise **on average** and carry answers **some
of the time**, which is the worst shape for a hard rule.

### Config is worth exactly nothing

**+0.000 on three corpora of four**, for 6 to 60 chunks. Not a lever.

### THE DECISION: no content-kind exclusion at ingest, in any form

```
tests    NEVER exclude - 11 of 20 queries on two corpora die
docs     small average gain, and it costs answers. NOT by default
config   +0.000. no effect to buy
```

**And the shape of the rule matters as much as the answer.** A kind-based rule
would have to be evaluated at INGEST, before the question exists - the same
defect that killed v2's fusion threshold (decision 1): a condition that needs
information production does not have at the moment it must be applied.

If this is ever wanted, it belongs at **search** time, where the question is
known, and it needs **no schema change**: `source` is already a column, so a
filter is a `WHERE` clause. Deciding when to apply it is the Step 2 planner's
job - it is the only layer that knows which capability is running.

> **The gates that worked are about what is REDUNDANT - a build directory, a
> stale duplicate. The gate that failed is about what is RELEVANT, and
> relevance is a property of the question, not of the file.**

### Limits

- 4 corpora, 80 queries, vector search alone.
- The classifier is a path regex - `tests/`, `test_`, `conftest`, `.md`,
  `.rst`, `.yml` - so `pytest`'s `testing/` directory counts as tests, which is
  correct for it and may not generalise.
- These queries were drafted against corpora that already included tests, so
  they are not biased toward or against them by construction.

---

## PARKED — CONTENT-KIND FILTERING, to be re-tested at the END of the run

The user's call, 2026-09-19: *"kinda optional... worth to check after every
other thing is completed."* Agreed, and parked here so it is not lost.

H18 rejected the HARD rule (always exclude tests). Three softer variants are
worth one pass each, on **more corpora than the four measured so far**:

| # | variant | what is already known |
|---|---|---|
| 1 | exclude tests only when tests are a MINORITY of the corpus | pooled **+0.033**, no corpus harmed — but the threshold was fitted to **4 corpora**, which is the trap this project has fallen into before |
| 2 | exclude tests for personal projects, keep them for libraries | the same rule as 1, named by intent rather than by ratio. Needs a way to TELL them apart that is not the ratio |
| 3 | **remove DOCS only, keep tests** — the simplest | smsspam +0.019, disaster +0.035, click **+0.111**, pytest +0.005 → **pooled ≈ +0.043**, and **1 query of 80 lost** on click |

**Variant 3 is the best-behaved and the least clever**, which is usually the
right combination. Its one flaw is the one that matters: a lost query means the
tool says *"not found"* about something in the repository.

**So test variant 3 in its DEMOTE form as well** — weight doc chunks below 1.0
rather than removing them. Nothing can be lost by construction, and the
measurement then only has to choose the weight.

**The bar for shipping any of them: ~10 corpora, not 4.** All three are free to
test - every vector is cached and filtering only removes rows -
`scripts/score_content_kinds.py` is the instrument.

---

## STILL UNMEASURED at this point in the run

| | why it matters |
|---|---|
| reranking on the 7 new corpora | H1 says ordering is the real question, so this is now the priority |
| ~~`SEARCH_LIMIT` 30 vs 50 with Python~~ | **DONE - H13.** 50 stays; 30 loses 5 queries of 423 and buys nothing we are short of |
| Cohere vs flash-lite with Python | 0% Python in v2; 1,000 calls a MONTH |
| the fusion `r@50` threshold | H1 complicates it: almost nothing has `r@50` headroom now |
| `RERANK_TOP_N` | never measured by anyone. H16 settles `VECTOR_TOP_N` and cannot speak to this one: its chunks are picked by vector search alone |
| ~~merged vs per-side~~ | **CLOSED.** v2 measured it: merged starves a side entirely on 43 of 57 queries. Dropped from the queue 2026-09-19 |
| ~~the all-suffix corpus~~ | **DONE - H17.** Every corpus is worse on the real walk, and `lung` is REFUSED outright |
| end-to-end time / `WARN_MINUTES` | still a guess |

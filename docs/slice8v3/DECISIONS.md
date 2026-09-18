# SLICE 8 v3 — DECISIONS

**Every decision, re-taken on the new zoo.** Not only the ones that moved — a
decision that survives a fresh search is worth more than one that was never
re-asked, and the two are indistinguishable unless both are written down.

```
the zoo      20 corpora, 10 PYTHON (50%), 423 queries
v2's zoo      13 corpora,  3 Python (23%), 286 queries
```

**The two rules the user set for this run, and they bind every row below:**

> **Do not re-test v2's chosen values — SEARCH the space again.** A config
> inherited from a different corpus population is an assumption wearing a
> number's clothes.

> **Do every measurement under the new condition** — free, cheap, medium and
> expensive — reusing a v2 result only where the sub-measurement would be an
> exact repeat.

**How to read a verdict:**

| verdict | means |
|---|---|
| **CONFIRMED** | the space was searched again and the old value won again |
| **CHANGED** | the old value lost, and the code or the recommendation moved |
| **OVERTURNED** | the old *reasoning* was wrong, not only its number |
| **STILL UNMEASURED** | say so plainly rather than inheriting a number |

**And the resolution bar, per G18.** Print the denominator, and judge a delta
against what the fixture can resolve, never against zero. At 20 queries one
query is 0.050 MRR; the bar used throughout is **1.5 queries**.

---

## THE TABLE

| # | decision | v2 said | **v3 says** | corpora (Python) | verdict |
|---|---|---|---|---|---|
| 1 | **fusion: on or off** | fuse when `r@50` < 0.95 | **ALWAYS ON** | 20 (10) | **CHANGED** |
| 2 | **fusion method** | score fusion | `score a=0.85`, **#1 of 51** | 20 (10) | **CONFIRMED** |
| 3 | **keyword ranker** | BM25, not `ts_rank` | BM25 | 20 (10) | **CONFIRMED** |
| 4 | **BM25 `k1` / `b`** | `1.2 / 0.75`, never swept | `1.2 / 0.75` — all six within 0.0037 | 20 (10) | **CONFIRMED, and shown not to matter** |
| 5 | **embedder primary** | `codestral-embed` | codestral, **19–0–1** | 20 (10) | **CONFIRMED** |
| 6 | **`MIGRATION` order** | gemini-2 above 001; mistral third | 001 above 2; mistral **last** | 20 (10) | **CHANGED — in code** |
| 7 | **the embedder gate** | tokens and calls | **+ a per-TEXT daily budget** | — | **CHANGED — in code** |
| 8 | **`SMALL_CORPUS_CHUNKS`** | 500 | **DELETED** | 6 (4) | **CHANGED — in code** |
| 9 | **`SEARCH_LIMIT`** | 50, never swept | **50**, and now swept | 20 (10) | **CONFIRMED** |
| 10 | **`RERANK_WINDOW`** | 50 (per tier) | **20** | 5 (5) | **CHANGED — IN CODE** |
| 11 | **reranking ships** | yes | yes — 9 real gains, **0 real losses** | 16 (10) | **CONFIRMED** |
| 12 | **the skip gate** | `SKIP_MARGIN = None` | `None` | 16 (10) | **CONFIRMED** |
| 13 | **routing by question kind** | dead | **dead** — every kind positive | 16 (10) | **CONFIRMED** |
| 14 | **chunk size `s`** | 500 | **500** | 7 (3) | **CONFIRMED** |
| 15 | **chunk overlap `o`** | 50 | **50** — nothing measurable moves it | 3 (3) | **CONFIRMED, and shown not to matter** |
| 16 | **the chunk header** | keep | **keep — +0.063 MRR, the largest chunking effect** | 3 (3) | **CONFIRMED** |
| 17 | **merged vs per-side rerank** | per side | **per side** — merged starves a side on **43 of 57** queries | v2 | **CONFIRMED** |
| 18 | **`VECTOR_TOP_N`** | 25, and "should be 10" | **15** — the measured best prompt of 30, halved for two sides | 18 (8) | **CHANGED — IN CODE. My first attempt shipped 30, a UNIT ERROR** |
| 18b | **`RERANK_TOP_N`** | 10 | 10 | 0 | **STILL UNMEASURED** |
| 19 | **exact vs HNSW** | exact | exact | — | **reused on purpose** |
| 20 | **BGE at `MIGRATION` position 2** | untouchable, platform argument | **moved to LAST** — the worst embedder we have | 4 (4) | **OVERTURNED — IN CODE** |
| 21 | **dual-embedder fusion** | never considered | **REJECTED** | 8–12 | **new, and negative** |

---

## 1. FUSION IS ALWAYS ON — CHANGED

v2 shipped *"switch the keyword channel ON below `r@50` ≈ 0.95 and OFF
above"*. **That rule is not implementable**, and this is the run's clearest
example of a measurement that cannot become a product:

> **`r@50` needs ground truth.** A user's repository has none, ever. So the
> condition can be evaluated on a benchmark and never at run time.

No proxy predicts it either — `pydantic` at 9,846 chunks is saturated while
`geo` at 729 is not, so size does not stand in for headroom.

Measured instead, always-on `score a=0.85` over 20 corpora and 423 queries:

```
gains >= 1 query on   5 corpora
loses >= 1 query on   0 corpora
net                   +8.7 queries MRR   +6.0 queries r@50
```

**It never measurably harms a corpus**, which is the only property a
permanently-on channel has to have. Cost: ~1,022 bytes per chunk (+12% of a
1536-dim row) and 4–5 database round trips, because Postgres has no BM25 and we
compute it in Python.

---

## 2–4. THE FUSION KNOBS — CONFIRMED BY SEARCH, not by re-test

The first run of `score_hybrid.py` in this session was made **with no flags**,
which pins every fusion knob at v2's winner. That is re-testing, not measuring,
and the user caught it. Re-run as a search:

```
--sweep        51 settings   score a=0.85 is #1 of 51
--sweep-bm25   6 settings    the FIRST sweep of k1/b in the project
```

**Both old values won.** But read row 4 carefully: all six BM25 settings land
within **0.0037 MRR** of each other. So `1.2 / 0.75` is confirmed *and*
demonstrated to be a knob that does not matter — which is more useful than the
confirmation, because it removes it from every future sweep.

---

## 5–6. THE EMBEDDERS — one confirmed, one moved in code

**codestral beats mistral 19–0–1**, 0.634 against 0.514 on the 20-corpus zoo.
Not close, and not a tie anywhere except once.

**`MIGRATION` was ordered partly on somebody else's benchmark**, and two
entries moved:

```
BEFORE  codestral, BGE, mistral, google-001, cohere, google-2
AFTER   codestral, BGE, google-001, cohere, google-2, mistral
```

`gemini-embedding-2` sat above `001` on **Google's** version number and
**Google's** MTEB mean. v2's G21 had already scored it, it lost, **and the code
was never changed** — so for a whole run the routing preferred the weaker
model. `mistral-embed` sat THIRD, above three better models, inside a tuple
whose own comment called it *"the strength order"*.

It stays in the list, last, because a walk must not dead-end: it is the only
model that can ingest 10,000 chunks quickly.

Both changes are **mutation-verified** — reverting either tuple fires exactly
one test.

> **A finding written in a document and not in a test is a finding that will be
> re-derived.**

---

## 7. THE EMBEDDER GATE — CHANGED, and it was a live production defect

`embedding_minutes()` returns `inf` for a model that cannot finish today, and
`_pick_embedder` skips those. It modelled a token budget and a call budget.
**Google's limit is neither**: one TEXT is one request, so a 96-text
`batchEmbedContents` call spends 96 of the day's 1,000.

```
BEFORE  20,000 chunks -> Gemini reports 163 minutes   (the truth: 20 DAYS)
AFTER    2,000 chunks -> CANNOT TODAY, drops out of the walk
          1,000 chunks -> still runs
```

Hit **twice on one day** while running into it: a `gemini-embedding-2` warm
died with HTTP 429 on its SECOND corpus, and `001` exhausted after 943 chunks.
`Rate` gains a fourth field, `daily_text_budget`; both Google models set 1,000.

**Cohere was checked and deliberately NOT given one** — it bills per CALL at up
to 96 texts, so its 1,000 a month is a caller's budget question and not a
per-ingest refusal. Its `tokens_per_minute` was corrected 640,000 → 100,000:
the old figure was a burst that never met a limit.

---

## 8. `SMALL_CORPUS_CHUNKS` IS DELETED — CHANGED

v2 shipped `= 500`, routing every corpus under that to Google first. Two
independent reasons it is gone, and only the second is about quality.

**It tripped the product's own warning.** `WARN_MINUTES = 2.0` is where
LabPilot stops and asks the user to confirm:

```
chunks   google   codestral
   240    2.0 min   0.10     <- the line
   500    4.1 min   0.21     WARNS THE USER
```

**At the shipped 500 the router picked an embedder that trips its own
warning.**

**And it does not buy quality.** Measured on six corpora against
`gemini-embedding-001` — the model that matters after row 6 — **three wins
each, net codestral ahead by 0.023 MRR ≈ half a query**, below resolution.

Deleted rather than retuned to 200, and that is the decision worth keeping:

> **A rule that exists to buy quality and buys none has no threshold that fixes
> it.** Moving the number would have preserved the mechanism and its cost while
> conceding it has no benefit.

---

## 9. `SEARCH_LIMIT` STAYS 50 — CONFIRMED, and swept for the first time

Never swept in v2 or v3. It is unlike every other knob because it is a
**ceiling**: an answer outside it can never be recovered by fusion, by
reranking, or by any later stage.

| `SEARCH_LIMIT` | mean recall | queries lost of 423 |
|---|---|---|
| 10 | 0.864 | **45** |
| 20 | 0.930 | 16 |
| 25 | 0.951 | 8 |
| 30 | 0.957 | 5 |
| **50** | **0.968** | **0** |

The only thing a smaller limit buys is database time, and exact search measures
~11 ms at 1,387 rows against a 350 ms round trip and a ~50 s report. **There is
no trade to make.** Going above 50 is the untested direction and is not free.

---

## 10. `RERANK_WINDOW` 50 → 20 — CHANGED (recommended, not yet in code)

Six windows, 5 corpora, **100% Python**, 89 to 9,846 chunks:

```
w10 +0.095   w20 +0.090   w30 +0.084   w50 +0.053   w5 +0.041
```

**The shipped w50 is nearly half as good as the best.** w10/w20/w30 are
indistinguishable — +1.84, +1.76 and +1.67 queries, a spread of 0.17 against a
bar of 1.5 — so the choice inside that band is made on cost and reach, not on
score: **20** is the middle of the flat region and costs fewer tokens per call
than 30, so more rerank tiers stay reachable.

This also finishes what v2's two-point comparison could not. Earlier in this
run H7 compared 50 against 30 and said 30, naming its own limit: *"20 and 40
are unmeasured."*

> **Two points make a direction, never an optimum.** A two-point comparison
> cannot see a flat region; it can only see which of the two is higher.

And `--window` is **not** `SEARCH_LIMIT` — verified in the source
(`vector_candidates = dense[q.id][:window]`):

```
search             -> 50   SEARCH_LIMIT     row 9
top 20 of those 50 -> 20   RERANK_WINDOW    this row
reranked, sent     -> 10   RERANK_TOP_N     row 18
```

---

## 11–13. RERANKING, THE GATE, AND ROUTING — all CONFIRMED

**Reranking ships.** 16 corpora, 10 Python, flash-lite at w50: **9 real gains,
0 real losses**, judged against each fixture's resolution rather than against
zero.

**`SKIP_MARGIN` stays `None`.** Third zoo, third time the same answer: the best
threshold skips almost nothing and sits within noise of always-rerank.

**Routing by question kind is dead**, and this run confirms it on 10 Python
corpora where v2 had 3. Every kind is positive:

```
claim +0.303 (n=10)   error +0.152   checklist +0.151 (n=7)
api   +0.140          structure +0.090   behaviour +0.089   constant +0.019
```

The worst single cell is `structure −0.500` on `websocket` with **n = 1** —
G18's denominator trap reproducing exactly, on the very finding that G18 was
written about. Slice 6 built a design principle on a cell of that shape.

---

## 14–16. THE CHUNKER — searched again, and the free thing wins

**Size**, 7 corpora:

| setting | MRR | r@50 |
|---|---|---|
| s=250 | 0.5358 | 0.9618 |
| **s=500** | **0.6144** | 0.9546 |
| s=750 | 0.6001 | 0.9773 |
| s=1000 | 0.5820 | **0.9845** |

`s=500` confirmed — **and read the second column before quoting the first.**
MRR peaks at 500 while `r@50` keeps climbing to 1000: **bigger chunks FIND more
and ORDER worse.** That is the third appearance of one shape this run, after
BGE and Cohere, so it is recorded as a rule rather than a curiosity:

> **Recall and ordering are different axes, and a change that buys one
> routinely sells the other.**

It also means `s=500` is only right **while a reranker runs**. With no
reranker, ordering is all we have.

**Overlap** is confirmed and shown not to matter: every setting from `o=0` to
`o=100` sits inside 0.013 MRR. The one real signal is that `o=0` costs `r@50`
(0.9245 against `o=25`'s 0.9804) — no overlap really does cut answers in half.

**The header** — the `[file · symbol · lines]` prefix — is worth **+0.063 MRR
and +0.053 `r@50`**, the largest single effect in the whole chunking pass and
larger than anything either tunable parameter moved.

> **The cheapest thing in the chunker is the one that matters most.** It costs
> ~20 tokens a chunk and is built from metadata we already hold.

---

## 17. MERGED VS PER-SIDE RERANKING — CONFIRMED, and it was mislabelled here

An earlier version of this document filed this as **STILL UNMEASURED**. That was
wrong, and the user caught it: **v2 measured it, and the result is not close.**

```
merged starves a side ENTIRELY on 43 of 57 queries
```

One rerank call over both artifacts lets the stronger side take every slot, so
the comparison is made against one artifact and a citation-free guess about the
other. For a tool whose whole job is comparing two things, that is not a quality
loss - it is the product not working.

**The v2 number is also a correction of a correction**, which is why it is worth
trusting: the broken `PairScores` instrument had reported **0 of 20**, and
fixing it turned "merged is fine" into "merged fails three quarters of the
time".

### Three more reasons, none of which needed a new run

1. **Per side makes coverage STRUCTURAL.** Merged makes it depend on the
   selector behaving. This project's own rule: *put a rule where it cannot be
   broken, not where it can be checked.*
2. **Merged is the one shape that loses Voyage.** Per side hands it
   `RERANK_WINDOW` documents; merged hands it double, which slice 6 measured as
   refused outright on a card-free account.
3. **The saving it buys is gone.** Merged halves the rerank CALL count - and the
   2026-09-19 fix that gave the rerank chain its second Google account doubled
   that budget anyway, from 29,800 calls a day to 59,600.

### What the literature says, and what it does NOT say

Searching it returns work on merging multiple **retrievers** - dense plus
sparse, several rankers over one corpus - and that consistently favours merging.
**It is a different question.** LabPilot's sides are two different
ARTIFACTS being compared, not two views of one corpus, and no result found
addresses starving one of them. Recorded as *not evidence either way* rather
than quoted as support.

**PER SIDE ships. This decision is closed.**

## 18. `VECTOR_TOP_N` AND `RERANK_TOP_N`

> **TAKE ONE OF THIS MEASUREMENT WAS VOID AND MUST NOT BE QUOTED.** It ran on
> `gemma-4-31b-it`, which (a) cannot be combined with v2's flash-lite 13-corpus
> run, and (b) failed 3 of 15 cells — gemma returns HTTP 500 on roughly one call
> in three. **The failures landed on N=10 and N=30 and never on N=20**, which is
> exactly the asymmetry that manufactures "N=20 wins". Restricted to
> fully-valid corpora only two remained and they disagreed.

> **A pooled mean is only as trustworthy as its worst cell.** Here the
> denominator was fine and the NUMERATOR was damaged by provider failures — and
> the damage was not evenly spread.

Take two ran on **flash-lite**, the same model as v2's 13 corpora, so the two
combine into **18 corpora, one model**. Result below.

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

### THE CHOICE: `VECTOR_TOP_N = 30`

Judged per corpus, in **queries**, against the 1.5-query resolution bar rather
than against zero:

| corpus | chunks | N=20 | N=30 | delta | verdict |
|---|---|---|---|---|---|
| websocket | 78 | 10 | 10 | +0 | tie |
| **quora** | 82 | 3 | 14 | **+11** | **N=30** |
| docx | 85 | 8 | 9 | +1 | tie |
| smsspam | 89 | 10 | 9 | −1 | tie |
| log | 146 | 11 | 11 | +0 | tie |
| cobra | 193 | 10 | 10 | +0 | tie |
| **requests** | 335 | 14 | 19 | **+5** | **N=30** |
| notebooks | 382 | 8 | 9 | +1 | tie |
| papers | 404 | 10 | 10 | +0 | tie |
| **docs** | 463 | 14 | 16 | **+2** | **N=30** |
| **lung** | 628 | 7 | 10 | **+3** | **N=30** |
| **jq** | 693 | 9 | 12 | **+3** | **N=30** |
| **geo** | 729 | 16 | 22 | **+6** | **N=30** |
| gson | 750 | 9 | 9 | +0 | tie |
| zod | 1,160 | 14 | 8 | **−6** | N=20 — *but see below* |
| click | 1,585 | 9 | 8 | −1 | tie |
| pytest | 6,714 | 6 | 5 | −1 | tie |
| **pydantic** | 9,846 | 9 | 5 | **−4** | **N=20** |

**N=30 wins 6 corpora above the bar, N=20 wins 2, and 10 are ties.**

**And one of those two is unreliable.** `zod` N=30 is the cell that was re-run
live today and came back **14 instead of 8** — with 14 it is a tie. So the solid
case for N=20 is **one corpus: `pydantic`, the largest in the zoo**.

```
10 -> 20   huge, everywhere.   N=10 wins ZERO corpora of 18
20 -> 30   +6 / −2 / 10 ties   net positive   <- the choice
30 -> 50   +4 / −1 /  8 ties   net positive but mostly ties,
                               and NO Python corpus above 1,160 chunks was tested
```

**Why 30 and not higher.** Above 30 the gains thin out to mostly ties, and every
corpus that carries N=50 and N=100 belongs to v2's 13 — **3 Python of 13**, the
exact skew this run exists to remove. Raising the number past the point our own
Python evidence stops would be inheriting a conclusion about Go, C and prose.

**Why 30 and not 20.** The shipped 25 was never measured at all; 20 and 30 were.
30 is better on the pooled share, the per-corpus mean, head-to-head wins, and on
*both* language pools separately.

**The honest cost.** `pydantic` at 9,846 chunks loses 4 queries of 20 going from
20 to 30, and it is the closest corpus in the zoo to what the product targets.
So this choice is made knowing it is slightly wrong for the largest repositories
and clearly right for everything else.

**Budget check.** `VECTOR_TOP_N` is per side, so 30 is 60 chunks ≈ 14,200 tokens
at the measured 236 tokens/chunk, plus ~2,000 of instructions, against
`PROMPT_BUDGET = 26,000`. It fits with room.

**THE NEXT MEASUREMENT THIS NAMES:** N=50 and N=100 **on the Python corpora**,
~200 generation calls. If Python keeps improving past 30 the way v2's 13 do, 30
is still too low; if it turns over, 30 is the ceiling and `pydantic` was the
early warning.

### What this decides, and what it does not

**This experiment picks its chunks by VECTOR SEARCH ALONE** — `chosen()` reads
`dense_orders` and no reranker touches it — so it measures **`VECTOR_TOP_N`**
and says nothing directly about `RERANK_TOP_N`.

```
VECTOR_TOP_N = 25 -> 30   the shipped 25 was never measured; 20 and 30 were,
                          and 30 wins. v2's own unshipped "should be 10" is
                          OVERTURNED: 10 wins ZERO corpora of 18.
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

## 19. EXACT VS HNSW — reused from v2 on purpose

The only measurement in this run deliberately **not** repeated. It is a
database benchmark, and its inputs are row count and vector width — neither of
which the zoo changed. Repeating it would have spent a day to re-derive
milliseconds that do not depend on which corpora we chose.

---

## 20. BGE AT `MIGRATION` POSITION 2 — OVERTURNED

`@cf/baai/bge-base-en-v1.5` sits **second** in `MIGRATION` and had never been
scored — not in v2, not in v3. It is there on a **platform** argument:
codestral and mistral-embed share one API key, so a Mistral outage would
otherwise take the top two.

Scored at last:

| corpus | chunks | codestral | BGE | delta |
|---|---|---|---|---|
| smsspam | 89 | 0.653 | 0.519 | **−0.134** |
| disaster | 108 | 0.753 | 0.633 | **−0.120** |
| titanic | 118 | 0.594 | 0.452 | **−0.143** |
| lung | 628 | 0.587 | 0.388 | **−0.200** |

**Loses 4 of 4, mean −0.149 MRR** — about 3 queries per corpus, and worse than
`mistral-embed`, which row 6 demoted to last for losing by far less. One
redeeming detail, and it is the same shape as row 14: on `lung` its `r@50` is
**0.941 against codestral's 0.882**. It finds more and orders far worse.

**So the fallback from our primary is the weakest model we have measured.**
`gemini-embedding-001` is on a third platform and scores 0.602, so it satisfies
the platform argument and the strength argument at once.

**CHANGED IN CODE 2026-09-18** — BGE moves from position 2 to LAST. The
robustness argument is not abandoned, it is satisfied by a better model:
`gemini-embedding-001` is on a third platform AND scores 0.602, which is what
that argument actually asked for. BGE also cannot ingest a large corpus at all
(684,000 neurons a day stops it at ~2,900 chunks), which is a second reason it
belongs behind `mistral-embed` rather than in front of it.

### Three bugs had made it unmeasurable, and that is why "never scored" survived two runs

```
1. score_hybrid.py  EMBEDDERS did not contain BGE at all
2. the chunk cache  "@cf/baai/bge-base-en-v1.5" has SLASHES, so the filename
                    became a PATH -> FileNotFoundError. The embedding SUCCEEDED
                    (89/89 vectors, 17,807 tokens spent) and was thrown away
3. the result file  same slashes, same silent loss
```

`score_rerank` had already sanitised slashes; the embed path never did.

> **This is the THIRD hardcoded-registry defect found in this run**, after
> `tier_reach.py`'s hardcoded corpus list and `EMBEDDERS` itself. **A registry
> that is data everywhere else and hardcoded in one script silently measures
> less than it appears to.**

---

## 21. DUAL-EMBEDDER FUSION — explored, and REJECTED

Not a v2 decision. It came from the user's question about using Cohere's
strength without paying its monthly budget, and it was free to test because
every vector was already cached: fuse two embedders' rankings with RRF, exactly
as vector and BM25 are fused.

**Rejected** — the gain does not survive the cost in ingest time, and a
size-tiered variant (google under 200 chunks, cohere to 500, mistral above) was
measured and did not beat codestral alone by enough to justify embedding every
corpus twice.

**One insight is kept, because it explains a failure elsewhere:**

> **Google ALONE is worse than codestral (0.590 against 0.646). Google ADDED to
> codestral is better (0.6664).**

That is precisely why the deleted rule in row 8 failed: it **substituted** one
embedder for the other where the only thing that helps is **adding** them.

---

## WHAT THIS RUN DID NOT SETTLE

| | why it is still open |
|---|---|
| **merged vs per-side reranking** | never run, in either version |
| **the reranker MODEL on the new Python corpora** | v2 ranked 9 configs on the old zoo. `tier_reach` now says Gemma serves 10 of 10 Python corpora at w50 where v2 said 4 of 13, so chain 3's BUDGET reasoning was wrong even where its order is right |
| **the all-suffix corpus** | every corpus here is `.py` only. A real ingest reads 58 suffixes, so `pydantic` would be 13,377 chunks rather than 9,846 (+36%) |
| **BGE's position in code** | row 20 is a recommendation, not a commit |
| **end-to-end time / `WARN_MINUTES`** | still a guess, as it was in v2 |
| **a fourth language** | 20 corpora beats 13, and is still one zoo |

---

## THE RULES THIS RUN EARNED

> **Re-testing a chosen value is not measuring it.** The first fusion run of
> the session pinned every knob at v2's winner and reported that v2's winner
> won.

> **Two points make a direction, never an optimum.**

> **Recall and ordering are different axes**, and a change that buys one
> routinely sells the other. Seen three times: BGE, Cohere, chunk size.

> **A pooled mean is only as trustworthy as its worst cell.** A damaged
> numerator is invisible in the mean and is rarely spread evenly.

> **A rule that exists to buy quality and buys none has no threshold that fixes
> it.**

> **A registry that is data everywhere else and hardcoded in one script
> silently measures less than it appears to.**

> **A finding written in a document and not in a test is a finding that will be
> re-derived.**

> **A results directory with two files for one run is a trap, and the
> canonical-looking name does not always win.** `answers_flashlite.json` was
> written mid-fix; `answers_regraded.json`, eight minutes later, moves 62 of its
> 75 cells. Section 18 was written twice because of it.

> **Re-using cached data is right when the model, the script, the fixtures AND
> the grader are the same** — and the grader is the one people forget, because
> it changes without any measurement being re-run.


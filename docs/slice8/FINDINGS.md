# Slice 8 — findings log

Written as they happen, with the evidence beside each one. A finding with no
run behind it is a guess and must say so.

---

## F1 — Google embedders CANNOT ingest today, and the halving fallback does not save them

**Status: production defect, measured 2026-09-16, not yet fixed.**

`MAX_BATCH_SIZE = 96` is derived in `embed/defaults.py` from
`TIGHTEST_TOKENS_PER_MINUTE = 50_000`, which is **Mistral's** budget. Google's
is **30,000**. Measured on the geo corpus, back to back on one key:

```
96 texts, est 44,554 tokens  ->  HTTP 429
40 texts, est 18,072 tokens  ->  HTTP 200, immediately after
```

The 40 passed **straight after** the 96 failed, so the bucket was not empty:
the 96-text call was refused **for its own size**. That is the Voyage shape
exactly — a single call larger than the per-minute budget is refused however
long you wait.

**The fallback cannot rescue it.** `looks_like_too_many_tokens` matches the
word `token` in the error text. Google's 429 body says *"You exceeded your
current quota ... rate-limits ... rate-limit"* and **never says "token"**, so
`embed_batches` raises instead of halving.

**Consequence:** every Google entry in `MIGRATION` — four of eight, including
`gemini-embedding-001`, the current recall leader — fails on its FIRST batch
for any artifact whose chunks average more than ~312 tokens
(`30,000 / 96`). This repository's own mean is 342 and geo's is 474, so both
would fail. It has never been seen because no production caller has routed to
Google and every earlier fixture had a smaller mean chunk:

```
quora    mean 217 tok  ->  96 x 217 = 20.8k  passes by luck
requests mean 229 tok  ->  96 x 229 = 22.0k  passes by luck
geo      mean 474 tok  ->  96 x 474 = 45.5k  REFUSED
labpilot mean 342 tok  ->  96 x 342 = 32.8k  would be REFUSED
```

**The fix is two lines and both are needed**, because either alone still
fails: batch by TOKENS against the model's own rate, not by a count derived
from another provider; and widen the refusal match beyond the word "token".

> **A batch size derived from one provider's quota is wrong for every other
> provider.** `MAX_BATCH_SIZE` is a Mistral constant wearing a global name.

---

## F2 — BGE's tokenizer ratio, and CLAUDE.md's arithmetic for it was wrong

**Measured 2026-09-16 from Cloudflare's own `usage.prompt_tokens`, 8 chunks
per corpus.** Real BGE tokens against OUR `chars / 3` estimate:

| corpus | ratio | corpus mean, our est | in BGE tokens | chunks over BGE's 512 |
|---|---|---|---|---|
| geo (Go) | **1.12x** | 474 | 530 | **665 of 729 — 91.2%** |
| requests (Py) | **1.39x** | 244 | 339 | 91 of 335 — 27.2% |
| quora (Py) | **1.45x** | 232 | 337 | 19 of 82 — 23.2% |

**CLAUDE.md records this ratio as 2.36x and it is not.** That figure came from
slice 1b's *39,936 BGE tokens against codestral's 14,979* — which compares BGE
to **codestral's tokenizer**, not to our estimate. Two different denominators,
so the number could not be used the way the file used it.

**The conclusion survives and gets worse in one place.** `_check_texts`
enforces `max_input_tokens = 512` in OUR units, so the real ceiling is
`512 / ratio` — between **353** (quora) and **457** (geo) of our tokens. Every
chunk between that and 512 passes the guard and is silently truncated. On geo
that is **91% of the corpus**, because the generic splitter packs Go chunks to
474 tokens where the Python AST splitter averages 232-244.

> **A ratio is only meaningful with its denominator named.** "2.36x" was true
> of codestral and false of our estimator, and the guard is written in our
> estimator's units.

**Consequence for slice 8 job 1:** BGE is NOT scored on geo. A score there
would measure truncation, not the model. It is also unaffordable — 345,676 of
our tokens is ~387,000 BGE tokens against a 684,000 daily budget, which would
spend most of a day's Cloudflare neurons on one corpus.

---

## F3 — Cohere's trial tier is 100,000 tokens/minute, recorded nowhere

**Measured 2026-09-16 by hitting it**, embedding geo:

```
HTTP 429  "trial token rate limit exceeded, limit is 100000 tokens per minute"
```

`embed/registry.py` carries `Rate(requests_per_minute=10)` for `embed-v4.0`
and **no token rate at all**, plus `measured_tokens_per_minute=640_000`. That
640k was explicitly a BURST — the registry comment says it was "capped at 6
requests to protect a 1,000-a-MONTH budget, so no limit was reached."

**It is 6.4x optimistic.** `embedding_minutes()` uses the measured figure, so
the estimator under-predicts a Cohere ingest by that factor: this corpus is
0.5 minutes predicted against **3.5 minutes real**.

> **A burst that never met a limit is not a throughput measurement.** The
> registry said so in its own comment and the number was used anyway.

---

## F0 — the instrument is trustworthy (control)

`score_hybrid.py quora codestral` reproduces the recorded 2026-09-07 numbers
to three decimals: **r@1 0.412, r@5 0.941, r@10 0.941, r@50 1.000, MRR 0.608**,
and `wRRF k=5 w=0.15` at MRR 0.619. Embedding cache and scorer both valid.

---

## F4 — Google counts one TEXT as one request, so it can embed 1,000 CHUNKS a day, not 96,000

**Measured 2026-09-16, two independent ways, and it disqualifies Google as a
production embedder for this project's target corpus size.**

Google's 429 names the quota explicitly:

```
quotaId: EmbedContentRequestsPerDayPerUserPerProjectPerModel-FreeTier
         limit 1000, model gemini-embedding-2
```

**Evidence 1 — the daily limit.** `gemini-embedding-2` on key 1 embedded geo
(729 chunks) and then began requests (335 more). It failed partway:
`729 + 335 = 1064 > 1000`. If a "request" were an HTTP call, that would be
about 16 calls of a 1,000 budget.

**Evidence 2 — the per-minute limit, decisive.** Three back-to-back calls of
**40 texts each** on `gemini-embedding-001`, inside six seconds:

```
call 1  +40 texts  ->  200
call 2  +40 texts  ->  200
call 3  +40 texts  ->  429   "limit: 100"
```

Three HTTP calls cannot exceed a limit of 100. **120 texts can.**

### What this changes

| | recorded in CLAUDE.md | measured |
|---|---|---|
| Google embed budget | "1,000 embed requests/day" read as 1,000 **calls** = up to 96,000 texts | **1,000 TEXTS per day per model per project** |
| Google per-minute | `requests_per_minute=100` read as 100 **calls** | **100 TEXTS per minute** |
| all four Google entries together | ~384,000 texts/day | **4,000 chunks/day** |

**`embedding_minutes()` is wrong for Google in two ways**, in
`labpilot/embed/base.py`:

```python
requests = math.ceil(chunks / MAX_BATCH_SIZE)  # HTTP calls, not texts
by_requests = requests / rpm
```

and there is **no daily REQUEST budget at all** — `Rate` models only
`daily_token_budget`, which Cloudflare needs and Google also needs in a
different unit.

For a 10,000-chunk repository the estimator returns **118 minutes**. The truth
is that it **cannot be done today at all**: 10,000 texts against 1,000 a day
is ten days on one model, and moving to another Google model mid-corpus is a
re-embed, not a continuation.

> **This is the same mistake as F1 one level up.** `MAX_BATCH_SIZE` assumed
> every provider counts an HTTP call; the estimator assumed the same thing.
> Google counts the thing inside the call.

**Decision impact — job 1.** Google's recall on the Python corpora is the best
this project has measured, and it is irrelevant at the target size: LabPilot
aims at **1,000-10,000 chunks per artifact** and Google tops out at **1,000
chunks per day**. It is usable for a notebook and unusable for a repository.
That is a capability gate, not a preference, and it outranks any recall score
— the same shape as "a model that cannot be indexed is not a candidate".

---

## F5 — reranking is a LARGE win, and slice 6's "routing signal" was a property of ONE model

**Measured 2026-09-16 on geo (729 chunks, 45 queries, codestral), window 50.**

| | r@1 | r@5 | r@10 | r@50 | MRR |
|---|---|---|---|---|---|
| vector alone | 0.444 | 0.667 | 0.689 | 0.867 | 0.526 |
| **+ `gemini-3.5-flash-lite`** | **0.689** | **0.822** | **0.822** | 0.867 | **0.746** |
| + `bge-reranker-base` (CF) | 0.244 | 0.422 | 0.600 | 0.867 | 0.347 |

**Headroom captured: +75% for flash-lite, −50% for bge.** `r@50` is unchanged
for both, so the instrument is sound: a reranker only reorders.

This is the strongest reranking result the project has: **+0.220 MRR**, against
+0.117 on the saturated quora corpus. The gain is larger here precisely
*because* geo is not saturated — there is something left to win.

### The category split does NOT reproduce, and that matters

Slice 6 measured `bge` winning on `constant` (+0.186) and collapsing on
`structure` (−0.534), and this project recorded that as a **routing signal** —
"a cross-encoder and a keyword ranker are both LOCAL relevance models". With a
good reranker on geo, reranking wins on **every** category:

| asks | before | after | delta |
|---|---|---|---|
| error | 0.378 | 0.778 | **+0.400** |
| structure | 0.494 | 0.704 | **+0.210** |
| api | 0.754 | 0.926 | +0.172 |
| behaviour | 0.620 | 0.786 | +0.165 |
| constant | 0.386 | 0.538 | +0.152 |

`structure` was slice 6's worst category (−0.534) and is now its **second
best** (+0.210).

> **The split was a fingerprint of `bge-reranker-base`, not a law about
> reranking.** Slice 6 said its own results "may NOT conclude which provider is
> best" and then a mechanism was built on top of one provider's failure. Routing
> by question type may still be worth doing — but this measurement is not
> evidence for it, and the old evidence describes a model we should delete.

### The gate stays OFF, now on a third corpus

```
tau 0.000 (never rerank)  MRR 0.525
tau 0.050 (skip 2 of 45)  MRR 0.752   <- best, and 2 queries from "always"
always rerank             MRR 0.746
```

Best is within noise of always-rerank while skipping 2 of 45 calls.
`SKIP_MARGIN = None` is confirmed for the third time.

---

## F6 — `bge-reranker-base` should be DELETED, not reordered

It is now measured worse than not reranking on **three corpora**:

```
quora     MRR 0.608 -> 0.520   -0.088
requests  MRR 0.646 -> 0.476   -0.170
geo       MRR 0.526 -> 0.347   -0.179
```

CLAUDE.md keeps it as chain tier 8 on the argument that "one corpus and one
saturated fixture is thin evidence" and that its ~2,840/day budget cannot run
out. **Two corpora have been added since, in a second language and a third
domain, and it lost on both.** The condition the registry itself set — "if
slice 8 confirms the number, the right move is to delete this tier rather than
reorder it" — is met.

---

## F7 — flash-lite reranking helps on EVERY question type, on EVERY corpus

**Measured 2026-09-16.** Per-category MRR delta, `gemini-3.5-flash-lite`,
window 50:

| asks | geo | requests |
|---|---|---|
| error | **+0.400** | **+0.300** |
| constant | +0.231 | +0.153 |
| api | +0.172 | +0.216 |
| behaviour | +0.161 | +0.141 |
| structure | +0.201 | +0.000 |

**Not one negative cell.** Slice 6 measured `bge` at **−0.534** on
`structure` and built a routing story on it. With a reranker that works, the
story disappears.

Cohere on geo is genuinely mixed, which is what a real difference between
models looks like: `error` +0.289 and `structure` +0.210, but `behaviour`
−0.015 and `constant` −0.044.

### Whole-corpus effect, three corpora

| corpus | vector MRR | + flash-lite | headroom captured |
|---|---|---|---|
| geo | 0.526 | **0.759** | **+75%** |
| requests | 0.646 | **0.791** | +50% |
| quora (slice 6, w30) | 0.608 | 0.799 | — |

`r@50` is unchanged on every run, so the instrument is sound.

> **Reranking SHIPS.** Slice 6 could not conclude this because it measured the
> one model that makes retrieval worse. Three corpora, two languages, three
> domains, and a large positive gain on all of them.

---

## F8 — the window curve TURNS OVER between 50 and 100

**Measured on geo with flash-lite**, varying the candidate window:

| window | reranked r@1 | reranked r@10 | MRR | ceiling (r@50 in window) |
|---|---|---|---|---|
| 10 | 0.622 | 0.689 | 0.640 | 0.689 |
| 20 | 0.689 | 0.756 | 0.726 | 0.800 |
| 30 | 0.667 | 0.778 | 0.719 | 0.822 |
| **50** | **0.711** | **0.822** | **0.759** | 0.867 |

| **100** | 0.511 | **0.911** | 0.686 | 0.933 |

Monotone up to 50, then it **turns over, and the two metrics disagree**: at
100 the reranker puts the answer in the top ten more often than at any other
width (`r@10` 0.911) and puts it FIRST far less often (`r@1` 0.511 against
0.711, MRR 0.686 against 0.759).

**`SEARCH_LIMIT = 50` is the default** because it wins MRR and `r@1`,
and 100 is worth testing because Cohere bills one search unit up to 100
documents, so half of every Cohere call is currently paid for and thrown away.

This also settles section 14.3's open question in favour of a **per-tier**
window rather than a global cut: cutting to 25 before the reranker would have
cost `r@10` 0.822 -> 0.756 on geo, and the tier the cut was protecting cannot
serve this corpus at any window (below).

---

## F9 — two rerank tiers cannot serve a real corpus at all, and both fail LOCALLY

Chunk size decides reachability, and geo's generic-splitter chunks (474 tokens
mean) are twice the Python corpora's:

| tier | limit | 50 geo documents | verdict |
|---|---|---|---|
| `gemma-4-26b-a4b-it` | 16,000 input tokens/min | ~27,344 | **refused by `_check_fits`, no request spent** |
| `gemma-4-26b-a4b-it` at window 30 | 16,000 | ~16,376 | **still refused, by 376 tokens** |
| Voyage (card-free) | 10,000 TPM, call counted whole | ~23,700 | refused by the provider |

Gemma is measured third-best on quora and **cannot rerank a Go repository**.
That is not a quality question, and no reordering of chain 3 fixes it — it is
the Groq shape again: alive, and unreachable at the real request size.

> **A tier's usable window depends on the CORPUS, not only on the provider.**
> The same tier serves 50 Python chunks and refuses 30 Go ones.

---

## F10 — EXACT SEARCH STANDS. The one condition that could overturn it is now measured

**Measured 2026-09-16 on the REAL Supabase instance, real vectors, real
embedded questions, plan asserted with EXPLAIN ANALYZE.**

The 2026-09-05 decision was explicit about what could reopen it: **time, and
only time** — recall cannot, because exact is 1.00 by definition, and storage
cannot, because exact is 2.5x cheaper. Here is the time.

| artifact | rows | client ms | **server ms** | plan |
|---|---|---|---|---|
| requests | 335 | 356 | **2.86** | Sort |
| geo | 729 | 340 | **6.07** | Sort |
| labpilot | 1,387 | 358 | **11.33** | Sort |

Server time is almost exactly linear at **8.2-8.5 microseconds per row**, so a
10,000-chunk artifact extrapolates to about **82 ms**. (An extrapolation, not
a measurement — and it holds only while the vectors fit the free tier's
500 MB working set. CLAUDE.md measured the cliff at 30,000 rows: 10,019 ms.)

### The first thing to notice is that the database is not the cost

**Client latency is ~350 ms and FLAT from 335 to 1,387 rows.** The round trip
from this VPN exit to Frankfurt swamps the scan by roughly 30x. Any earlier
number that mixed the two was measuring the network.

```
exact search, 1,387 rows     11 ms     the database
one round trip              350 ms     the network, 30x larger
one report                   52,700 ms   the model, 4,600x larger
```

### With a partial HNSW index per artifact

| rows | ef_search | server ms | vs exact | recall@10 | plan |
|---|---|---|---|---|---|
| 335 | 40 / 100 | 2.88 / 2.93 | 1.0x | 1.000 | **index NOT USED** |
| 729 | 40 / 100 | 6.05 / 7.18 | 1.0x / 0.8x | 1.000 | **index NOT USED** |
| **1,387** | **40** | **1.22** | **9.3x** | **0.960** | **INDEX** |
| 1,387 | 100 | 11.61 | 1.0x | 1.000 | **index NOT USED** |

Three things, and two of them are new:

1. **Below ~1,000 rows Postgres refuses the index and sorts instead**, exactly
   as slice 4 found on a local container. It is not our query shape - the
   expression and the operator class match.
2. **At 1,387 rows it finally uses the index, and it is 9.3x faster** - but
   at `ef_search = 40` that costs **4% of recall**.
3. **At `ef_search = 100` the planner stops using the index again**, because a
   wider search becomes more expensive than sorting 1,387 rows. So "raise
   ef_search to recover recall" and "use the index at all" are in TENSION at
   this size, which no earlier measurement showed.

### The decision

**Exact search ships, and this closes the question rather than deferring it.**
Switching to HNSW would save about 10 ms of a ~50,000 ms answer — 0.02% — and
would cost 4% of recall at the only setting the planner will actually choose.
Storage confirms the other half: the indexes are **22 MB of a 44 MB total**
for 2,451 rows, so the index is about as large as the table.

> **We are not short of database time. We are short of model time and network
> time, and an index cannot buy either.**

**Revisit at ~20,000 chunks in one artifact**, where exact extrapolates past
160 ms and the free tier's RAM cliff starts to matter. Nothing below that
changes the answer.

---

## F11 — a cheap tier does NOT replace the strong tier for the REPORT

**Job 9, measured 2026-09-16.** The lean `REPORT` template, stuffed (100
chunks, ~24,275 tokens), `thinking=MEDIUM`, on `gemini-3.5-flash-lite` —
500/day against the recorded baseline's 20/day.

```
STOP   16.4s   5,596 characters   citations 12 written, 12 RESOLVED (100%)
```

Fast, complete, and every citation resolves. Then it is graded against
`EXPECTED.md`:

| | baseline (`gemini-3.6-flash`, 2026-08-17) | **flash-lite** |
|---|---|---|
| findings | **13 of 19** | **~8 of 19** |
| of the 5 that CARRY THE STORY | **4** | **2** (#11 stopwords, #9 threshold) |
| characters | 11,507 | 5,596 |
| citations resolved | 47 of 47 | 12 of 12 |
| §6 comparability gate | held | **BROKEN** |

Found: label smoothing, weight decay, the scheduler, the missing test split,
the re-tuned threshold, one seed, stopword masking, the extra cosine feature.
**Missed**: pooling the projected features (#1), `pos_class_weight` defined
and never called (#6), the unfreeze off-by-one (#5), the 12.1-point
train/validation gap (#10b), and every small B-only defect (#12, #14–#18).

### The worst part is not the count

§6 correctly returns **NO — the two numbers are not comparable**, naming both
causes. Then §9 writes:

> *"...which explains why Side B's validation F1 (0.8262) sits substantially
> below Side A's reported performance (0.851)."*

**It performs the comparison it just forbade.** That is precisely the failure
CLAUDE.md recorded on 2026-08-14 — *"a correct verdict does not constrain the
prose that follows it"* — and the reason the rule became "ban the material,
not the conclusion". The strong tier holds that gate; this one does not.

### What this does and does not settle

CLAUDE.md section 11.9 challenged "reserve the strongest tier for
`explain_divergence`", on good grounds: session 10 measured model strength
out as the cause of the *coverage* problem in that experiment, and blind
spots are per-model and disjoint rather than better-and-worse.

**The challenge fails for the report specifically.** It is not that
flash-lite is wrong — it is that it writes half as much and stops earlier,
which is free recall stopping when the answer *feels* complete. Cheap tiers
keep their place on the nine other calls in a report; the report itself stays
on the strong chain.

**Honest limits:** one run, one fixture, one cheap tier. The baseline is a
different model on the same fixture, so the comparison is fair on prompt and
corpus and not on anything else. `gemma-4-31b` cannot be tested at all here —
its 16,000 input tokens/minute is below a 24,275-token stuffed prompt.

---

## F12 — the end-to-end answer is 90-250 SECONDS, and generation is 92% of it

**Job 4, measured 2026-09-16, and it had never been measured.** Driven through
the real `services.ask()`, so it includes the assembled rerank chain and the
real generator chain with its fallbacks.

| stage | STUFF path | SEARCH path |
|---|---|---|
| embed the question | 6.80s (3.8%) | 1.71s (1.9%) |
| search | 0.93s (0.5%) | 1.61s (1.8%) |
| gate + rerank | 3.52s (2.0%) | 4.15s (4.6%) |
| build the prompt | 0.00s | 0.00s |
| **generate** | **166.45s (93.7%)** | **82.38s (91.7%)** |
| **TOTAL** | **177.70s** | **89.85s** |

A second, independent run of the same search path gave **116.88s** and an
earlier one **252.12s**. So the honest range is **90-250 seconds, and the
whole spread is in generation** — which this project already measured as
wildly variable (a 36x spread in thinking tokens at `temperature: 0`).

Ingest, once per artifact: `A_paper.md` 18 chunks in 4.1s, `B_train.py` 82
chunks in 30.3s.

### What this settles

**`WARN_MINUTES = 2.0` is measuring the wrong thing.** It warns about
EMBEDDING, and embedding a 100-chunk pair takes 34 seconds while the ANSWER
takes 90-250. A user who is told "this will take about 2 minutes" and then
waits four has been told the wrong number by the wrong stage.

**Retrieval is 4-7% of an answer and is not worth optimising for time.** This
agrees with F10 from the other direction: the database is 11 ms, the network
350 ms, retrieval as a whole about 6 seconds, and generation 82-166 seconds.

```
database          0.011s
search + rerank   6s        <- everything slice 8 measured for quality
generate         82-166s    <- 92% of the wait
```

**And Step 2 multiplies the dominant term.** CLAUDE.md estimates a report at
~10 calls with routing. At 82-166 seconds for ONE call, the product
constraint it wrote down - *"we will not ship a tool that costs ten minutes
for a simple task"* - is not a future risk. **One call already costs up to
four minutes**, so the planner keeping simple questions to one node is not an
optimisation, it is the only thing standing between the tool and that line.

**The tier that answers changes the wait by 2x.** `z-ai/glm-5.3-flash`
(tier 1, free) took 166s; `gemini-3.6-flash` took 82s after two Google tiers
rate-limited. Cheapest is not fastest.

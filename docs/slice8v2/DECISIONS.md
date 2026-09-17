# SLICE 8 v2 — every decision taken, and every one corrected

**The resume document.** If the session ends, start here: this is what was
decided, what was overturned, what is still open, and what to run next.

Branch `slice8/measure-v2`, pushed. `main` untouched.

**Read `RESUME.md` FIRST** - it carries the environment incantation, the traps,
and the exact commands for everything still owed. Then this file, then
`RESULTS.md`, `FINDINGS.md`, `MEASUREMENTS.md`.

---

## A. DECIDED, with the run behind it

| # | decision | evidence |
|---|---|---|
| A1 | **Exact search ships.** Revisit at ~20,000 chunks in one artifact | 12 artifacts, real instance, plans asserted. Crossover is **~700 rows**, not ~1,000. Index costs **6-13% recall** at `ef=40`, and `ef=100` makes the planner abandon it at every size. Index is 43% of storage |
| A2 | **Reranking ships**, `gemini-3.5-flash-lite` | 13 corpora, 286 queries. Helped **10**, hurt **3**, mean **+0.122**. `r@50` unmoved on every run |
| A3 | **`SKIP_MARGIN = 0.05`** — overturns `None` | `None` was "confirmed" 3x, each on 1-2 corpora *where reranking helped every query*. At 0.05: beats always-rerank, loses on **2 of 13**, skips **18%** of rerank calls. On `zod` the gate beats both reranking and not reranking |
| A4 | **`s = 500` chunk size is vindicated** | best of five sizes pooled over 4 corpora; the curve has the shape the dilution argument predicts |
| A5 | **The free context header stays** | +0.022 mean MRR over 6 corpora, largest where a chunk is least self-describing (papers +0.098, cobra +0.065) |
| A6 | **`codestral-embed` stays primary** — on CAPABILITY, not recall | on the corpora all five reached the top three are within **0.012**. Google embeds 1,000 texts/day; Cohere is 1,000 calls/month. codestral is the only strong model that can ingest a repository |
| A8 | **A small corpus goes to Google first** - SHIPPED, `SMALL_CORPUS_CHUNKS = 500` | Google retrieves best where vector search is already easy (quora 0.674, requests 0.650 against codestral's 0.608 and 0.646) and loses where there is real headroom (geo 0.493 against 0.526). Its quota points at the same range - ~1,000 chunks a day. A REORDERING, never a restriction: a spent bucket falls through to codestral. 752 tests pass |
| A7 | **Google counts TEXTS, not calls** — batching does not help | `729+335 = 1,064` texts → `limit: 1000`; 3 calls x 40 texts in 6s → `limit: 100`. Three calls cannot exceed 100; 120 texts can |

---

## B. CORRECTED — claims made this session that did not survive

| what I said | what is true |
|---|---|
| "not one of 63 wRRF settings is never-worse — zero" | **Misleading.** It used a zero tolerance. On a 20-query corpus one query moving one place is 0.025 MRR, so a 0.006 "loss" is noise. **7 settings never lose more than 0.010.** The user's memory of slice 5 was right |
| "codestral wins the embedder ranking by 0.17" | **Wrong.** That compared models measured on *different corpus sets*. On the 3 corpora all five reached, the top three are within **0.012** — which **reproduces** the first run's "within 0.013" |
| "gemini-embedding-2 is worst of five" | **Unresolved, not worst.** Only 3 corpora, 2 of them saturated. No config bug found (dim 3072, norms 1.0, distinct vectors) |
| "embedding-2 hit its limit after 3 corpora" | **Wrong framing.** Those 3 were embedded by an EARLIER session the same day (1,253 texts). Tonight it got zero. `geo` alone is 73% of a day's quota |
| "send ~50 chunks per side" | **Does not stand.** Measured on a 100-chunk fixture where 50/side is *most of the corpus*, so it cannot separate "more chunks" from "more of the corpus". And 21k tokens **disqualifies Gemma** (16,000 input/min, 14,400 calls/day) |
| "slice corpora to vary size" | **Rejected by the user, correctly.** A slice is not an artifact: `geo[:50]` is the first 7% of a library in file order, with broken references. Nobody uploads that |

---

## C. THE RULE FOR `k` AND `w` — it depends on corpus SIZE

Measured with the ladder (one corpus, language and domain held still):

```
<= ~300 chunks   vector r@50 is already 1.000, so keyword can only DISTURB
                 -> k=5, w=0.05-0.15

>= ~400 chunks   r@50 falls, so keyword has something to ADD
                 -> k=60-90, w=0.7   (geo 400: r@50 0.929 -> 1.000)
                 -> costs MRR 0.539 -> 0.429, so only with a reranker after it

unknown size     k=5 w=0.3   never loses r@50 on any of 13, four times the
                             MRR gain of the k=5 w=0.15 slice 5 shipped
```

---

## D. STILL OPEN — what to run next

| # | open question | why it matters | cost |
|---|---|---|---|
| **D1** | **top-N, properly** — `scripts/score_answers.py` is BUILT; the run was cut off by a network collapse and its partial output must NOT be read as a result | my answer was measured on one 100-chunk fixture and does not stand | ~65 calls |
| D2 | **`SEARCH_LIMIT` window sweep** | still rests on ONE corpus (geo) from the first run | ~20 min |
| D3 | **`gemini-embedding-2` on 5 more corpora** | its rank is unresolved; the SECOND Google key has an unused 1,000/day | 884 texts |
| ~~D4~~ | ~~Google-first routing for small corpora~~ | **DONE and SHIPPED** - `SMALL_CORPUS_CHUNKS = 500` in `api/services.py`, three tests pin it. Verify it on real corpora via RESUME 4.3 | done |
| D5 | **merged vs per-side, two unrelated corpora** | quora gave 50% slots and identical scores; the harsh case never finished | ~50 calls |
| D6 | **Cohere and `rerank-3` as rerankers** | Cohere is the chain PRIMARY and is scored on one corpus | ~80 calls |
| D7 | **end-to-end time** | `WARN_MINUTES = 2.0` is still a guess | ~10 min |
| D8 | **fold all of this into CLAUDE.md** | none of the 7 corrections are written there yet | — |

---

## E. THE NEW top-N EXPERIMENT — the design the user specified

**Rejected:** slicing a corpus into 50/100/200-chunk pieces. A slice is not an
artifact.

**Accepted:** whole, real corpora at their natural sizes.

```
corpora   all 13, no slicing        78  82  85  146  193  335  382
                                   404 463 693 729 750 1160
N         5, 10, 20, 30, 50 chunks sent
grade     MECHANICALLY, using each fixture's OWN queries as the answer key
```

**The answer key already exists.** Every fixture has ~20 questions, each with
a ground-truth file and line. So the instrument is:

> give the model **N chunks**, ask it the corpus's own questions, and score:
> did it answer, did it cite, and **does the citation resolve to the
> ground-truth file and line**?

That runs on all 13 corpora, needs no hand-written `EXPECTED.md`, and measures
the one thing retrieval cannot: **did the model USE the evidence it was
given.**

**Why it answers the question my run could not:** `N` is a different thing at
each corpus size - 50 chunks is 50% of a 100-chunk artifact and 5% of a
1,000-chunk one. Across 13 natural sizes, if the best `N` stays flat it is
about the COUNT; if it tracks a percentage it is about COVERAGE, and 50 would
be far too few on a repository.

**Constraint that must survive the result:** a prompt over **16,000 input
tokens** disqualifies Gemma (14,400 calls/day) and leaves only Gemini Flash
(20/day). 20 chunks fit every tier; 68 do not.

---

## F. BUGS FOUND AND FIXED THIS RUN

| bug | consequence |
|---|---|
| `fnmatch` does not implement `**` | `**/*_test.go` kept every top-level test file. **cobra was 408 chunks including its tests**, really 193 |
| PDF anchors matched on exact text | 23 of 36 PDF drafts dropped on anchors that were really there. Fixed with whitespace-normalised, wrap-aware matching: papers went 4 → 20 usable queries |
| the embedding cache is keyed by corpus+model, not by the query set | a re-drafted fixture silently reused the OLD questions' vectors. Both reader and writer now refuse a cache whose count disagrees |
| `backend_out_of_capacity` and SSL timeouts raised instead of waiting | two corpora died mid-embed. `DEFAULT_TIMEOUT` allows 10s to CONNECT, which is tight on a slow link — a real user risk during ingest |
| embedding paced at codestral's PUBLISHED 50k tokens/min | measured 554k sustained with zero refusals; pacing to an unenforced number cost ~40 minutes |

---

## G. HOW TO RESUME

```
branch      slice8/measure-v2   (pushed, 18+ commits, main untouched)
corpora     .corpora/           (gitignored; env vars in .corpora/env.sh)
vectors     .cache/hybrid/      (paid for; validated to |1-cos| = 3e-10)
raw numbers .logs/results/*.json
```

Say: *"read `docs/slice8v2/` and continue slice 8 v2 on branch
`slice8/measure-v2`."*

---

# THIRD SESSION — 2026-09-17

Exit `80.240.20.89`, **AS20473 The Constant Company** (Vultr, Frankfurt).
Google answered **200 on both keys**; the probe decided it, not the ISP name.

**Read `FINDINGS.md` G14–G19 for the evidence.** This section is the decisions
only.

---

## 0. THE INSTRUMENT WAS BROKEN, and it was found before anything new was trusted

`PairScores` synthesised a score from a **listwise** reranker's ORDER and cached
it per pair. Every call therefore produced the same numbers 50…1, so two calls
covering different candidate sets for one query collided and the merged order
was arithmetic rather than anything the model said. **Five of thirteen rerank
corpora and all three merged benchmarks were void.** See **G14**.

**It does not reach production.** Nothing in `labpilot/` outside
`rerank/contracts.py` reads `.scores`; the shipped `rerank()` makes one call per
tier, keeps no cache, and never synthesises. The bug was created by the
*measurement's own optimisation*.

**What it cost:** the 13 clean caches migrated for free (211 rankings kept,
verified against a recorded number — `cobra` 0.634 → 0.794 with `calls: 0`), and
the 5 void corpora were re-run.

---

## A. DECIDED, with the run behind it

| # | decision | evidence |
|---|---|---|
| A1 | **Exact search ships.** Revisit at ~20,000 chunks in one artifact | unchanged — 12 artifacts, real instance, crossover ~700 rows |
| A2 | **Reranking ships**, `gemini-3.5-flash-lite` | **restated against each fixture's RESOLUTION**: **9 REAL gains** (+5.1 to +20.9 queries), **1 REAL loss** (`gson`, −2.7q), **3 nothing measurable** (`docs` −1.8q, `zod` −1.1q, `websocket` +1.5q). "Helped 10, hurt 3" overstated both sides |
| **A3** | **`SKIP_MARGIN` stays `None`** — **0.05 is OVERTURNED** | a global gate is worth **+2.4 queries out of 286** at its best setting (0.03) and **+1.5** at 0.05, while costing 2.4 on one corpus. The per-corpus best tau is 0.000/0.020/0.030/0.050/0.100 — never the same twice, so it is a fit, not a constant. Slice 6's answer is reinstated for the opposite reason: not because reranking is harmful, but because a working reranker leaves a gate nothing to save |
| A4 | **`s = 500` chunk size** | unchanged |
| A5 | **The free context header stays** | unchanged |
| A6 | **`codestral-embed` stays primary** — on CAPABILITY | **reproduced**: on the 3 corpora all five embedders reached, the top three are within **0.012** (codestral 0.594, cohere 0.598, gemini-001 0.606) |
| A7 | **Google counts TEXTS, not calls** | unchanged |
| A8 | **A small corpus goes to Google first** — SHIPPED | ⚠ **blocked in practice** by the `MAX_BATCH_SIZE` defect below |
| **A9** | **PER-SIDE reranking, confirmed** — merged is rejected | **43 of 57 queries starved a side.** `quora` 4/17, `papers+notebooks` 19/20, `cobra+log` 20/20. Merged halves the rerank calls and cannot see one of the two artifacts on most queries. The broken instrument had reported 0 of 20 |
| **A10** | **N = 20 chunks in the prompt** | best N on 9 of 13 corpora; as a **COUNT** cv 0.41 against 0.99–1.03 as a **share**, over a 15× range of corpus sizes. So N is a count, not a coverage fraction. **CORRECTED**: the experiment picked its chunks by VECTOR SEARCH ALONE - `chosen()` uses `dense_orders` and no reranker touches it - so it measures the DEGRADED path directly: **`VECTOR_TOP_N` should be 10 per side, not 25**. `RERANK_TOP_N` is NOT measured by it. Reranked chunks are better ordered, so their optimum is at most 20 and may be lower - an argument, not a number |
| **A11** | **Fusion switches on below `r@50` ≈ 0.95, and the method is SCORE FUSION** | every recall gain lands on the three corpora below 0.95; every corpus at or above it is exactly **+0.000**. `score a=0.85` gains on 8 of 13 (and LOSES on 5, worst -0.029) and takes the largest recall gain (`geo` +0.067 vs wRRF's +0.022); wRRF's entire MRR range (−0.006 to +0.016) is inside one-query resolution |
| **A12** | **There is NO routing signal in the rerank data** | weighted by query count over 286 queries, **every** question kind is positive (+0.102 to +0.303). `structure` — slice 6's −0.534 — is **+0.169**, third best. Its worst case is **one query** scored −0.500 |

---

## B. CORRECTED — claims made THIS session that did not survive

| what I said | what is true |
|---|---|
| "dilution is real and costs 13 points by N=100" | **Confounded.** The questions that only become answerable at N=100 are the ones retrieval ranked 51st–100th, i.e. the hard ones. On a **fixed** question set the fall is 8 points, and paired it is a **STEP at 20** (N=20→100 p=0.012) followed by a plateau (N=30→100 p=1.000) |
| "fusion rescues the corpora where reranking hurts" | **One case, two counter-cases.** Fusion+rerank wins on `gson` (0.697) and loses to vector+rerank on `geo` (−0.037) and `papers` (−0.049). B4 reproduces slice 6: **fusion's recall gain does not survive reranking** |
| "the best N is 5 on eight corpora" | **The denominator.** At N=5 the whole panel holds under three answerable questions per corpus, so a 1.000 is two of two. With a floor of eight, the best N is **20** on nine of thirteen |

---

## C. THE SAME ERROR, THREE TIMES — print the denominator beside every ratio

| where | the ratio | what it produced |
|---|---|---|
| top-N | `USED` over <3 answerable questions | "the best N is 5" |
| reranking | an MRR delta on 13 queries beside one on 45 | "helped 10, hurt 3" |
| routing | a per-kind delta with **one** query in the kind | `structure = −0.534`, which became a design principle |

None is visible in the value. All three were found by asking *how many
questions is that?*

---

## D. TWO PRODUCTION DEFECTS — still unfixed, and ONE BREAKS A SHIPPED DECISION

Not implemented here: this is a learning project and production code is the
user's to write. The design is recorded so it is a decision, not a rediscovery.

**1. `MAX_BATCH_SIZE = 96` is a MISTRAL constant with a global name.** It is
`floor(50,000 / 510)` from codestral's per-minute tokens and is used in three
places as if universal. At the measured mean of 341.6 tokens per chunk, 96
Google texts is ~32,800 tokens against a 30,000/minute ceiling — refused on the
**first batch**. `embed_batches()` halves only on a refusal containing the word
*token*, and Google's does not, so it **raises instead of halving**.

**A8 shipped `SMALL_CORPUS_CHUNKS = 500`, routing every small corpus to Google
first.** So the shipped routing cannot complete an ingest.

**2. `embedding_minutes()` counts HTTP calls where Google counts TEXTS**, and
models no daily request budget at all. It reports ~118 minutes for a
10,000-chunk Google ingest; the truth is **ten days**.

**The design both need:** `max_batch_size` and the unit of account move onto the
embedder (`Spec` / `Rate`) instead of a module-level constant, and `Rate` gains
a daily **request** budget beside its daily token budget.


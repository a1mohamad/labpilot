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
| D4 | **Google-first routing for small corpora** | Google is best on easy corpora AND its quota fits exactly that range: `<=500 chunks -> google`, `>500 -> codestral`. One `if` in `by_speed()` | free to try |
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

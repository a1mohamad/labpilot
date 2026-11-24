# Jev, the decision model

[Docs home](../README.md)

### Jev — the decision model, and the first paid tier (2026-09-19)

*Investigated at the user's request after it trended, measured on two corpora,
and shipped into chain 3. **It is not an LLM**, which is why it is here and not
in `CHAIN`.*

**What it is.** TypeSafe's "System One" model, launched 2026-09-15. It does not
generate text. It takes unstructured `state` plus typed `questions` and answers
**all of them in one parallel pass**, returning probabilities. Three types
only: `noul` (yes/no probability), `choice` (enum, max 255, plus a distribution
and a confidence) and `score` (an ordered scale of 2-10 levels). It cannot
rank, cannot do arithmetic, and cannot write a word.

#### Why a model with no ranking type is a reranker

It has `noul`, and that is the shape a cross-encoder produces:

```
s(q, d) in [0, 1]
```

So a ranking is N nouls in one call, sorted. Slice 6 proved our cross-encoders
are pointwise, so a per-document probability is a legitimate reranker.

#### The route, and the refusal that named it

**No TypeSafe account, no waitlist, no proxy — it is on the OpenRouter key this
project already has.** It is absent from `GET /api/v1/models` (447 chat models,
**zero** hits) because its modality is `text->decisions`, and
`/chat/completions` refuses it. That refusal is the documentation:

```
"typesafe/jev-1.13 is a decisions model and cannot be used with the
 chat/completions endpoint. Use the /api/alpha/decisions endpoint instead."
```

A **Netlify AI Gateway proxy** was designed and built first, because Netlify
injects `TYPESAFE_API_KEY` into its own compute and is the genuine no-card
route. It is **not used** and is not in the repository. Keep it only as the
fallback if OpenRouter ever refuses: Netlify Free is 300 credits/month with no
card, 180 credits to the dollar, but AI Gateway runs **only on Netlify
compute** — so it needs a proxy function and a second deployment target, and a
production deploy costs 15 of those 300 credits.

#### THE BALANCE LIED FOR A MINUTE, and it nearly became a false finding

```
call 1       ->  total_usage 0            identical to Cline's free tier
+60 seconds  ->  total_usage 0.000014364  to the digit, that one call
```

**It is billed.** $0.042 per million input tokens, output free. The account
counter is **not a live instrument** — and the paid control that settled the
Cline question did *not* discriminate here, because a free-provider control
also reported zero. Only waiting did.

> **"The balance did not move" is not evidence until it has had a minute.**
> Cline's rule was right and its instrument was not enough.

#### MEASURED — two corpora, 30-document window, codestral

| reranker | quora MRR | geo MRR | quora r@1 | geo r@1 |
|---|---|---|---|---|
| `gemini-3.5-flash-lite` | **0.799** | 0.681 | 0.706 | 0.622 |
| **Jev** | 0.770 | **0.712** | 0.647 | **0.644** |
| `gemini-3.1-flash-lite` | 0.745 | — | 0.588 | — |
| `gemma-4-26b-a4b` | 0.732 | — | 0.647 | — |
| `rerank-3-lite` (Voyage) | 0.725 | — | 0.588 | — |
| `rerank-v4.0-fast` (Cohere) | 0.669 | 0.621 | 0.471 | 0.511 |
| *vector alone* | *0.608* | *0.526* | *0.412* | *0.444* |
| `bge-reranker-base` | 0.520 | 0.355 | 0.353 | 0.244 |
| `ms-marco-MiniLM` (local) | 0.421 | — | 0.235 | — |

**One corpus each against flash-lite; the means are 0.740 and 0.741 —
indistinguishable.** Jev is the steadier of the two and wins **geo**, the
corpus with real headroom (vector `r@50` 0.867, not saturated at 1.000). It
beats every remaining tier on every corpus measured.

**It answers the question that killed two other rerankers: can it read code?**
Yes — Go *and* Python, beating the purpose-built cross-encoders on both. That
is exactly where `bge-reranker-base` and `ms-marco-MiniLM` failed.

**Latency, 30 documents, through the VPN and two network hops:**

```
Jev                     1.23s quora  ·  1.55s geo
gemini-3.5-flash-lite   1.3s
gemini-3.1-flash-lite   5.3s
gemma-4-26b-a4b        18.7s
gemma-4-31b            22.8s
```

About 15x faster than either Gemma at a better MRR on both corpora. The vendor
claims 70-500ms; ours includes the network, so that is not contradicted.

#### IT IS LISTWISE, AND THE SHAPE SAYS OTHERWISE

A noul per document looks pointwise, and a pointwise scorer may be cached per
`(query, chunk)`. **Jev may not.** Every document shares one `state`, so a
score is conditioned on its neighbours:

```
the same chunk:  0.62 among 2 documents
                 0.85 among 10 documents      drift 2.3e-01
```

Against an effect size of about 0.15. `verify_pointwise` refused to continue
and the cache moved to per-candidate-set — which is precisely the defect that
voided five corpora in slice 8 v2. **That check has now paid for itself
twice.**

#### Why it sits where it sits

**Tier 3 in the assembled chain, tier 2 as a model.** Assembled slot 2 is
flash-lite on the *second Google account* — the same model, another free
500/day. A billed tier between the two keys would spend money while a free
allowance sat unused, and would break the reason `_both_accounts` keeps the
twins adjacent.

**And it is the first non-Google tier, which is worth as much as the rank.**
Eight of twelve tiers are Google, and a refused VPN exit has already taken
every Google endpoint from this project for a week. The fallback below it is
Cohere's 1,000 a **month** and a Voyage that cannot take a 50-document window.
Jev is the only independent rerank capacity in the chain, and a test pins that.

#### It costs the 512MB budget nothing — measured, not assumed

```
marginal import cost of rerank/jev.py      0.6 KB
widest payload, 50 docs x 2,000 chars    145 KB peak, 107 KB on the wire
new dependencies                           NONE
requirements / docker / .env.example       unchanged
```

**0.03% of the Render ceiling**, against ~120MB for the local ONNX reranker
that is deliberately excluded. It needs **no new environment variable** —
`OPENROUTER_API_KEY` already serves three generator tiers — so Step 3's
container, `.env.example` and `smoke.yaml` are all untouched.

#### The mutation that survived, and the hole it found

Every other tier is *handed* a ranking by its provider. Jev is handed a
probability per document, **so the ordering is our code** — and nothing tested
it:

```
Jev placed first, ahead of flash-lite   -> fires ALONE
Jev dropped from the chain              -> fires, 2 tests
Jev pointed at a Google key             -> fires ALONE
sort ASCENDING, worst document first    -> NOTHING. 777 tests passed.
```

A reranker that sorts backwards is worse than no reranker, and it is invisible
downstream: the caller still receives a well-formed `Ranking` and cites the
least relevant chunk with full confidence. `tests/unit/rerank/test_jev.py`
closes it — re-running that mutation fires 3 tests, and reading dict insertion
order instead of the `dN` index fires alone.

#### WHERE ELSE IT FITS — Step 2, and none of it is built

Reranking is the only thing Jev does here today, and it is the smallest of its
uses. Read the capability library by OUTPUT TYPE rather than by task, and six
Step 2 nodes stop being prose:

| Step 2 node | output | Jev primitive |
|---|---|---|
| **the correspondence gate** | FULL / PARTIAL / NONE | `choice`, 3 options |
| **`verify(claim, code)`** | match / mismatch / absent | `choice`, 3 options |
| **§6 comparability** | YES / NO / CANNOT TELL | `choice`, 3 options |
| **`find_missing`** | is this B decision in A? | `noul` per column |
| **the `representation` check** | same idea, different language? | `noul` |
| **the four finding axes** | kind · box · basis · direction · magnitude | 7-way, 5-way, 3-way, 3-way `choice` + `score` |
| `summarize` · `find_bugs` · `explain_divergence` · `propose_next` | prose | ❌ impossible |

**Three of those are places this project has already MEASURED a failure**,
which is the real argument rather than the neatness:

- **§6 broke and we watched it break.** Slice 8 job 9: flash-lite wrote in §6
  that the two F1 numbers are not comparable, then compared them in §9. Prose
  can contradict itself across sections; **a typed value read by code cannot**.
- **The gate cannot live in a prompt** — this file's own rule: *"the model will
  find something, being unhelpful is against its training."* Jev has no urge to
  be helpful; it returns a distribution.
- **`verify` batches 5 claims per call only to save quota**, and this file says
  merging claims destroys detail. Jev removes the reason to batch.

It also brings **calibrated confidence** free, which axis 4 needs and which a
model's opinion of itself is not.

**Two limits, and the first is the one that matters.** Jev cannot write the
report, so it does **not** touch the 98.2% — it attacks the nine cheap calls,
not the expensive one. And it is unmeasured on all six: reranking asks *"is
this relevant?"*, `verify` asks *"does the code do what the claim says?"*, and
that is a harder question. **Build the typed nodes behind a small interface so
Jev is a second implementation later, not a rewrite** — that costs nothing and
is good design regardless.

#### A new instrument: `--cached-only`

`scripts/retrieval/score_rerank.py` can now re-derive a whole table from stored results
and spend **nothing**. It exists because the pointwise probe costs **2 real
calls per model**, so "just re-run from cache" would still have spent 2 of
Cohere's 1,000 a month to reprint numbers we already had. A cache **miss
raises** instead of quietly becoming a call — verified by asking for flash-lite
at window 30, which is cached only at 50.

#### What this does NOT settle

- **Two corpora.** This project's own rule: a fixture may REJECT, never
  CONFIRM.
- **flash-lite's quora 0.799 is from the record, not recomputed.** Only a
  window-50 cache exists for it, and re-running it was deliberately refused.
- **Window 30 only.** 50 geo chunks are ~23,700 tokens against the OpenRouter
  route's **32,000** ceiling, so `SEARCH_LIMIT` fits but barely — the same
  corpus-dependent window finding slice 8 made about Gemma.
- **`alpha` is in the endpoint path**, which is the provider's own warning.
  Route, shape and billing can change without notice; a 402 falls through and
  costs one request.
- **Step 2 owns the rest of it.** `verify` (match/mismatch/absent), the
  correspondence gate, §6 comparability and the four classification axes are
  all typed decisions Jev fits, and **none is built** — the capability library
  does not exist yet. Jev cannot write the report, so it does not touch the
  400-second problem.

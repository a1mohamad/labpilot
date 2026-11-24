# Full text: Slice 6 — DONE 2026-09-11: built, measured, and NOT switched on

[Docs home](../../README.md)

## Slice 6 — DONE 2026-09-11: built, measured, and NOT switched on

*The code is written, tested and mutation-verified. The measurement then said
something nobody planned for, and then said the opposite: **the cheapest
reranker makes retrieval clearly WORSE, and a better one makes it clearly
BETTER.** Same corpus, same window, same instrument — only the provider
changed. So the question slice 6 was built to answer, "does reranking help",
turns out not to be a question about reranking at all.*

*It still ships the way slice 5's keyword channel ships — built, unreachable,
nothing calling it — because the provider that helps cannot serve our window on
a free account and the one that can, hurts. **That is slice 8's decision, and
it now has real numbers under it instead of a quota-shape argument.***

**654 passed, 32 skipped, 1 xfailed, ruff clean. 14 of 14 mutations verified
real, 12 of them firing alone.** *(Those were the numbers the day slice 6
closed. It then landed on `main` re-committed piece by piece — ~40 commits, not
a merge — and the suite reads **715 passed, 46 skipped, 1 xfailed** as of
2026-09-13. `feat/reranking` is dead and behind `main`.)*


### What shipped

| module | holds |
|---|---|
| `rerank/contracts.py` | `Ranking` — an order, its scores, and which model produced it |
| `rerank/errors.py` | `RerankError` |
| `rerank/defaults.py` | `MAX_DOCUMENTS` 100 · `MAX_DOCUMENT_TOKENS` 510 · `RERANK_TOP_N` 10 |
| `rerank/base.py` | `HTTPReranker` — the template, written from three live probes |
| `rerank/cohere.py` · `voyage.py` · `cloudflare.py` | the three cross-encoders |
| `rerank/registry.py` | `RERANK_CHAIN`, in CLAUDE.md's order, recorded as unmeasured |
| `rerank/chain.py` | `rerank()` and `skip()` |
| **`retrieval/gate.py`** | `margin()` and `should_rerank()` — **core**, not the adapter |
| `scripts/retrieval/score_rerank.py` | the instrument, and it validates itself |

`rerank/` is the **seventh** package and the fifth adapter. `test_architecture`
fired the moment the folder appeared — *"['rerank'] belong to no layer"* —
exactly as the slice 6 notes predicted.


### Probing first found things the docs do not say

All three providers were probed live **before a line was written**, which is
the discipline slice 5 earned. Six findings, and three changed the code:

| probe | result | consequence |
|---|---|---|
| **a list of queries** | **400 · 400 · 422** | the no-batching rule is MEASURED now, on three independent providers, not read from docs |
| empty documents | Voyage 400, Cohere 400, **Cloudflare 500** | a caller's bug becomes *their* 500, so `_check_inputs` refuses locally |
| Cloudflare `top_k` | truncates the body, **identical neurons** | cost follows INPUT, never output — `top_k` buys nothing but a smaller response |
| Cohere, 3 documents | `search_units: 1` | per-CALL billing confirmed, and we send 50 of a free 100 |
| Cohere headers | `x-endpoint-monthly-call-limit: 1000` **and `x-trial-endpoint-call-limit: 10`** | a second ceiling this file never recorded |
| unknown field | Voyage **400**, Cloudflare **200 and ignored** | the embedder asymmetry, again: prefer the provider that refuses |

And the published neuron rate is exact, not approximate: 87 prompt tokens cost
**0.024589** neurons, which is `87/1e6 × 283` to five figures. So a real
50-document call is **3.52 neurons of 10,000 a day ≈ 2,840 calls daily**.


### The instrument validates itself before anything is believed

Two checks, both cheap, and the first one licenses the whole cache design.

**Is a cross-encoder pointwise?** The per-pair cache is only valid if the other
documents in a call cannot change a pair's score. Measured by scoring one pair
inside a 2-document call and a 10-document call:

```
Cloudflare   drift 2.4e-07 … 6.3e-07
Voyage       drift 0.0
```

So yes, pointwise — one forward pass per `(query, document)`, no normalisation
across the batch. **Had a provider normalised, every number below would have
been quietly wrong**, which is the identical-vectors bug of slice 4 wearing new
clothes. `score_rerank.py` refuses to continue if the drift exceeds `1e-6`.

**Can `r@50` move?** It cannot: a reranker only reorders what it was given. It
is reported on every run and was `True` on all four. A free check that says
*"the measurement is broken, not the reranker"* whenever it fails.


### MEASUREMENT 1 — `bge-reranker-base` hurt, on every run

**Read the model name, not the word "reranking".** Cloudflare's
`bge-reranker-base` over the dense top-50 — four runs, two corpora, two
embedders. A better model is measured two sections below and goes the other
way:

| corpus / embedder | | r@1 | r@5 | r@10 | r@50 | MRR |
|---|---|---|---|---|---|---|
| quora / codestral | vector | **0.412** | **0.941** | **0.941** | 1.000 | **0.608** |
| | + rerank | 0.353 | 0.824 | 0.882 | 1.000 | 0.528 |
| quora / google | vector | **0.529** | **0.941** | **1.000** | 1.000 | **0.674** |
| | + rerank | 0.353 | 0.824 | 0.882 | 1.000 | 0.527 |
| requests / codestral | vector | **0.533** | **0.800** | **0.933** | 0.978 | **0.646** |
| | + rerank | 0.311 | 0.644 | 0.711 | 0.978 | 0.476 |
| requests / google | vector | **0.533** | **0.800** | **0.844** | 1.000 | **0.650** |
| | + rerank | 0.311 | 0.644 | 0.711 | 1.000 | 0.477 |

**Headroom captured: −100%, −∞, −500%, −86%.** Not a tie, not noise: a drop of
0.17 MRR on 45 queries is the "large regression" that
[the saturated-fixture rule](../../step1/keyword-search.md#the-fixture-is-saturated-so-it-may-reject-and-may-not-confirm--2026-09-07)
explicitly licenses this fixture to report.

**And one row is worth more than the rest.** On `requests` the reranked numbers
are the **same to three decimals for both embedders** — 0.311 / 0.644 / 0.711,
MRR 0.476 against 0.477:

> **Once a reranker runs, it decides the order and the embedder almost stops
> mattering.** The embedder is then only responsible for `recall@50` — getting
> the answer into the window at all.

That has a direct consequence for slice 8, and it inverts one of its rules: the
embedder ranking on `recall@10` and `MRR` is the right criterion **only if
reranking stays off.** If it is ever switched on, rank embedders on `recall@50`
alone and spend the effort on the reranker instead.


### THE NEGATIVE RESULT WAS ABOUT THE PROVIDER — measured 2026-09-11

*This is the most important result of slice 6, and the project nearly did not
get it. Every number above was produced by the reranker we could afford to run
124 times, and the temptation was to write "reranking does not help us" and
close the slice. **The theory section forbade exactly that** — "may NOT
conclude which provider is best" — so a second provider was measured.*

`rerank-3-lite` cannot take 50 of our documents on a free account, so **both
providers were re-run at a 30-document window** — same corpus, same embedder,
same candidate set, same instrument. Only the model changed:

| quora / codestral, window 30 | tier | r@1 | r@5 | r@10 | MRR |
|---|---|---|---|---|---|
| **`rerank-3-lite`** (Voyage) | **2** | **0.588 +0.176** | 0.882 | **0.941** | **0.725 +0.117** |
| `rerank-v4.0-fast` (Cohere) | **1** | 0.471 +0.059 | 0.882 | **0.941** | 0.669 **+0.061** |
| vector alone | — | 0.412 | **0.941** | **0.941** | 0.608 |
| `bge-reranker-base` (Cloudflare) | 3 | 0.353 **−0.059** | 0.824 | 0.824 | 0.520 **−0.088** |

**All three tiers of chain 3 are scored, and the chain is in the wrong order.**
Cohere cost 17 calls of its 1,000 a month — 1.7%, and worth it: leaving the
*primary* unmeasured was a worse outcome than spending them. Today's order runs
**second-best, best, harmful**; on quality alone it should be reversed to
Voyage, Cohere, then nothing — `bge-reranker-base` is worse than not reranking
at all, so it does not belong in the chain on these numbers.

**But quality alone does not decide it, and that is the whole difficulty.**
Voyage wins and cannot serve a 50-document window on a free account. Cohere
works at full width and has 1,000 calls a *month* against a per-query cost.
Cloudflare has ~2,840 calls a *day* and hurts. **No tier is good on both axes**,
which is why slice 8 has to decide it with the window size in hand.

**A 43% relative gain in getting the right chunk FIRST, from the same 30
candidates the bi-encoder had already chosen.** And on the same data the cheap
model loses 14%. The spread between two rerankers is far larger than the spread
between reranking and not reranking.

> **"Does reranking help?" is not a question with an answer. It is a question
> about a specific model, and our two differ by 0.205 MRR — three times the
> whole headroom this slice was chasing.**

**Where the gain lands is exactly where theory said it would.** `r@10` does not
move at all (0.941 both ways) and `r@50` cannot move by construction. The entire
gain is at `r@1` and `MRR` — **ordering inside the window**, which is the only
thing a reranker is able to do. A result that showed `r@10` improving would have
meant the measurement was broken.

**And it inverts the gate.** With `bge`, the best threshold was the one that
never reranked. With `rerank-3-lite`:

```
tau      skipped     MRR
0.000    17/17      0.607     <- never rerank = vector alone
0.030    10/17      0.708
0.100     3/17      0.735     <- best
none      0/17      0.725     <- always rerank
```

**The gate stops being a way to avoid a bad reranker and becomes a small
optimisation on a good one** — 0.735 against 0.725, which is well inside noise
on 17 queries. `SKIP_MARGIN` stays `None` for that reason, not for the earlier
one: with a reranker worth running, there is almost nothing left for a gate to
save.


### The second corpus was STOPPED at 8 of 45, on purpose

*Voyage's 200M tokens are a **one-time** grant that never renews, and its
card-free 3 RPM / 10K TPM makes 45 queries about an hour of wall clock. The
user called it: do not spend a one-time grant on a heavy measurement. The 8
queries already paid for were scored instead, and they cost nothing more.*

**And they turn out to be a biased sample, which is the more useful finding.**
`queries.json` is grouped by category, so `R01`–`R08` are not eight arbitrary
queries — **they are the entire `constant` block**, the one category reranking
was already measured to be best at:

| requests, 8 `constant` queries, window 30 | r@1 | r@5 | r@10 | MRR |
|---|---|---|---|---|
| vector alone | 0.250 | 0.625 | 0.875 | 0.390 |
| `bge-reranker-base` | 0.375 | 0.625 | 0.875 | 0.514 **+0.123** |
| **`rerank-3-lite`** | 0.375 | **1.000** | **1.000** | **0.533 +0.143** |

> **Read this as a second measurement of the ROUTING finding, not as a second
> measurement of reranking.** On `constant` questions both rerankers help and
> the better one helps most — which is what the full 45-query breakdown already
> said (`bge` gained +0.190 there). It cannot be quoted as "reranking helps on
> requests", because the full run showed `bge` LOSING overall, and losing on the
> categories these 8 queries contain none of.

**A fixture ordered by category is not a fixture you can truncate.** Any partial
run of `queries.json` samples one `asks` value, so the first `k` queries are a
category study wearing a corpus study's clothes. Worth remembering before the
next expensive measurement is cut short.


### NINE RERANKER CONFIGURATIONS SCORED — and CONFIG matters as much as MODEL

*Same corpus, embedder and 30-document window throughout, so the column is
comparable end to end. The last two rows exist because the user refused
"gemma is unusable" and said **"something in your setup is wrong."** It was.*

| reranker | kind | MRR | r@1 | latency | budget |
|---|---|---|---|---|---|
| **`gemini-3.5-flash-lite`** *(tuned)* | LLM, listwise | **0.799** | **0.706** | **1.3 s** | 500/day |
| **`gemini-3.1-flash-lite`** *(tuned)* | LLM, listwise | **0.745** | 0.588 | 5.3 s | **its own 500/day** |
| `gemma-4-26b-a4b-it` *(tuned)* | LLM, listwise, **MoE** | **0.732** | **0.647** | 18.7 s | **its own 14,400/day** |
| `gemma-4-31b-it` *(tuned)* | LLM, listwise | **0.732** | 0.588 | 22.8 s | **14,400/day** |
| `rerank-3-lite` (Voyage) | cross-encoder | 0.725 | 0.588 | — | 200M once · 3 RPM |
| `gemini-3.5-flash-lite` *(untuned)* | LLM, listwise | 0.706 | 0.529 | 3.9 s | 500/day |
| `rerank-v4.0-fast` (Cohere) | cross-encoder | 0.669 | 0.471 | — | 1,000/**month** |
| *vector alone* | — | *0.608* | *0.412* | — | free |
| `bge-reranker-base` (CF) | cross-encoder | 0.520 | 0.353 | — | ~2,840/day |
| `ms-marco-MiniLM` | cross-encoder, local | 0.472 | 0.294 | — | unlimited |
| `ministral-3b-2512` | LLM, listwise | 0.440 | 0.176 | — | rate-limited |

> **Two rows are the SAME MODEL, 0.093 MRR apart.** Tuning flash-lite moved it
> further than the gap between flash-lite and Cohere's purpose-built
> cross-encoder. **How you configure a model is not a detail beside which model
> you pick — here it was the larger effect.**


### `gemma-4-26b-a4b` — the MoE sibling, and MoE bought less than expected

25.2B total parameters but only **~3.8B active**, so it should be far faster
than the 31B dense model. Measured, three samples each on one 30-document call:

```
gemma-4-26b-a4b (MoE, 3.8B active)   median 18.7 s
gemma-4-31b     (dense, 31B)         median 22.8 s
gemini-3.5-flash-lite                median  1.5 s
```

**18% faster, not the 5-8x the active-parameter count suggests.** Both Gemma
models are ~13x slower than flash-lite. **The bottleneck is Google's serving of
these models, not their size** — the same conclusion the 13-token floor test
reached (12.1 s to do nothing).

**On quality it ties the 31B on MRR and beats it on `r@1`** — 0.647 against
0.588, the second-best `r@1` of anything measured. For a first-position metric
that is the one that matters, so the MoE is the better of the two Gemmas on
both axes.

**And it has its own separate 14,400/day**, because Google's quota is per
model. The two Gemmas together are 28,800 calls a day.

**One real defect: it sometimes returns an empty ranking.** A bare `[]` —
schema-valid, and an opinion about nothing. Measured once in 17 queries (~6%),
and it killed a run outright before the parser learned to treat a decline as
"retrieval's order stands", which is what `skip()` already means elsewhere.

> **A decline is invisible in MRR**, because keeping the retrieval order scores
> exactly like vector alone. A model that silently abstains 6% of the time
> looks 6% more average, never 6% more broken. The rate has to be counted
> separately or it cannot be seen at all.


### `gemini-3.1-flash-lite` — dominated on quality, valuable on QUOTA

Measured 2026-09-11, same corpus and window as every row above:

```
                        MRR     r@1     latency
gemini-3.5-flash-lite  0.799   0.706     1.4 s
gemini-3.1-flash-lite  0.745   0.588     5.3 s
```

**3.5 dominates 3.1 on every axis** — better MRR, better `r@1`, and ~4x faster.
On quality alone there is no reason to prefer the older one.

**Its value is that it is a different MODEL, and Google's quota is per model.**
This file measured that on 2026-08-16: the 429 body says
`GenerateRequestsPerDayPerProjectPerModel-FreeTier`, and `quota_pool` exists
because of it. So 3.1 is not a weaker copy of 3.5 competing for the same
budget — it is **a second, independent 500/day** at MRR 0.745, which is still
above Voyage, Gemma and Cohere.

That makes the two Flash-Lite models a natural pair at the top of a rerank
chain: 1,000 calls a day between them, no shared bucket, and the fallback is
the third-best reranker measured rather than a degradation.

**Recall barely moves for any of them**, and that is the fixture rather than
the models: `r@5` and `r@10` sit at 0.941 for vector alone and for every
reranker. On this corpus only `r@1` and MRR have room, which is exactly what
[the saturated-fixture rule](../../step1/keyword-search.md#the-fixture-is-saturated-so-it-may-reject-and-may-not-confirm--2026-09-07)
predicts and another reason the full `requests` run belongs to slice 8.


### The two settings that did it, both measured

**1. `thinking=None`.** Every Gemini tier ships `thinkingLevel: MEDIUM`. On a
ranking task that is waste:

```
flash-lite, IDENTICAL 109-token answer, one 30-document call
  thinking MEDIUM (shipped)   3.88 s   930 thought tokens
  thinking LOW                2.24 s   351
  no thinking field           1.28 s     0
```

**3x the latency and 930 tokens to produce the same answer.** CLAUDE.md has
said since 2026-08-17 that thinking is a per-task knob, never a global setting.
This is the number behind it, and the shipped default is wrong for this task.

**2. A JSON response schema.** `responseMimeType: application/json` plus an
integer-array schema. On gemma, one 30-document ranking went **45.5 s → 14.4 s**
and the reply stopped being prose wrapped around an answer.

`GeminiProvider.generation_config` now carries both — the Gemini-shape twin of
`OpenAICompatibleProvider.extra_body`. Step 2's claim extraction needs the same
field for its own reason (*"output a fixed shape so the next node parses
instead of guessing"*), so it has a scheduled consumer.


### Gemma: I was wrong about it TWICE, and the user was right to push

**First I recorded it as unable to follow the output format.** That was **my
parser**. Gemma reasons in prose, walking the chunks in order — *"Chunk [1] …
Chunk [2] … Chunk [3]"* — and gives its ranking last. A left-to-right scan for
numbers read the REASONING and returned the identity order. Its real reply
ended `3, 1, 2, 4`, which is correct.

> **Reading the first 90 characters of a reply is not reading the reply.** A
> model that reasons puts its answer at the END; a parser that scans from the
> front measures the thinking and calls it the conclusion.

**Then I recorded it as too slow at 95 s, and closed the question.** The user
did not accept it — *"it's a much lighter model, with much more quota,
something in your setup is wrong"* — and pushing produced the schema finding
that took it to 14.4 s and the top three.

**The premise in that objection was actually inverted**, and that is worth
keeping too: `gemma-4-31b-it` is a **31-billion-parameter dense** model, while
`gemini-3.5-flash-lite` is Google's smallest, fastest tier. Gemma is the
*heavier* one — its larger free quota made it look cheaper. Measured on a
13-token prompt, which isolates serving latency from everything else:

```
gemma-4-31b-it          12.1 s      <- the floor, doing nothing
gemini-3.5-flash-lite    0.8 s
```

**A wrong reason can still find a real bug.** The objection was mistaken about
which model is lighter and completely right that the setup was broken.


### What this does to chain 3

The shipped chain is Cohere, Voyage×2, Cloudflare — and on these numbers
**the two best rerankers are not in it at all**, while the last tier is worse
than not reranking. Slice 8 now chooses among **nine measured configurations**
rather than ordering four by quota shape.

The live trade it must make is no longer quality — it is **latency against
budget**: flash-lite is best and fastest on 500 calls/day; gemma is second and
11x slower on 14,400/day. `verify` needs one call per claim, so at ~30 claims
that is 40 s against 7 minutes.

> **Quota is not the only budget. Latency is one too, and it is the one nobody
> writes down.**


### The cross-encoder table, and the generation line inside it

*The local ONNX model was added on 2026-09-11 and it completes the picture.
CLAUDE.md asked for the measurement to run on it from the start; Cloudflare was
substituted, and that substitution is what produced the first, wrong headline.*

| reranker | trained | where | MRR effect |
|---|---|---|---|
| `ms-marco-MiniLM-L-6-v2` | 2021, MS MARCO | **local, free, unlimited** | **−0.136 … −0.202** |
| `bge-reranker-base` | 2023 | Cloudflare | **−0.088 … −0.170** |
| `rerank-v4.0-fast` | modern | Cohere | **+0.061** |
| `rerank-3-lite` | modern | Voyage | **+0.117** |

> **The dividing line is the model's GENERATION, not local versus API, and not
> price.** Both MS-MARCO-era cross-encoders hurt our retrieval on every run.
> Both modern rerankers help. Free and paid appear on both sides of the line,
> so cost explains nothing.

**Why that is the better conclusion.** "The provider matters" is true and shallow
— it invites picking a vendor. "Old cross-encoders trained on web prose fail on
code, newer ones do not" is a *mechanism*, and it predicts: it is the same
reason `bge` collapsed on `structure` and `behaviour` queries, the ones that ask
what code DOES.

**And it takes away the cheap answer to Step 2's cost problem.** The local model
is the only reranker that BATCHES — no rate limit, no call count, every pair in
one forward pass — which is exactly what `verify` needs at one call per claim.
It is also one of the two that make retrieval worse. So the thing that solves
the cost problem does not currently solve the quality problem, and slice 8
cannot treat "run it locally" as a free escape.

**A newer local model is the open move**, not a rejected one. `bge-reranker-v2-m3`
and the Qwen3 rerankers are ONNX-exportable and modern; none was tried, because
the point of this exercise was the measurement and not a model hunt.

**The instrument caught something real on the way in.** The pointwise check
refused the local model at first: the same pair drifts between a 2-document and
a 10-document call. The tokenizer output is bit-identical, so the cause is int8
GEMM being sensitive to batch **shape**. Padding to a fixed 512 — the obvious
fix — made it fifty times worse, moving one pair from 0.0003 to 0.72, because
490 of 512 tokens become padding and that ONNX export's attention mask does not
fully neutralise them.

> **Set a numerical tolerance against the EFFECT SIZE, never against zero.**
> The local model moves MRR by ~0.15; a cache accurate to 1e-2 cannot invent or
> hide that. The API models stay at 1e-6, because they measure 0.0 and 2e-07.


### What this does NOT establish, stated before anyone quotes it

- **The provider flip rests on ONE corpus.** `quora` is the **saturated**
  fixture this file has warned about since 2026-09-07: 17 queries, `r@5`
  already 0.941, and a 30-document window that is 37% of the whole corpus. The
  full `requests` run is owed, and it belongs to slice 8 — where Cohere must be
  measured anyway, so all three can be scored in one pass.
- **One embedder, one window.** 30 documents, not the 50 the pipeline retrieves.
- **Cohere is still unmeasured**, and it is the chain *primary*. Its 1,000 calls
  a month are one bucket shared with chat and embed, and a run is 45 calls.
- **It does not reopen fusion.** Measurement 4 showed `wRRF`'s gain vanishing
  under `bge`; whether it survives under a reranker that actually orders well is
  a different question, and an unasked one.


### What it DOES establish, and it changes slice 8's job

1. **The candidate chain order in the slice 6 theory would have been actively
   harmful.** That order — local, then **Cloudflare**, then Voyage, then Cohere
   — was argued from quota shape, and quota shape put the one model we have
   measured to *hurt* retrieval at the front of the chain.
2. **Chain 3's order is now a quality question with evidence**, not a budget
   question. Slice 8 owns it, and it must measure Cohere before deciding.
3. **"Cheapest instrument" and "best instrument" are different choices**, and
   slice 6 needed both: Cloudflare's ~2,840 calls a day made 124 measurements
   affordable, and Voyage's stronger model made the result mean something.

> **Measure the thing you will ship, not only the thing you can afford to
> measure.** The affordable instrument answered a different question, and it
> answered it confidently enough to have closed the slice on a false premise.


### MEASUREMENT 2 — how many chunks to send

On `requests / codestral`, the delta at every window:

```
   window   before    after    delta
    top-1    0.533    0.311   -0.222
    top-5    0.800    0.644   -0.156
   top-10    0.933    0.711   -0.222
   top-20    0.978    0.889   -0.089
   top-50    0.978    0.978   +0.000
```

**There is no window at which this reranker helps.** The loss shrinks as the
window widens, which is the shape you would expect from a ranker that is
shuffling rather than sorting: the wider the window, the less its order matters.

So `RERANK_TOP_N = 10` is shipped as a **number with no evidence behind it
yet** — the question "how many to send" cannot be answered from a reranker that
should not be sending any. It is the first thing to re-measure once a provider
that helps is found.


### MEASUREMENT 2 WAS MIS-SPECIFIED, and the correction is the useful part

*Slice 6's plan said measurement 2 would decide "how many chunks to send" using
`recall@N`. It cannot, and no amount of running it would have helped. This is a
flaw in the plan, found by executing it.*

**`recall@N` only ever rises with N:**

```
r@1 0.533    r@5 0.800    r@10 0.933    r@20 0.978    r@50 0.978
```

$$
\text{recall@}N \text{ is monotone in } N
$$

So asking retrieval "what is the best N?" can only ever answer *"bigger"*. The
reason to stop sending more is **dilution and lost-in-the-middle**, and that
term does not exist until a model reads the prompt:

$$
P(\text{good report}) \approx
\underbrace{P(\text{answer is in the } N)}_{\text{rises with } N}
\times
\underbrace{P(\text{the model uses it})}_{\text{falls with } N}
$$

**The left factor is a retrieval measurement. The right one is a generation
measurement.** Slice 6 only ever had the left, so `RERANK_TOP_N = 10` ships as
a placeholder with no evidence, and its comment says so.


### What the frontier DID settle, for free

Retrieval can find where MORE stops helping, even though it cannot find where
FEWER starts. That is an upper bound, and it is worth having:

| N | quora: vector | + Voyage | requests: vector | + `bge` |
|---|---|---|---|---|
| 1 | 0.412 | **0.588** | 0.533 | 0.311 |
| 3 | 0.765 | **0.882** | 0.711 | 0.600 |
| 5 | **0.941** | 0.882 | 0.800 | 0.667 |
| 10 | 0.941 | 0.941 | 0.933 | 0.778 |
| 15 | 0.941 | 0.941 | **0.978** | 0.889 |
| 20 | 0.941 | 0.941 | 0.978 ← flat | 0.911 |
| 50 | 1.000 | 0.941 | 0.978 ← flat | 0.978 |

1. **A good reranker shifts the curve LEFT.** Reranked N=3 (0.882) beats vector
   N=3 (0.765), and reranked N=1 beats vector N=1 by +0.176. That is what "you
   can cut harder when the reranker is good" means numerically.
2. **A bad one shifts it RIGHT.** `bge` needs **N=30** to reach what vector
   reaches at **N=15** — it pushes answers down, so you must send more to
   compensate.
3. **Nobody should send 50.** On `requests`, vector alone is flat from 15
   onward: 15 → 50 buys **0.000** and costs 35 chunks of dilution.

**So N ∈ {20, 50} is eliminated for free, and generation only has to choose
among {3, 5, 10, 15}.** That is the expensive measurement made four times
cheaper by a free one.


### The design this produced — TWO numbers, not one

*The user's, and it is better than what this file had.* One `RERANK_TOP_N` for
both paths is wrong, because the two paths have different recall curves:

```
measure once:   best N with a reranker      ->  RERANK_TOP_N
measure once:   best N on vector alone      ->  VECTOR_TOP_N

at runtime:     a reranker answered?  ->  send RERANK_TOP_N
                gate skipped, or all tiers failed?  ->  send VECTOR_TOP_N
```

**And do not optimise "recall and MRR against chunk count" directly** — there
is no exchange rate between them, so any weighting is arbitrary. Use the
frontier to *eliminate dominated N* (free), then let answer quality pick the
survivor (generation).

**One concrete code consequence for slice 7.** `skip()` currently truncates to
whatever `top_n` it was handed. When the gate skips or every tier fails, the
caller must pass the **vector-path** N, not the rerank one — otherwise the
degraded path silently uses a number calibrated for a path that did not run.

> **A metric that only moves one way cannot choose a middle.** Before planning
> a measurement, check that the number you intend to read is capable of having
> an optimum at all.


### MEASUREMENT 3 — the gate, and the answer is "skip everything"

Sweeping the dense margin `m = s₁ − s₂`. `τ = 0.000` means *skip whenever the
best hit leads at all*, which is effectively always:

| τ | quora/codestral | quora/google | requests/codestral | requests/google |
|---|---|---|---|---|
| **0.000** (skip all) | **0.608** | **0.674** | **0.646** | **0.650** |
| 0.005 | 0.652 | 0.683 | 0.619 | 0.593 |
| 0.010 | 0.638 | 0.616 | 0.565 | 0.529 |
| 0.020 | **0.716** | 0.621 | 0.569 | 0.562 |
| 0.030 | 0.685 | 0.621 | 0.547 | 0.508 |
| 0.050 | 0.639 | 0.582 | 0.541 | 0.477 |
| 0.100 | 0.592 | 0.582 | 0.498 | 0.477 |
| none (rerank all) | 0.528 | 0.527 | 0.476 | 0.477 |

*(MRR. The best row per run is bold where it is not `τ = 0`.)*

**The best gate is the one that never reranks** — on 3 of 4 runs. The two
exceptions sit on the 17-query corpus and the sweep there is **non-monotonic**
(0.652 → 0.638 → 0.716 → 0.685 → 0.639), which is the signature of noise on a
tiny sample. Picking `τ = 0.02` because it is the maximum would be fitting a
threshold to 17 queries.

**So `SKIP_MARGIN` ships as `None`, meaning the gate is OFF.** That is not
indecision: a threshold here is **calibrated, never chosen**, and what the
calibration produced is *"this reranker should not run"* rather than a number.
The mechanism the gate was built for is still supported, and by our own data —
reranking does worst exactly where the first stage was most confident.


### MEASUREMENT 4 — slice 5's fusion gain does not survive

`requests / codestral`, with the BM25 channel on:

```
vector alone                 r@1 0.533  r@5 0.800  r@10 0.933  MRR 0.646
wRRF k=5 w=0.15              r@1 0.556  r@5 0.822  r@10 0.933  MRR 0.662   <- slice 5 reproduced
vector          -> rerank    r@1 0.311  r@5 0.644  r@10 0.711  MRR 0.476
wRRF k=5 w=0.15 -> rerank    r@1 0.311  r@5 0.622  r@10 0.711  MRR 0.472
```

**Two things at once.** Slice 5's finding reproduces independently — `wRRF`
really does beat vector alone, by about one query. And **the gain vanishes the
moment a reranker runs**: `r@10 +0.000`, `MRR −0.005`.

This file predicted it in those words — *"the gain is real, small, and in the
region slice 6 overwrites"* — and it is now measured rather than reasoned.
Fusion's value therefore depends entirely on whether reranking ever ships, and
the two decisions cannot be taken separately. Both belong to slice 8.


### The finding that outlives the negative result: it is a ROUTING signal

Breaking the `requests` result down by the `asks` label the query file carries:

| asks | n | vector MRR | + rerank | delta |
|---|---|---|---|---|
| **constant** | 10 | 0.354 | **0.540** | **+0.186** |
| **error** | 5 | 0.600 | 0.613 | +0.013 |
| api | 7 | 0.456 | 0.289 | −0.167 |
| behaviour | 14 | 0.787 | 0.530 | −0.258 |
| **structure** | 9 | **0.926** | 0.392 | **−0.534** |

**Now compare it with what slice 5 measured for BM25, on the same corpus:**

| asks | vector | bm25 | rerank |
|---|---|---|---|
| constant | 0.354 | 0.423 | **0.540** |
| error | 0.600 | 0.612 | 0.613 |
| behaviour | 0.787 | 0.657 | 0.530 |
| api | 0.456 | 0.175 | 0.289 |
| structure | **0.926** | 0.426 | 0.392 |

**The cross-encoder and BM25 win on the same question type and collapse on the
same one.** That convergence is the useful result of this slice, and it has a
mechanism behind it rather than only a number:

> **A reranker and a keyword ranker are both LOCAL relevance models** — they ask
> *"does this document answer this query?"*. A whole-chunk embedding answers a
> different question, *"what is this chunk about?"*, and that is what a
> `structure` query needs. So they are not three grades of the same tool; they
> are two different tools.

And `constant` is the `CLIP_NORM` shape — *"what is this value set to"* — which
this file has called out since slice 1 as a distinct retrieval need. Reranking
beats **both** vector (0.354) and BM25 (0.423) there, at **0.540**.

**This is the third independent time the same split has appeared**: the embedder
missed `D2` at rank 46, BM25 rescued it, and now the cross-encoder ranks that
family best of all. The conclusion is not "pick the best ranker". It is
**route by question type**, which is already a rule in this file and now has
three measurements under it.


### The bad result was PROBED, not accepted — 2026-09-11

*"It doesn't make any sense that the Cloudflare model gets that ugly result" —
the user, and the instinct was right to act on. A model with a good reputation
scoring WORSE than no reranking is more often a bug in the caller than a bad
model. Four checks, and the integration survived all four.*

| suspicion | test | result |
|---|---|---|
| **512-token truncation** — BGE's tokenizer is 2.7x less efficient on our code, so a 230-token chunk could really be 600+ | score prefixes of one chunk; identical scores mean the tail was never read | **no truncation** — 0.00105 → 0.00263 → 0.00304 → 0.00327 as the prefix grows |
| **`id` is not the index at scale** | plant an obvious answer at positions 0, 37 and 49 of a 50-document call | **correct every time**, score 0.9999, and the runner-up identical across all three |
| **the response is silently capped** | count what comes back from 50 | **50 of 50** |
| **we picked an old model** | list Cloudflare's rerankers | **there is exactly one** |

**So the wiring is right and the model really does rank our code badly.** Then
the failure was read rather than summarised, and it has a shape:

```
23 queries WORSE   13 BETTER   9 unchanged

R32 [api]        place 1 -> 36      the five worst cases are ALL
R40 [structure]  place 1 -> 32      queries the bi-encoder already
R12 [behaviour]  place 1 -> 18      had at place 1
R15 [behaviour]  place 1 -> 16
R19 [behaviour]  place 1 -> 15

best gains:  6 -> 3,  4 -> 1,  7 -> 2,  8 -> 5
```

> **When the first stage is already right at #1, reranking has zero upside and
> maximum downside.** It cannot promote what is already top; it can only push
> it down. Losses of +14 to +35 places against gains of 3 to 5.

That is the literature's *"reranking can make results worse when the first
stage was already confident and correct"*, measured on our own corpus — and it
explains the gate sweep, where "skip everything" won. It is also **not** a
property of reranking: `rerank-3-lite` raised `r@1` from 0.412 to 0.588 on
quora, so it promotes correct answers where `bge` demotes them.

**A process note, because it nearly cost the finding.** The first version of
this diagnostic compared `(index, score)` tuples against a set of ints, so
every lookup silently reported "not found" and the script announced a maximum
damage of zero — flatly contradicting the aggregate it was meant to explain.
**Two numbers from the same data disagreeing is a bug, not a subtlety**, and
the disagreement was the only thing that revealed it.


### Two confounds tested and eliminated

**The chunk header is not the problem.** We send `chunk.embed_text` — header
plus text — and a header like `[adapters.py · class HTTPAdapter · lines 80-120]`
could plausibly be noise to a model that reads query and document together.
Measured on `requests / codestral` with `--no-header`:

```
with header     r@10 0.711   MRR 0.476
without header  r@10 0.711   MRR 0.469
```

Identical at `r@10`, slightly *worse* without. So the header is not the cause,
and it is not worth stripping.

**The corpus ratio is a real limit, and it is named rather than hidden.** The
top-50 window is **61% of the 82-chunk quora corpus** and **15% of the
335-chunk requests corpus**. At the 1,000–10,000 chunk artifacts this project
actually targets it would be **0.5–5%**. Reranking 61% of a corpus is not the
production task, and every number above inherits that caveat.


### Provider corrections, measured and then confirmed on Voyage's own dashboard

**Two things this file recorded about Voyage were wrong, and both matter.**

**1. The rate limit was the BILLED tier's.** Platform Accounts claimed
*"4M TPM / 2,000 RPM"*. A card-free account gets **3 RPM and 10K TPM** — read
from Voyage's own Rate Limits dashboard, and stated in its 429:

> *"You have not yet added your payment method … reduced rate limits of 3 RPM
> and 10K TPM."*

**2. The 200M free grant does not cover the model we chose.** The same page
says the first 200 million tokens are free **"for Voyage series 3 models"**.
CLAUDE.md picked `rerank-2.5-lite` on 2026-08-11 — series 2.5, and therefore
outside the grant. `rerank-3-lite` and `rerank-3` both exist and both answer,
probed live 2026-09-11. **The registry now uses `rerank-3-lite`**: a generation
newer *and* the one the free tokens actually pay for.

**And pacing does not rescue it, which took two wrong hypotheses to learn.**
The limit is *"requests or tokens in the most recent minute"*, so a single call
counts against it whole — a call bigger than 10K tokens is refused however long
you wait. Measured on the `requests` corpus, each after a clean 90-second wait:

| documents | est. tokens | result |
|---|---|---|
| 50 | ~16,900 | **refused** |
| 40 | ~13,100 | **refused** |
| **30** | ~8,900 | **passed** |

> **Voyage cannot serve our `SEARCH_LIMIT = 50` window on a card-free account
> at all.** Not slowly — *not at all*.

That is the Groq shape exactly: alive, and unreachable for the real request
size. The chain already handles it correctly — `RerankError` falls through to
Cloudflare — at a cost of one wasted request per call, which is the argument
slice 8 needs when it revisits the order.

**A pre-flight token check was considered and REFUSED**, and the reason is this
file's own rule that *an estimate is not a budget*. Our `chars / 3` estimator
puts a 50-chunk quora call at ~11,400 tokens, which **passes**, and a 40-chunk
requests call at ~13,100, which **fails**. An estimator that straddles the real
boundary in both directions would refuse working calls to avoid wasting one
request in sixteen thousand. Check the threat before writing the guard.

**The other two providers needed no correction, only completion.** Cloudflare's
published 283 neurons per 1M input tokens is exact to five figures, and Cohere's
headers carry a second ceiling nobody had recorded —
`x-trial-endpoint-call-limit: 10` beside the monthly 1,000.

> **A provider's published rate limit is not your account's rate limit, and its
> free grant may not cover the model you picked.** Both facts were sitting on
> the provider's own dashboard the whole time; neither is in its API.


### The slice 6 closing review — 2026-09-11

*The standing question across the whole system, and the RAG system in
particular: **which real failure is still unprotected?** Two gaps, and the
first is the highest-risk untested seam in the pipeline.*

**1. Nothing checked the translation between two number spaces that look
identical.**

```
store.search()  ->  SearchHit.chunk_index    an ID in the corpus
rerank()        ->  POSITIONS into the list it was handed
```

`rerank/` may not import `store/`, so **neither package can check this** — it
belongs to the caller, and slice 7 is about to write it. CLAUDE.md's own
warning for exactly this shape: *"the position is what the caller uses to look
a chunk back up, so an index off by one cites the wrong file and line with full
confidence."*

`tests/integration/test_retrieval_to_rerank.py` runs chunk → store → search →
rerank → back to real chunks. **Chunk ids start at 100**, so a position used as
an id is provably wrong — the same correction slice 5 needed when a fixture
numbered its chunks from zero and could not tell an id from a row.

**2. The four tiers that now LEAD chain 3 had no liveness check.** The models
we intend to use most were the only ones nobody was watching. Four calls a week
against 500/day and 14,400/day budgets. They also assert `declined == 0`,
because **a decline keeps the retrieval order and is invisible in the ranking
itself**.

**Two mistakes in my own new tests, both corrected rather than worked around.**
The fakes were bare functions and the `Reranker` protocol needs a `.rank`
*method*. And the file claimed `Ranking` refuses an out-of-range position — **it
does not, and cannot**, because it never learns how many documents were sent.
The range check lives in `HTTPReranker._validated`, which does know.

> What actually protects the citation is that the caller indexes a list, so an
> impossible position raises `IndexError` rather than quietly naming the wrong
> chunk. **Loud is the property worth pinning; "impossible" was wishful.**

**Refused deliberately:** an `api/` test, because `api/` still does not import
`rerank` — `test_error_boundaries` stays green and will fire the day slice 7
wires it, which is the guard working rather than a gap.


### What slice 6 deliberately did NOT do

- **Nothing calls `rerank`.** Same as slice 5's keyword channel: no flag, no
  setting, because a flag nobody reads is dead configuration. Slice 7 wires it
  if slice 8 says it should run at all.
- **`ministral-3b-2512` is not built.** Tier 4 of chain 3 is LLM-as-reranker — a
  different mechanism needing a prompt, a parse and its own failure modes,
  reached only when all three cross-encoders are gone. Recorded unbuilt rather
  than half-built, like HNSW on the shelf.
- **The local ONNX model is not installed.** CLAUDE.md preferred it as the
  measurement instrument; Cloudflare's ~2,840 calls a day plus a per-pair cache
  gave the same repeatability with no 200MB dev install and no model download.
  It is still the only option that can **batch**, so it stays on slice 8's list.
- **No `api/` test, and `test_error_boundaries` stayed green** — correctly,
  because `api/` does not import `rerank` yet. It will fire the day slice 7 does,
  which is the guard working.


### What slice 6 may NOT conclude, restated against its own results

| may conclude | may NOT conclude |
|---|---|
| `bge-reranker-base` hurts our retrieval, on 2 corpora × 2 embedders | **that reranking hurts** — a better model helps, measured |
| `rerank-3-lite` helps, on **one saturated corpus** | that reranking helps **in general** — one corpus, 17 queries |
| the provider matters more than the stage does | that chain 3's order is right — all three are scored now and it is **wrong** on quality |
| the gain and the loss are question-type shaped | that the chain-3 order is settled — still unmeasured end to end |
| fusion's gain does not survive `bge` | that fusion is dead — untested under a reranker that ORDERS well |
| a cross-encoder is pointwise, so pairs cache | the real value of `r` — that needs Step 2 |
| Voyage cannot serve a 50-document window free | how `RERANK_TOP_N` should be set — `recall@N` is MONOTONE and cannot have an optimum |


### The r@1 / MRR question is SETTLED

START HERE reported `recall@1 0.645` against `recall@50 0.994`, and the slice 5
table reported `MRR 0.645`. They could not both be that value. Measured:

| run | true r@1 | MRR |
|---|---|---|
| quora / codestral | **0.412** | 0.608 |
| quora / google | **0.529** | 0.674 |
| requests / codestral | **0.533** | 0.646 |
| requests / google | **0.533** | 0.650 |

**`0.645` was the MRR, mislabelled as `recall@1`.** The true `r@1` is 0.412 to
0.533 depending on the run, so the top slot is wrong **half the time** — a
bigger gap than the file claimed, and the strongest remaining argument for
finding a reranker that works.


### Formats are Step 1, not Step 2, and the reason is permanence

> **The chunker is permanent. Chunk boundaries decide what is possible, and
> nothing downstream repairs them.** A corpus embedded with bad boundaries must
> be re-chunked **and** re-embedded — the whole thing, not the difference.

That is the entire argument for putting slice 3 before pgvector.

**What slice 3 must cover, in priority order:**

| Format | Priority | Library |
|---|---|---|
| **`.ipynb`** | **highest** — the user's own work is notebooks | **none** — stdlib `json` |
| **`.pdf`** | **highest** — papers are PDFs | `pypdf`, pure Python, small |
| `.docx` | medium — cheap to add | `python-docx` |
| other code languages | low | **one** generic splitter, not one per language |

Three notes that will otherwise be re-derived:

- **For a notebook, read the outputs, not only the source.** This is the lesson
  from building `quora_siamese`: the run summary numbers lived in the stored
  outputs, and the first version of `A_paper.md` was invented because only the
  code was read. The *"what do the numbers say?"* question needs those outputs.
- **PDF extraction is lossy, and it must be measured rather than assumed.**
  Two-column layouts interleave, equations become noise, tables collapse, and
  section headers often do not survive — which degrades header splitting. A
  **scanned** PDF has no text at all and must be **refused**: OCR models break
  the [memory budget](../../product/memory-budget.md#memory-budget--render-free-tier-512mb).
- **Refuse what cannot be handled well.** Every new format either gets a real
  loader or a clear 422. Never a silent fallback.


### Do not use LangChain's document loaders — corrected 2026-08-20

The [Architecture](../../architecture/stack.md#architecture--stack) bullet used to allow *"document loaders,
text splitters, model interfaces"*. It was written before the
[512MB budget](../../product/memory-budget.md#memory-budget--render-free-tier-512mb) was measured, and the two
rules now disagree. **The memory rule wins for loaders.**

```
langgraph            -> langgraph-checkpoint, langgraph-sdk,
                        langgraph-prebuilt, pydantic  (+ langchain-core)
langchain-core       -> small, and contains NO loaders
langchain-community  -> SQLAlchemy, aiohttp, numpy, dataclasses-json, langchain
                        ^ PyPDFLoader lives here, and only here
```

Three reasons, weakest first:

1. **Output shape.** They return LangChain `Document` objects, which we would
   convert to `Piece` / `Chunk` on every call.
2. **Volume.** `langchain-community` costs ~120–200MB resident, against a ceiling
   the API plus ingest already fills to ~290–370MB.
3. **The one that settles it — LangChain does not contain the parser.**
   `PyPDFLoader` requires `pypdf` to be installed anyway. So the choice is
   `pypdf` against `pypdf` **plus** `langchain-community` plus its whole tree.

**The argument that would overturn this:** if anything else ever needs
`langchain-community`, the volume reason dies and only the weak shape reason
remains. Today nothing else needs it — **LangGraph does not.**

**Unverified, and it must be checked before Step 2:** the tree above is from
memory, not from an install. Run `pip install langgraph` into a throwaway venv
and read the real dependency list. *An estimate is not a measurement* — this
file's own rule.


### Cost per slice — this is what sets the pace

| # | Generation quota spent | Note |
|---|---|---|
| 1 | **none** | embedding is a separate quota from chat |
| 2 | **none** | pure file work |
| 3 | **none** | pure file work |
| 4 | **none** | database only |
| 5 | almost none | a query embed is ~20 tokens |
| 6 | **careful** | Cohere is 1,000 per **month**, shared with embed. Use the local ONNX reranker in tests |
| 7 | a few | one end-to-end run |
| 8 | **the expensive one** | full reports, and Flash models give **20 per day** |

Slices 1 to 5 cost almost nothing. That is unusual, and it is the right place to
move quickly.

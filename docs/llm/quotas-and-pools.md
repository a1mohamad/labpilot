# Free quotas and pools

[Docs home](../README.md)

### The real free-tier numbers — measured 2026-08-16, and they overturned a lot

**This file said Google gives "~1,500 RPD". That was wrong, and several decisions
rested on it.** The truth, read from the account's own
`aistudio.google.com/rate-limit` page and confirmed by live 429s:

| Model | RPM | TPM | **RPD** |
|---|---|---|---|
| Gemini 3.7 / 3.6 / 3.5 / 3 Flash | 5 | 250K | **20 each** |
| Gemini 3.5 / 3.1 Flash-Lite | 15 | 250K | **500 each** |
| **Gemma 4 31B / 26B** | 30 | **16K** | **14,400 each** |
| **Gemini Embedding 1 / 2** | **100** | **30K** | **1,000 each** |

**The embedding row was read from the same page on 2026-08-28**, and it closes
the gap slice 1b left open. Two things follow, and the second is the one that
binds:

- **There are two embedding models, each with its own 1,000/day.** Confirmed by
  `GET /v1beta/models`: `gemini-embedding-001` **and** `gemini-embedding-2`
  (plus a `-preview`). Quota is per model, so that is **2,000 embed requests a
  day** — on a pool completely separate from the Flash generators.
  **`gemini-embedding-2` has never been called and never been scored.**
- **Requests are not the limit; 30K tokens/minute is.** Against codestral's
  50K TPM, Google is the *tighter* of the two on ingest:

$$
T_{\text{ingest}} = \frac{2000 \times 192}{30{,}000} \approx 13 \ \text{minutes}
\qquad \text{against codestral's} \approx 8
$$

  So "Google is better" is true of **recall** and false of **ingest speed**.
  That is exactly the trade the corpus-size routing rule exists to settle, and
  it now has a third candidate instead of two.

Three things follow, and all three changed the design:

1. **Google's quota is per *model*, not per key.** The error body says so:
   `GenerateRequestsPerDayPerProjectPerModel-FreeTier, limit: 20`. So one spent
   model must not retire the others — that is what
   [`quota_pool`](#a-pool-is-the-bucket-that-runs-out-not-the-api-key) fixes, and
   it recovered about **40 requests a day**.
2. **"Spend Google first because it is huge" was false.** Three Flash models give
   60/day against OpenRouter's 50 — the same size. The ordering survived, but the
   reason for it did not.
3. **The newer the model, the smaller the allowance.** 3.7 Flash launched
   2026-08-13 with 20/day and answers 503 constantly. **Do not assume a new model
   inherits the previous one's limits.**

Every provider's shape, now measured rather than assumed:

| Pool | Requests | Tokens | Shape |
|---|---|---|---|
| **Google** | 20/day (Flash) · 500/day (Lite) · 14,400/day (Gemma) | 250K/min (16K Gemma) | **per model** |
| **OpenRouter** | 50/day, 20/min | — | **per account** |
| **Mistral** | 50/min | 25K–1M per model | per model + monthly org cap |
| **Groq** | **1,000/day** | **8,000/min total** | per account |
| **Cloudflare** | 10,000 neurons/day ≈ 11 reports | — | per account |
| **Cohere** | 1,000/**month**, shared across chat+embed+rerank | — | per account |

Two kinds of limit exist, and they behave differently:

| Type | Behaviour | Platforms |
|---|---|---|
| **Quota** | Runs out. Dead until reset | OpenRouter, Google, Groq, Cohere, Cloudflare |
| **Rate limit** | Never runs out — only throttles | Mistral (per-model TPM/RPS) |

### A pool is the bucket that runs out, not the API key

*(Built 2026-08-16, after a per-model 429 cost ~40 requests a day.)*

`api_key_env` answers *"how do I authenticate?"*. It is the wrong answer to
*"what just ran out?"* — and the chain was using it for both.

```
Google      each MODEL has its own daily quota   →  independent buckets
OpenRouter  ONE 50/day for the whole account     →  shared bucket
```

So `HTTPProvider` gained **`quota_pool`**, defaulting to `api_key_env` so nothing
changes for providers that do not set one. Google entries set
`quota_pool=f"GOOGLE:{model}"`; OpenRouter entries leave it alone and keep
sharing. The chain reads `provider.pool`.

Two tests pin the two halves, because they are opposite requirements and a single
test could not express both:

```
test_each_google_model_owns_its_quota_pool     →  all pools differ
test_openrouter_tiers_share_one_quota_pool     →  all pools identical
```

**The general lesson:** *authentication and accounting are different questions.*
Any field that answers both is wrong for at least one of them — and the failure
is silent, because a shared key looks exactly like a shared quota until the day
it isn't.

### Two kinds of limit, and they are not the same thing

*(Measured 2026-08-16/17. Both fields exist because two providers genuinely
differ — this is not over-engineering.)*

| Provider | What the limit counts | Modelled as |
|---|---|---|
| **Gemma 4 31B** | **input only** — `GenerateContentInputTokensPerModelPerMinute` | `max_input_tokens = 16_000` |
| **GPT-OSS (Groq)** | **input + reserved output** | `context_window = max_output_tokens = 8_000` |

The evidence that they differ, from one smoke run:

```
Groq   413  "Limit 8000, Requested 8273"    ← prompt 77 + max_tokens 8192
Gemma  200                                   ← same max_tokens 8192, passed
```

Groq counts the `max_tokens` you *reserve*, even if you never use it. Gemma does
not. So a single field could not describe both.

**Why this matters more than it looks.** `_check_fits` now refuses these tiers
**before the HTTP call** — no request spent, no 413, no 429, no retry, no
backoff. That is what made it safe to rank them by capability instead of hiding
them at the end of the chain. And when retrieval shrinks the prompt below their
limits, **they start working with no code change**, because the check reads the
prompt rather than a flag someone has to remember to flip.

> **A limit you model correctly becomes a schedule, not an exclusion.**

**Step 1 unlock, worth more than any reordering:** when the reranker brings the
prompt under ~16K input, **Gemma 4 31B + 26B add 28,800 requests/day** — more
than every other pool in this project combined, at AA 29.7 / LMArena #27.

**Mistral also has a monthly consumption cap**, so it is not truly unlimited —
their docs state API access "can be suspended until the next month begins" if the
organization cap is reached. It resets monthly rather than daily, which is far
better, but it is still a ceiling. *The exact number is on the account's own
Limits page, not in public docs — record it here once read.*

Assignments, so no pool funds two jobs:

| Pool | Assigned to | Reason |
|---|---|---|
| **OpenRouter** (50/day) | **Generation only** | Scarcest pool. Never spend it on embedding or reranking |
| **Google** | Generation **+ embedding backup** | Chat and embedding are **separate quotas**, so no conflict |
| **Mistral** | Generation **+ embedder primary** | Rate-limited, largest headroom |
| **Groq** | Generation, **small jobs only** | 1,000/day but 8K total per call — perfect for the gate, impossible for a report |
| **Cohere** | **Rerank only** | 1,000/month is one shared bucket across chat, embed and rerank — too small to split |
| **Voyage** | **Rerank only** | 200M tokens is a one-time grant, so bank it — spend renewing quota first |
| **Cloudflare** | Rerank t2 · embedder t4 · generation t7 | Neurons are shared, so keep every user light |

### Why the adjacency rule was retired — 2026-08-16

**The old rule:** *same-pool tiers must not sit adjacent*, pinned by
`test_no_two_adjacent_tiers_share_an_api_key`. Its purpose was to stop the chain
wasting a second attempt on a pool that had just run out.

**It was written before pool-aware skipping existed, and this file said so:**

> *"Pool-aware 429 skipping would fix this properly, but it does not exist yet —
> it is planned for `chain.py`. When it lands, the swap costs nothing."*

**It landed in slice 2.** `dead_pools` means one 429 retires every tier on that
key at once:

```
tier 1  429, resets tomorrow  →  GOOGLE_API_KEY marked dead
tier 2  skipped instantly, 0 requests
tier 3  skipped instantly, 0 requests
tier 4  the next real attempt
```

Adjacency now costs **nothing**, so the rule was forbidding a chain shape that is
free — and forbidding the very shape the quota argument asks for.

**Three invariants replace it, and they check the property that actually
matters** — not *arrangement*, but *survival*:

| Test | Asserts |
|---|---|
| `test_no_single_pool_can_kill_the_whole_chain` | killing any one pool leaves at least one tier |
| `test_no_single_pool_can_stop_a_full_report` | …and at least one that can serve `REPORT_MAX_TOKENS` |
| `test_the_chain_spans_at_least_three_pools` | the chain is not secretly one provider |

The second is the strongest of the three: it is the only one that would notice
the chain quietly filling with 16K-output models.

**The general lesson is about invariants, not about pools.** The old test encoded
a *workaround* for a missing feature. When the feature arrived, the test kept
enforcing the workaround — and it was still green, so nothing drew attention to
it. **A test that pins a workaround must name the workaround, or it outlives the
problem and starts causing one.**

**One risk is genuinely higher now** and is accepted with open eyes: if the Google
*account* is restricted — as happened on 2026-08-11 — **six** tiers die at once,
not two. That scenario is already close to fatal, and the volume Google supplies
every other day is worth more than the marginal protection.

### Pin the deliberate exceptions, so an accidental one still breaks CI

*(2026-08-17.)* Three tiers cannot serve a full report today, each for a
different, measured reason. A test asserting *"every tier can"* would simply be
false; a test asserting nothing would let a real regression through. So the
exceptions are **named constants** and the test compares against the list:

```python
OUTPUT_TOO_SMALL = ("GPT-OSS 120B (Groq)", "Devstral 2")
INPUT_LIMITED = ("Gemma 4 31B",)
```

| Test | Asserts |
|---|---|
| `test_only_known_tiers_cannot_serve_a_full_report` | the output-capped list is **exactly** these two |
| `test_only_known_tiers_are_blocked_by_an_input_limit` | the input-capped list is **exactly** this one |
| `test_an_input_limited_tier_costs_no_request` | `_check_fits` rejects an oversized prompt **before** any HTTP call |

The third is the one that matters most: it proves the blocked tiers are **free**,
which is the entire reason they can be ranked by capability instead of hidden at
the end of the chain.

**The pattern generalises.** When a rule has real exceptions, do not weaken the
rule and do not delete the test. **List the exceptions by name.** Then a
deliberate loss is documented, and an accidental one — a new tier quietly
dropping below the report budget — breaks the build.

An earlier version of this test, `test_input_limited_tiers_sit_at_the_end_of_the_chain`,
was **deleted the same day it was written**: it enforced a workaround for a cost
that `max_input_tokens` had already removed. The same mistake as the adjacency
rule, caught faster this time.

**Transport**: plain `requests` for every tier in Step 0 — one uniform style,
and it keeps the underlying HTTP call visible for learning. OpenRouter, Mistral,
Cloudflare and Cohere's chat endpoint all speak the **OpenAI-compatible**
`/chat/completions` shape, so they differ only in base URL, API key, and model
name. Google is the one odd shape, and Cohere's rerank/embed endpoints are their
own. Migrating Gemini to the `google-genai` SDK later is optional, and would be a
change *inside* `LLMClient` only.

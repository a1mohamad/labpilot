# Failure rules, token limits and thinking models

[Docs home](../README.md)

### How the chain decides — the SIX-way rule

*Was three ways, then five on 2026-08-16. **A sixth was added 2026-09-19: a 500
is RETRIED.** Each one arrived after a real failure the previous rule handled
wrongly, and this one was costing the largest quota in the project — 57,600
Gemma calls a day — over a fault that clears by itself in three seconds.*

| The failure | Response | Why |
|---|---|---|
| 429, resets in **seconds** | wait, **retry the same tier** | the tier is healthy, just busy |
| 429, resets **tomorrow** | **skip every tier on that pool** | the *account* is spent, not the model |
| **429, `limit` header is `0`** | **fail this tier alone, pool untouched** | not busy — **not entitled**. It will never reset |
| **503** | wait, **retry the same tier** | the server said *"try again later"*, and it works |
| **500** | wait 3s, **retry the same tier**, then 10s | **CORRECTED 2026-09-19** — the server is failing, not refusing, and it recovers. Measured: gemma-4-31b answers 500 on **two calls of three** and 200 on the third |
| 400 / empty / timeout | **next tier** | retrying cannot change it |

**Why the `limit: 0` case had to exist.** GLM-5.2 (then tier 2) began answering
`429` with `x-ratelimit-limit-tokens-minute: 0`. Read the *limit*, not the
remaining: a ceiling of zero means the model is not on this account's plan. The
old rule treated it as a spent pool and **marked all of Mistral dead**, so
Devstral — which was working perfectly — was skipped on every single call.

$$
\text{not entitled} \iff \text{status} = 429 \;\wedge\; \min_i(\text{limit}_i) = 0
$$

`_http.rate_limit_ceiling` takes the **minimum** of every `x-ratelimit-limit-*`
header, because Mistral sends two (requests and tokens) and either one at zero
blocks the call. `_http` extracts the number; `chain` decides what it means —
the same split as `retry_after` and `reset_at`.

**Why the 503 case had to exist.** The old rule lumped 503 with 500 and moved on,
on the reasoning *"retrying cannot change it"*. Measured, that is simply false:

```
gemini-3.7-flash   try 1 → 503 UNAVAILABLE   try 2 → 200 STOP
```

Google's 503 says *"experiencing high demand … usually temporary"* and clears in
seconds. It was seen **three times in one afternoon**, on two different models.
Every one of those threw tier 1 away for nothing, and is the likeliest reason so
many saved reports were served by tier 3.

**A 503 never kills a pool.** Only 429 does. `RETRYABLE_STATUSES` in `defaults.py`
holds both codes; `dead_pools` is still reached only from 429.

**The general lesson, and it generalises past HTTP:** *"the server refused"* is
not one fact. Refusals differ by **whether trying again can help** and **whether
the refusal is about the model or the account**. Those two questions produce four
cases, and a chain that collapses them loses working tiers.

The discriminator is distance to reset, because a per-minute bucket cannot take
longer than 60 s to refill by definition:

$$
\text{pool is dead} \iff (t_{\text{reset}} - t_{\text{now}}) > \tau,
\qquad \tau = 60\ \text{s}
$$

If no header says which, the chain retries once and treats a second 429 as a
dead pool. Backoff honours `Retry-After` when present, otherwise
$d_k = d_0 \cdot 2^{k}$ capped by `max_delay`.

**`max_retries_per_tier = 1`, and that number came from arithmetic.** Worst case
is $N \times ((R+1)\,T_{\text{timeout}} + \sum d_k)$; at `R=1`, fifteen tiers
and the current 600 s read timeout that is $15 \times 1201 \approx 5$ hours.
Nobody waits five hours, so **`DEFAULT_TOTAL_BUDGET = 900 s`** enforces a real
ceiling and every remaining tier is recorded as `skipped: time budget spent`
rather than silently dropped.

*The numbers moved on 2026-08-17 and this paragraph moved with them: the read
timeout went 180 s to 600 s and the budget 300 s to 900 s, together, because
`DEFAULT_TOTAL_BUDGET` must never sit below `DEFAULT_TIMEOUT[1]` — see
[the read timeout note](constraints.md#constraints). The 42-minute figure was the old
seven-tier arithmetic; the shape of the calculation is unchanged.*

**Two kinds of math live in this file, and they are not the same.** The backoff
formula and the pool-dead test each became one line of code. The 42-minute bound
and $N_{\text{effective}}$ never run at all — they were computed once, on paper,
and their only output is two constants. Expect that split everywhere.

### Token limits — measured 2026-08-12

Every number below was read from the provider's **own** API or docs, never from a
blog or a rounded UI label. `GET /v1/models` and `GET /api/v1/models` cost no
generation quota, so this cost nothing.

*Renumbered 2026-08-17 for the fifteen-tier chain. `max_input` is the new third
column — see [Two kinds of limit](quotas-and-pools.md#two-kinds-of-limit-and-they-are-not-the-same-thing).*

| # | Model | `context_window` | `max_output` | `max_input` | Source |
|---|---|---|---|---|---|
| 1 | Gemini 3.7 Flash | 1,048,576 | 65,536 | — | Google `GET /v1beta/models` |
| 2 | Gemini 3.6 Flash | 1,048,576 | 65,536 | — | Google `GET /v1beta/models` |
| 3 | Gemini 3.5 Flash | 1,048,576 | 65,536 | — | Google `GET /v1beta/models` |
| 4 | GLM-5.2 | 1,048,576 | 1,048,576 † | — | Mistral `GET /v1/models` |
| 5 | Nemotron 3 Ultra | 1,000,000 | 65,536 | — | OpenRouter `GET /api/v1/models` |
| 6 | Gemini 3.5 Flash-Lite | 1,048,576 | 65,536 | — | Google `GET /v1beta/models` |
| 7 | Mistral Medium | 262,144 | 262,144 † | — | Mistral `GET /v1/models` |
| 8 | **Gemma 4 31B** | 262,144 | 32,768 | **16,000** | live 429, quota id |
| 9 | North Mini Code | 256,000 | 64,000 | — | OpenRouter `GET /api/v1/models` |
| 10 | Nemotron 3 Super | 262,144 | 262,144 † | — | OpenRouter `GET /api/v1/models` |
| 11 | GPT-OSS 120B (CF) | 128,000 | 128,000 † | — | Cloudflare dashboard |
| 12 | **GPT-OSS 120B (Groq)** | **8,000** | **8,000** | — | live 413 |
| 13 | Magistral Small | 262,144 | 262,144 † | — | Mistral `GET /v1/models` |
| 14 | Devstral 2 | 262,144 | **16,384** | — | Mistral API + docs |
| 15 | Gemini 3.1 Flash-Lite | 1,048,576 | 65,536 | — | Google `GET /v1beta/models` |

**Groq is modelled as an 8,000 context window on purpose.** Its real context is
131,072, but the binding limit is a **total** per-minute budget of 8,000 covering
prompt *and* reserved output. Setting `context_window` to the smaller number
makes `_check_fits` enforce exactly the right inequality. **Model the limit that
binds, not the one the vendor advertises.**

† shared window — the provider publishes no separate output cap, so the sum check
does the real work.

**Three traps this exercise exposed, all worth remembering:**

1. **The same model on two hosts has different limits.** OpenRouter's page for
   `gpt-oss-120b` reports 131K output — but that is *CoreWeave's* deployment.
   LabPilot calls Cloudflare's, which is 128K total. Always read the page for the
   host you actually call.
2. **UI labels round; the API does not.** OpenRouter renders 65,536 as "66K" and
   64,000 as "64K" — so a label cannot be reversed into an integer. Take exact
   values from `GET /api/v1/models`.
3. **Devstral's 16,384 output cap is the one that will bite.** Every other tier
   allows 64K+. A 20,000-token request passes tiers 1–4 and fails tier 5 — now
   caught locally instead of costing a request.

Google is the only provider where input and output are **separate** limits
($t_{\text{in}} \le C_{\text{in}}$ *and* $T_{\text{out}} \le C_{\text{out}}$),
which is why the validator checks both rather than only the sum.

**Devstral's 16,384 may be stale — do not trust it without a re-test.**
*(Raised 2026-08-16.)* Asked directly, Mistral **accepts** `max_tokens: 32000` on
`devstral-2512` with a 200. That does not prove it can *generate* 32,000 tokens,
only that the parameter is not rejected, so the number here was left alone. But
if it is wrong, `_check_fits` is excluding a working tier from every report for
no reason. Settle it with one long-output request, not with another guess.

### The reasoning content shape — found 2026-08-16

**A reasoning model on the OpenAI wire format does not return a string.** It
returns a **list of blocks**, and our `_extract_message` called `.strip()` on it:

```json
"content": [
  {"type": "thinking", "thinking": [{"type": "text", "text": "The user asked…"}]},
  {"type": "text",     "text": "Hello!"}
]
```

```
AttributeError: 'list' object has no attribute 'strip'
```

`_visible_text` now keeps only blocks whose `type` is `"text"` and drops the
thinking. Both branches are pinned by tests, including *"a model that only
thinks counts as an empty answer"* — which must stay an `LLMError`, because a
budget spent entirely on thoughts is a failure, not an answer.

**This had been true of GLM-5.2 all along.** That tier was broken twice over: the
429 hid a shape crash waiting behind it. **A tier that fails early can hide a
second bug — when one is fixed, re-test rather than assuming the tier is now
good.**

**`reasoning_effort` also needs `top_p: 1`.** With `temperature: 0` and nothing
else, Mistral answers:

```
400  "top_p must be 1 when using greedy sampling"
```

So `MISTRAL_REASONING` is `{"reasoning_effort": "high", "top_p": 1}`. The earlier
note in this file predicted a **422** for models that reject the field; the real
code is **400** with `code: 3051`, and it is a *different* failure from this one.
Both were guesses until a request was actually sent.

**Thinking length is not repeatable, even at `temperature: 0`.** Nine runs of
`mistral-medium-latest` on one trivial prompt:

```
completion tokens: 53 · 531 · 531 · 531 · 865 · 1533 · 1901 · 1901 · 53
```

A **36× spread**, while `magistral-small-latest` sat at 39–40 every time. The
answers were identical; the *cost* was not. Two consequences: a small
`max_tokens` makes a reasoning tier **flaky rather than broken** (it passed at
2048, then failed on the same setting an hour later — the smoke floor is now
8,192), and any future cost estimate per call must be a range, not a number.

### Thinking models — the count is at least four of seven

*(Corrected 2026-08-12. An earlier note implied `gemini-3.6-flash` was safe
because it passed a 64-token test. It passed by luck on a trivial prompt.)*

Google AI Studio exposes a **Thinking level** selector for `gemini-3.6-flash`
— Minimal / Low / Medium / High, defaulting to Medium. And OpenRouter's own page
calls Nemotron 3 Ultra an *"open frontier-**reasoning** … model"*. So:

| Tier | Model | Thinking? |
|---|---|---|
| 1 | Gemini 3.6 Flash | **yes** — level selector, defaults to Medium |
| 3 | Gemini 3.5 Flash | **yes** — proven live, spent 60 of 64 output tokens |
| 4 | Nemotron 3 Ultra | **yes** — NVIDIA's own description |
| 7 | `gpt-oss-120b` | **yes** — proven live, `content: null` at 20 tokens |
| 2, 5, 6 | GLM-5.2, Devstral 2, North Mini Code | **unverified — assume yes** |

$$
T_{\text{out}} = T_{\text{think}} + T_{\text{answer}}
$$

`max_tokens` budgets both. Too small a budget returns an empty answer that the
chain then wastes a tier on.

**Measure the rest for free on the next smoke run.** Those 7 requests already
happen weekly — print each raw body once and read `usageMetadata.thoughtsTokenCount`
(Gemini) or `choices[0].message.reasoning` (OpenAI shape). The universal signal
needs no field name at all: **completion tokens far larger than the visible
answer**. That is what caught `gpt-oss-120b`.

**Thinking level is a per-task knob, not a global setting** — `explain_divergence`
wants High, the correspondence gate wants Minimal. That argues for a `thinking`
field on `GeminiProvider`, added in **slice 4** when real `max_tokens` values are
chosen. Not before: nothing reads it yet. Get the exact REST field name from
`<> Get code` in AI Studio rather than from memory.

**Housekeeping that still applies (from the end of Step 0 slice 1).** The repository is
`https://github.com/a1mohamad/labpilot`; Python 3.13 venv; dependencies pinned; keys live in `.env`
(git-ignored) with `.env.example` as the committed template; every platform account for Steps 0-4 exists
(see [Platform Accounts](platform-accounts.md#platform-accounts--verified-august-2026)). **Layout is flat, not `src/`**: both give
the identical import path (`from labpilot.llm import LLMClient`), so moving to `src/` later is one `git mv`
that changes no imports — not a decision worth making now. **GitHub secrets are repository-wide, so they
apply on every branch, but scheduled workflows run from `main` only.** `smoke.yaml` must map each secret
with the variable name and the secret name matching on both sides of the colon (the 2026-08-11
`OPENROUTE_API_KEY` typo broke every scheduled run). `feat/llm-client` was squash-merged into `main` on
2026-08-11 and kept, not deleted (the user's choice).

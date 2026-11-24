# Token budget

[Docs home](../README.md)

### Token budget — decided 2026-08-10

**Decision: static input budget, dynamic output budget, per-tier validation.**
Recorded now; **built with `chain.py`**, not before. Full design discussion
happens when that section is reached.

Every provider enforces one inequality — output tokens are reserved *before*
generation starts, so they eat the same window as the prompt:

$$
t_{\text{in}} + T_{\text{out}} \le C
\qquad\Longrightarrow\qquad
B_{\text{in}} = C - T_{\text{out}} - M
$$

`t_in` prompt tokens · `T_out` our `max_tokens` · `C` the model's context window ·
`B_in` the input budget we may fill · `M` a safety margin.

`M` is not optional, because token counts are **estimates**. Each provider has
its own tokenizer and we do not have it:

$$
\hat{t} \approx \frac{\text{chars}}{k},
\qquad k \approx 4 \ \text{(English prose)},
\qquad k \approx 3 \ \text{(code)}
$$

Use `k = 3` for LabPilot — prompts are code-heavy, and code is denser than prose.
Underestimating shows up as a wasted request and a vague `400`, so be pessimistic.

**Why the input budget is static.** The context windows in the chain are
1M (tier 1) · ~128K (tiers 2–3) · 262K (tier 4) · 131K (tier 5). The floor is
Gemini at ~128K — but we should not want more than ~100K anyway:

- **Retrieval quality collapses long before the window does.** Facts placed in
  the middle of a very long context get lost. Sending 400 chunks does not make
  LabPilot smarter; it buries the relevant one. Being near 128K means retrieval
  is doing its job badly.
- **Prefill latency** on a free tier will time out before it answers.

So a fixed **~100,000 token input budget fits under every tier's floor**, and a
per-tier input budget would buy nothing real. It would also cost the one property
LabPilot cannot lose: if tier 1 sees 40 chunks and tier 5 sees 8, the two answers
differ for reasons unrelated to the models, and a wrong comparison can no longer
be diagnosed. **One prompt, every tier.**

**Why the output budget is dynamic.** "Do these two even correspond?" needs ~200
tokens; a full divergence report needs ~4,000. One global value gives either
truncated reports (`finish_reason: length`) or thousands of reserved tokens
wasted on a one-line answer. So `max_tokens` is a **parameter of the call**, not
a field on the provider.

**Where each number lives** — one home each, never a literal in a function:

| Number | Home | Reason |
|---|---|---|
| `context_window` per model | a field on each provider, filled in `registry.py` | provider data; changes when a free model is swapped |
| `INPUT_BUDGET` ≈ 100,000 | one shared constants module | must be identical for every tier — that is what keeps comparisons comparable |
| `SAFETY_MARGIN`, `CHARS_PER_TOKEN` (3) | same shared module | estimation policy, not provider data |
| `max_tokens` | argument to `complete()` / `generate()` | depends on the task, not the model |

**Pre-flight validation (the one genuinely per-tier piece).** Before the HTTP
call, check `estimate + max_tokens + M ≤ context_window` and raise `LLMError`
immediately if it fails. This gives *"prompt ~140K, tier 5 holds 131K"* instead
of a provider's vague `400`, and spends no request from a 50/day pool.

**Rejected: a fully dynamic per-tier prompt.** It would require `generate` to
take a *builder* (`Callable[[int], str]`) instead of a string, so the chain could
say "rebuild at 120K" on fallback. Clean in principle, but it breaks
comparability, forces retrieval to re-run inside the fallback loop, and changes
the locked `generate(prompt) -> LLMResult` signature. Revisit only if a real
prompt is ever proven to need more than 100K.

**Add `context_window` to the provider dataclass only when the validator that
reads it exists** — a field nobody reads is dead code. *(Done together, as
required, on 2026-08-12.)*

#### Two budgets, not one contradiction — clarified 2026-08-12

This file used to give two different prompt budgets — **~100,000** here and
**~20,000** under Constraints — and they read like a contradiction. They are not.
They are two mechanisms with different enforcers:

| Number | Enforced by | Protects against | Status |
|---|---|---|---|
| `context_window` per tier | `HTTPProvider._check_fits` | the provider's hard 400 | **built 2026-08-12** |
| `INPUT_BUDGET` ≈ **20,000** | **retrieval**, at slice 3 | TPM limits, latency, and facts getting buried in a long context | not built yet |

**Use 20,000, not 100,000.** Tokens-per-minute binds before context does, and a
focused 20K prompt gives a *better* answer than a padded 100K one — attention
spreads and the important lines get buried. The 100,000 figure was only ever an
observation that such a prompt would still fit under every tier's window; it was
never a target. Treat it as a ceiling that should never be approached.

The estimator and margin are now real code in `_text.estimate_tokens` and
`defaults`:

$$
\hat{t} = \left\lceil \frac{\text{chars}}{k} \right\rceil, \quad k = 3
\qquad\text{and}\qquad
\hat{t}\,(1+m) + T_{\text{out}} \le C, \quad m = 0.10
$$

**The margin multiplies only the estimate, never `max_tokens`.** `t̂` is a guess
and can be wrong; `max_tokens` is a number we choose and send literally, so the
server honours it exactly. Padding a known quantity only wastes window. That is
the general rule: **a safety margin belongs on estimated quantities, never on
known ones.**

#### The estimator was checked against real counts — it is correct

*(Measured 2026-08-16. `k = 3` stays.)* Providers return the true token count on
every call, so the estimate can be graded for free:

| Prompt | our `chars/3` | provider's real count | |
|---|---|---|---|
| `FULL`, sample pair | 19,736 | **19,151** | over by 3% ✅ |
| `CORE` stuffed, sample pair | 28,056 | **26,594** | over by 5.5% ✅ |

**It over-estimates on real LabPilot content**, which is the correct direction —
the margin is there to be unnecessary.

**A synthetic test said the opposite, and that was the test's fault.** Repetitive
one-line code (`def step(x): return x*2+1`, ×2400) measured **33,621** real
tokens against a 27,200 estimate — 19% *under*. Newline- and punctuation-dense
filler tokenizes far worse than real source. **A worst-case string is not a
measurement of your data; grade an estimator on the corpus it will actually
see.**

**A real tokenizer would not fix this.** `tiktoken` is OpenAI's BPE, while the
chain runs on Google, Mistral, NVIDIA and Cohere — it would be a *different*
wrong number plus a dependency on a 512MB box. **The upgrade is measurement, not
arithmetic:** log estimate against the returned count on every call and let `k`
be set by evidence. `prompt_tokens` is already logged; only the comparison is
missing.

#### Tokens-per-minute does not reject a single large request

*(Corrected 2026-08-16.)* A 33,621-token prompt was sent to
`mistral-medium-latest`, whose ceiling is **25,000 tokens/minute**, and it
returned **200**. TPM throttles *across* a minute; it does not reject one call
that exceeds it.

This weakens the reasoning — though not necessarily the conclusion — behind
[the Groq exclusion](constraints.md#constraints), which says a 24K prompt "can never pass" an
8K TPM limit. That may be true of Groq specifically, but it does **not** follow
from TPM alone and was never tested. **Re-check an exclusion against the claim
that produced it, not against the memory of the decision.**

### Budgeting all three chains — added 2026-08-11

The generator budget above is about **one call**. This is about **how many calls
a real session costs**, which is what actually exhausts a quota. Working
assumptions: a repo of `N ≈ 2,000` chunks at `t̄ ≈ 500` tokens ≈ **1M tokens**;
retrieval fetches 50 candidates and reranks to 10.

**The universal rule: cost is knowable before the first call, so check it and
refuse to *start* rather than dying halfway.** True for all three chains.

#### Embedder — the bursty one, but offline

Ingest time is bounded by whichever limit binds first, tokens or requests:

$$
T_{\text{ingest}} \;=\; \max\!\left(\frac{N\,\bar{t}}{\text{TPM}}\times 60,\;
\frac{\lceil N/B \rceil}{\text{RPS}}\right)\ \text{seconds}
$$

`B` = batch size (texts per request). With `N=2,000`, `t̄=500`, `B=100`:

| Model | TPM | Bound by | Ingest time |
|---|---|---|---|
| `codestral-embed` | 50,000 | tokens | **~20 min** |
| `mistral-embed` | 20,000,000 | requests (1 RPS) | **~20 s** |

20 minutes is acceptable — **ingest is offline and queued**, nobody is watching.
Query-time embedding is ~20 tokens per turn and is effectively free.

#### Reranker — one call per retrieval, three different ceilings

> **CORRECTED 2026-09-09, twice. Both the call size and `r` were wrong — see
> [the slice 6 theory](../step1/reranking.md#slice-6--the-theory-recorded-2026-09-09).**

**The call size.** This section assumed 50 chunks × 500 tokens = 25,000. Our
chunks **measure 229 tokens**, and Voyage publishes the real formula
(`query tokens × documents + sum of document tokens`):

$$
20 \times 50 \;+\; 50 \times 229 \;=\; 12{,}450 \text{ tokens per call}
$$

So every capacity below is roughly **double** what was recorded here:

$$
\text{Voyage: total calls} \le \frac{200{,}000{,}000}{12{,}450} \approx 16{,}000
\qquad
\text{Cloudflare} \approx \frac{10{,}000}{3.5} \approx 2{,}850 \text{ per DAY}
$$

**`r`, and this one is not a rounding error.** This section said a full report
does *"~5 retrievals"*, giving ~200 reports/month on Cohere. **That 5 came from
the `verify` BATCHING line** — 5 claims per *generation* call — which is a
different step on a different budget. The agent design in this same file says
claim extraction yields ~14 claims, and **each claim needs its own search, so
its own rerank**. Batching the answering step reduces no searches.

$$
r \;=\; N + 1, \qquad N = \text{claims per report, UNKNOWN until Step 2}
$$

$$
\text{Cohere: reports/month} \le \frac{1{,}000}{r}
\quad\Longrightarrow\quad
N = 30 \;\Rightarrow\; 32 \text{ reports/month}
$$

**Do not replace one guess with another.** `N` cannot be counted until the agent
exists. What the arithmetic does show is which provider makes `N` stop
mattering: Cloudflare renews ~2,850 calls **a day**, and a local model has no
call count at all. Cohere's 1,000/month is the smallest budget of the three by a
wide margin, and it is the one that repeats per query.

**The order is unchanged** — spend the expiring bucket, bank the one-time grant
— and the alternative it now has to beat is recorded in the slice 6 section.

**The 510-token trap:** Cohere auto-chunks any document longer than 510 tokens,
which silently multiplies the billed document count. Keep chunks under 510 or
the arithmetic above is wrong by a factor of 3.

**Then two more tiers with no practical ceiling** — Cloudflare's `bge-reranker`
(neurons are cheap for reranking) and `ministral-3b-2512` at 12.5 RPS. Running
out of reranking entirely is therefore very unlikely, and if it happens the
answer is "skip it", not "fail".

#### Generator — the binding constraint

One **full** report is not one call. Under the default plan with 14 extracted
claims, batching `verify` 5 claims per call:

| Step | Calls |
|---|---|
| `summarize` A and B | 2 |
| `align` | 1 |
| `verify` (14 claims ÷ 5) | 3 |
| `find_missing`, `diff_choices` | 2 |
| `explain_divergence`, `propose_next` | 2 |
| **Total** | **~10** |

$$
\text{reports per day} \;=\; \Big\lfloor \frac{\text{daily quota}}{10} \Big\rfloor
$$

*Rewritten 2026-08-17 on the measured quotas — the old table assumed Google gave
~1,500 RPD and therefore ~150 reports/day. **Both numbers were fiction.***

| Pool | Daily quota | Full reports/day, un-routed |
|---|---|---|
| Google Flash ×3 | 20 each = **60** | **~6** |
| Google Flash-Lite ×2 | 500 each = **1,000** | **~100** |
| Google Gemma ×2 | 14,400 each | ⏸ blocked until the prompt shrinks |
| OpenRouter | 50 | **~5** |
| Groq | 1,000 | ⏸ small jobs only |
| Cloudflare | ~11 calls | **~1** |

**The conclusion inverts.** The old note said *"tier 1 must be Google because it
has 1,500/day"*. The truth is that Google's **best** models give 60 calls a day
between them — about six un-routed reports — while its **cheap** models give
1,000 and its Gemma models 28,800.

**That is the whole argument for
[model routing](../agent/design.md#model-routing--a-chain-per-task-not-a-model-per-task).** Spend
the 20/day models on `explain_divergence` only, and run the other nine calls on
Flash-Lite, Gemma and Groq. Same report count, far better report.

#### Consequences to build in

- **Batch the verify loop.** 5 claims per call turns 14 calls into 3.
- **Plan with rules before spending an LLM call on classification** — never burn
  a generation call to decide how to spend generation calls.
- **Cheap steps to cheap tiers.** `summarize` and `verify` are easy; reserve
  tier 1 for `explain_divergence`, which is the actual product.
- **Emit a cost estimate before executing a plan**, and refuse plans that exceed
  the remaining budget. Same discipline as the pre-flight token validator and the
  ingest budget check.

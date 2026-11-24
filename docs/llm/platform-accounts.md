# Platform accounts

[Docs home](../README.md)

## Platform Accounts — Verified August 2026

*Table rewritten 2026-08-11 after Cerebras died and Mistral was added.*
**"Verified" now means a request returned a token — not that an account exists.**

| Platform | Role | Limits | Card? | Proven live? |
|---|---|---|---|---|
| **Cline** | **Generator t1** — `z-ai/glm-5.3-flash` | **UNKNOWN — published nowhere, and no rate-limit headers.** Free models cost **0 credits** | No | ✅ 2026-09-13 |
| **OpenRouter** | Generator t4 + t5 | 50/day, 20 RPM | No | ✅ 2026-08-10 |
| **Google AI Studio** | Generator t1/t2/t3/t6/t8/t15, **embedder t3 — now proven** | **per model**: Flash 20/day · Flash-Lite 500/day · Gemma 14,400/day | No — see restriction note | ✅ 2026-08-27 |
| **Mistral** | Generator t4/t5/t7/t9, **embedder primary** | **per-model** TPM/RPS + a monthly cap | No — **phone verification** | ✅ 2026-08-16 |
| **Cohere** | **Reranker t1**, embedder last resort | 10 req/min rerank, **1,000 calls/month total** | No | ✅ 2026-08-11 |
| **Voyage AI** | **Reranker t2** | **200M tokens, one-time, SERIES 3 ONLY** · **3 RPM / 10K TPM** on a card-free account — the "4M TPM / 2,000 RPM" here was the BILLED tier. Both read from its own Rate Limits dashboard | No | ✅ 2026-09-11 |
| **Cloudflare Workers AI** | Reranker t3, embedder t4, generator t7 | 10,000 neurons/day, resets 00:00 UTC | No | ✅ 2026-08-11 |
| **Groq** | Generator t12 · **Step 2 small jobs** | **1,000 req/day** · **8,000 tokens/min total** | No | ✅ 2026-08-17 |
| ~~**Cerebras Cloud**~~ | ~~tier 5~~ | — | **YES — blocked** | ❌ `402` |
| **Kaggle** | Fine-tuning (Step 4) | ~30 GPU-hrs/week, 2×T4 or P100, 12h sessions | No (phone verification) | — |
| **Lightning AI** | One-shot escape hatch for a bigger GPU | **5 credits, one-time** (~2 A100-hrs) | No (phone verification) | — |
| **Hugging Face** | LoRA adapter hosting + **the public demo** | ZeroGPU: max 2 Spaces, small daily GPU-seconds quota | No | — |
| **Modal** | **Fine-tuned model serving only** — no longer a chain tier | $30 credit (Starter) | No | ❌ |

**Rejected after testing, 2026-08-11:**
- **Groq** — free TPM (6K–12K) is smaller than one LabPilot prompt; no embeddings.
- **Z.ai** — made redundant: GLM-5.2 (stronger than their free GLM-4.7-Flash) is
  already reachable on the Mistral key, so the signup was never needed.
- **llm7.io** — the largest free allowance found (100 req/hr, 1M tokens/24h, email
  only, no card) but it resells frontier models with **no stated data-logging
  policy**, and LabPilot sends users' code. Acceptable as a *development
  workhorse*; never in the shipped chain.

**Mistral needs phone verification.** That is stricter than this project's
preferred "no card, no phone" rule, but the account already exists and Mistral is
now central — it holds the embedder primary and two generator tiers.

### What was verified live on 2026-08-11 (Mistral)

`GET /v1/models` → **HTTP 200**, 55 models. Then actual calls:

| Model | Result |
|---|---|
| `glm-5-2` | ✅ **HTTP 200**, returned text |
| `codestral-embed` | ✅ **HTTP 200**, **1536 dimensions** |
| `mistral-embed` | ✅ **HTTP 200**, **1024 dimensions** |
| any reranker | ❌ **none exist** — zero matches in the model list |

Also present: `zai-glm-5-2`, `codestral-embed-2505`, `devstral-2512`,
`devstral-medium-latest`, `mistral-large-2512`, `codestral-2508`.

**Still unconfirmed:** whether the account is on Free mode, and the exact monthly
token cap. Both are on the account's own `Subscription` / `Limits` pages. Record
them here once read — the cap decides how much of the chain rests on Mistral.

### What was verified live on 2026-08-11 (Cohere, Voyage, Cloudflare)

Every remaining platform was proven with a real call. **Nothing in the project is
unproven now.**

| Provider | Model | Result | Latency | Cost signal |
|---|---|---|---|---|
| Cohere | `rerank-v4.0-fast` | ✅ 200 | ~1 s | `billed_units.search_units: 1` |
| Voyage | `rerank-2.5-lite` | ✅ 200 | 3.8 s | `usage.total_tokens: 28` |
| Cloudflare | `@cf/openai/gpt-oss-120b` | ✅ 200 | ~2 s | **6.0 neurons** |
| Cloudflare | `@cf/baai/bge-base-en-v1.5` | ✅ 200 | 1.2 s | **768 dimensions** |
| Cloudflare | `@cf/baai/bge-reranker-base` | ✅ 200 | 1.1 s | **0.0124 neurons** |

Both rerankers ranked correctly — the `lr = 3e-4` document scored highest every
time, the irrelevant `import os` lowest.

**Cohere is fast; a 96-second reading was a local network fault.** A repeat gave
`HTTP 000` at 21 s (curl never completed the connection) then `HTTP 200` at
0.97 s. When timing a provider, take more than one sample — and remember `000` is
a client-side failure, not a provider response.

#### `@cf/openai/gpt-oss-120b` is a thinking model — the Gemini trap, again

With `max_tokens: 20` it returned:

```json
"finish_reason": "length",
"message": {"content": null,
            "reasoning": "User asks: \"Reply with one word: ok\". So we need to"}
```

`content: null` — the whole budget went to reasoning. With `max_tokens: 800` it
answered `"ok"`, still spending **54 completion tokens on one word**.

So tier 7 needs a `max_tokens` floor exactly like the Gemini tiers, and it hides
its thoughts in a **`reasoning`** field rather than Gemini's
`usageMetadata.thoughtsTokenCount`. Two families, two field names, same failure:
our `_extract_message` sees an empty answer and falls through for no real reason.
**Assume any modern model may be a thinking model until proven otherwise.**

#### Neuron economics — measured, not estimated

The live call confirms the published rates exactly: 73 in + 54 out = 6.0 neurons.

| Job | Real call size | Neurons | Per day (10,000) |
|---|---|---|---|
| **Generation** | 20K in + 4K out | **909** | **~11** |
| **Reranking** | 25K tokens | **~7** | **~1,400** |

**Reranking is roughly 130× cheaper per token than generation on Cloudflare.**
That measurement is the hard evidence for the quota allocation: Cloudflare is a
rerank/embed home, and its generation tier is outage insurance only.

### Google AI Studio — the account restriction of 2026-08-11

**What happened.** Every `generateContent` call returned
`403 PERMISSION_DENIED — "Your project has been denied access. Please contact
support."` The key itself was fine: `ListModels` returned `200 OK` with the same
key. A brand-new project created minutes later was marked `Restricted`
immediately, before it had ever made a request, with the tooltip *"This
Project's API access is restricted. Please set up billing to continue."*

**What it was not.** Not billing — Google's own pricing page says AI Studio is
free in all available regions. Not the region — Google's available-regions page
lists Germany, which is what the billing dialog showed. Not the model slugs —
they were verified against the live model list.

**How the two refusals differ, and why that identified the cause:**

| What fires | Error | Meaning |
|---|---|---|
| Request comes from a refused **IP** | `400 FAILED_PRECONDITION` — *"User location is not supported"* | checked **per request**, on the IP — **not on the ISP**: one ISP's addresses can differ, measured 2026-08-27 |
| Project or account is flagged | `403 PERMISSION_DENIED` — *"project has been denied access"* | applied **before** any request is judged |

A per-request check cannot restrict a project that has made no requests. So the
flag was on the **Google account**, and every project it created inherited it.

**The fix: a different Google account.** Tiers 2 and 3 then passed on the first
try. `GOOGLE_API_KEY` in `.env` now belongs to that second account.

**Rule going forward: do not use this account through a VPN or a location-
switcher extension.** The flagged account was being used with one; the working
account was not. A mismatch between account country and connection country is a
standard anti-fraud trigger. Losing this account too would cost two tiers.

**That rule cannot be obeyed literally here, so it is replaced by a check.**
*(2026-08-27.)* The user works from behind a VPN and has no unproxied route to
Google at all, so "do not use a VPN" is not an available option — the honest
version is **"use an exit Google accepts, and prove it before every LLM
session."** That is
[the network precondition](../rules/sources-and-network.md#network-precondition--check-the-exit-isp-before-any-llm-work).
Keep the account-country warning as the reason a `403` would appear; the `400`
is the exit, and it is the one that actually happens here.

**And the general lesson, which cost an afternoon:** an issued API key is not a
working API. Google was recorded as "created and verified" on 2026-08-08 and had
never once returned a token.

**Confirmed again on 2026-08-11, and this time it cost a whole tier.** Cerebras
was recorded as "verified, no card" on 2026-08-08 on the strength of a signup
alone. Its first ever request returned `402 Payment Required`. The plan had made
it the chain's only independent quota.

**Rule: a platform is "verified" only when a request has returned a token.** The
Platform Accounts table now carries a *"Proven live?"* column for exactly this
reason. Cloudflare and Cohere are currently in the unproven state — do not build
on either until one call has succeeded.

### Lightning AI — read the credit maths before using it

*Re-verified 2026-08-09 against lightning.ai/pricing. An earlier version of this
file said "15 credits per month" and "~3 hrs on A100" — **both were wrong.**
Corrected below. If your account balance disagrees with this, trust the account
and update this section again.*

The advertised **"up to 80 free GPU hours"** is not 80 hours, and not monthly.
Their FAQ, exact wording:

> "You get 5 free Lightning credits upon registration. Add a card for 25 more.
> If you don't use them, they expire in 12 months."

So under this project's no-card rule the real allowance is **5 credits, once,
ever** (~$1 each). The 80-hour headline assumes 30 credits — i.e. a card — on
the *cheapest interruptible* machine. Every figure on that page is worded
*"to start"*: nothing here refills each month.

Official rates (per GPU/hr, billed by the second) and what 5 credits actually buy:

| GPU | VRAM | $/hr | Hours from 5 credits |
|---|---|---|---|
| T4 | 16 GB | $0.42 | ~12 hrs |
| L4 | 24 GB | $0.48 | ~10 hrs |
| L40S | 48 GB | $2.14 | ~2.3 hrs |
| A100 | 40 GB | $2.19 | **~2.3 hrs** |
| A100 | 80 GB | $2.71 | ~1.8 hrs |
| H100 | 80 GB | $4.50 | ~1.1 hrs |
| H200 | 141 GB | $6.53 | ~0.8 hrs |

Free-tier caps that also matter: **A100/H100/H200 sessions are limited to 4
hours**, max **1 GPU per Studio**, max 2 concurrent GPUs, 50GB persistent
storage. T4/L4/L40S sessions are uncapped in length.

**What it is:** a cloud development environment (browser VS Code, Jupyter, SSH
from a local IDE). The free Studio is **CPU-only** and must be restarted every
4 hours. GPU time always costs credits.

**Use it for:** the 26B OOM test (see [Fine-Tuning](../step4/fine-tuning.md#fine-tuning-plan)) — and
understand this is a **single ~2-hour shot on an A100**, not a resource to come
back to. Plan the run completely on the free CPU Studio first, then switch that
same Studio to A100 only when the code is ready to execute.

**Do not use it for:** routine training — Kaggle gives ~30 GPU-hrs *per week*,
which is vastly more. And **not for serving the demo** — see the correction
below.

**Habit to keep:** always stop the machine when finishing work. Credit platforms
charge for the time the machine is *on*, not the time spent typing. This is the
most common way free credits are lost.

### Checked and rejected — do not revisit
All of these require a card, or are the wrong category. Recorded so this
research is never repeated.

| Platform | Reason |
|---|---|
| Nebius AI Cloud | Card required; charges $25 on signup |
| Nebius Token Factory | Card required at signup form |
| Beam Cloud | Only $1 free; card required to unlock the rest |
| Cerebrium | "Add a payment method to deploy apps" |
| Saturn Cloud | Pricing page shows only pay-as-you-go and Enterprise |
| RunPod | Card + $10 deposit required |
| Oracle Cloud Always Free | Card required at signup (virtual cards rejected) |
| Koyeb | Free tier closed to new users after the Mistral acquisition |
| Northflank, Intel Tiber | Card or coupon required |
| GCP / AWS / Azure trial credits | Card required; GPU quota often refused |
| SageMaker Studio Lab | Closed to new signups on 2026-07-30 |
| Google Colab | Terms forbid serving a notebook as a web service |
| Incus | Not a hosting service — it organises a Linux machine you already own. No GPU, no server, no public URL. Would also need WSL2 on this 8GB machine. Genuinely useful only for sandboxing agents that *execute* code — a v2 concern, since v1 only reads code. |
| Octopus Deploy | A deployment orchestration tool, not a host. Provides no compute. |


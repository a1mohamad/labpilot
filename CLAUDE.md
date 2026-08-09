# CLAUDE.md — LabPilot

Project instructions for Claude Code, and orientation for any human reader.
Read the two rule sections first — they change *how* everything below is done.

**Contents:** [Working Rules](#working-rules-read-first) · [Overview](#project-overview) ·
[Status](#current-status) · [Environment](#development-environment) ·
[Conventions](#conventions) · [Architecture](#architecture--stack) ·
[LLM Serving](#llm-serving--fallback-chain) · [Platform Accounts](#platform-accounts--verified-august-2026) ·
[Build Plan](#build-plan--walking-skeleton) · [Fine-Tuning](#fine-tuning-plan) ·
[Risks](#open-risks--revisit-before-or-during-the-build) ·
[Out of Scope](#explicitly-out-of-scope-for-v1)

---

## Working Rules (Read First)

### Learning mode — this is a learning project, not a delivery project
This is the user's first project in RAG, agents, MCP, and LLM fine-tuning.
The goal is to **learn these concepts**, not only to end up with a finished app.

- **Explain before building.** Before any new piece (a RAG step, an agent node,
  an MCP integration, a fine-tuning step), first explain the concept. Simple
  *language*, never simplified or wrong *ideas*.
- **Do not write code by default.** Describe what needs to be done and let the
  user write and apply it themselves. Learning happens in the writing.
- **Exception:** write code directly only when the user explicitly asks — for
  example *"please code this for me."*
- This applies at **every stage** of the project, not only the first step.

#### Format for every new concept — follow this order
The stated goal is not only to ship LabPilot. It is to understand these ideas
well enough to design *future* projects with them. So teach the fundamentals,
not just the API calls.

1. **The concept** — what it is and what problem it solves, in plain words.
   Use an analogy if it genuinely helps.
2. **The details** — how it actually works, step by step. The real mechanism,
   not a hand-wave.
3. **The math** — whenever there is math underneath, show it. Do not skip it and
   do not water it down. Define each symbol.
4. **Where it sits in the pipeline** — how this piece connects to the ones
   before and after it, so the shape of the whole system stays visible.

#### Explanation depth — where explanations start
This project assumes a reader already fluent in the deep-learning and
deployment stack. **Explanations start above that line, not from zero.**

Assumed known — do not re-teach:
- **Modelling**: PyTorch, TensorFlow/Keras, CNNs, RNNs/LSTMs, transformers,
  self-attention and cross-attention, tokenization, WordPiece/BPE, embeddings,
  BERT, GPT-2, Hugging Face Transformers, classical ML and boosting, EDA,
  validation.
- **Engineering**: FastAPI, Docker, Nginx, PostgreSQL, SQLAlchemy/Alembic,
  MLflow, Airflow, Kafka, CI/CD, React/TypeScript.
- **Math**: at the level of Andrew Ng's ML/DL courses and MIT Deep Learning.
  Linear algebra, softmax, dot products, gradients — all fair game, shown
  directly rather than avoided.

Explained in full depth — the four gaps this project exists to close:
**RAG, vector databases, agent orchestration (including MCP), and LLM
fine-tuning.**

**Practical rule:** connect every new idea to the assumed-known list. Vector
search is cosine similarity over embeddings — so go straight to the formula,
normalization, and why approximate nearest-neighbour search exists; do not
define "embedding". Agents are control flow over state — not "a helpful robot".

### Communication
English proficiency is between B1 and B2, not a native speaker.

- Use clear, simple English words and short sentences.
- Simplify the *language*, not the *concepts*.
- Avoid idioms, slang, and heavily casual phrasing.

### Sources — verify before trusting
When checking whether a platform or service is free, **only two sources count**:
the provider's own pricing page, and the actual signup or deploy flow.

Blog posts, "best free GPU" lists, and credit-aggregator sites are frequently
wrong or out of date. This was proven on 2026-08-08: three platforms
(Beam, Cerebrium, Saturn Cloud) were reported as "free, no card" by such sites
and all three required a card when tested. Every claim sourced from official
documentation held true.

Also watch the wording. **"No charge" is not the same as "no card needed."**
Several platforms perform a "$0 authorization" — they take no money, but a card
is still required, so the account is still blocked.

---

## Project Overview

LabPilot is an agent-based tool that compares two pieces of work — a research
paper vs. code, or code vs. code — and explains **why their results diverge**,
then proposes the next experiment to test.

It is a portfolio capstone project, deliberately scoped to close four specific
skill gaps: **RAG**, **vector databases**, **agent orchestration** (including
MCP), and **LLM fine-tuning**.

### Comparison modes
- **Paper vs. Code** — a paper's claims/methodology against an implementation
- **Code vs. Code** — two implementations against each other
- The "Code" side accepts either a single file/notebook or a full repository —
  same comparison logic either way, just more files to retrieve from.

### What every comparison must surface
1. Bugs or implementation errors
2. Differing approaches / design choices between the two sides
3. Missing details (hyperparameters, preprocessing steps, seeds, library
   versions) that the code had to assume
4. A causal explanation for *why* the results likely diverge — not just
   "these differ"
5. A concrete suggestion for the next experiment to run

### Edge cases to handle explicitly
- **Mismatched domains** (e.g. an unrelated paper + repo): detect and report
  "no meaningful correspondence found" — never hallucinate a comparison.
- **Notebook vs. large repo**: rely on the RAG retrieval layer to narrow the
  repo down to relevant files. Never dump a whole repo into context.
- **Cross-language comparisons** (e.g. Python vs. C++): route the harder
  abstract/algorithmic reasoning to the top of the fallback chain
  (Nemotron 3 Ultra), not to the fine-tuned small model. The fine-tuned model
  is a demo artifact, never part of the live reasoning path.

---

## Current Status

**Phase: Step 0 — walking skeleton. Not started yet.**

Setup is complete:
- Git repository connected to `https://github.com/a1mohamad/labpilot` (branch `main`)
- Virtual environment on Python 3.13
- Four dependencies installed and pinned
- API keys stored in `.env` (git-ignored), template committed as `.env.example`
- All platform accounts for Steps 0–4 created and verified
  (see [Platform Accounts](#platform-accounts--verified-august-2026))

Next piece to build: the `LLMClient` — see [LLM Serving](#llm-serving--fallback-chain).

---

## Development Environment

Windows 11. **Git Bash** is the preferred shell (PowerShell also works, but the
commands below assume Git Bash).

### Hardware limits — important
This machine has **4–6GB VRAM and 8GB or less system RAM**.

Consequences, decided 2026-08-08:
- **Running any model locally is ruled out.** A 4B model in 4-bit needs ~3GB for
  weights alone, and the KV cache grows with prompt length. LabPilot sends long
  prompts (retrieved code chunks + paper text), which is the worst case. Windows
  itself uses 3–4GB of the system RAM before anything else starts.
- **Docker Desktop (Step 3) will feel heavy.** It runs through WSL2, which takes
  a large share of 8GB. It will work, but expect slow image builds. Close other
  programs while building.
- All model inference — base models and the fine-tuned model — happens on hosted
  platforms. Nothing runs on this machine.

### Activate the virtual environment
```bash
source .venv/Scripts/activate
```

### Recreating the venv — important gotcha
Two Python versions are installed on this machine, and **plain `python`
resolves to 3.10**, not 3.13, because Python310 comes first on PATH. Always
name the version explicitly:

```bash
py -3.13 -m venv .venv
```

Verify with `python --version` **after** activating — it must say 3.13.
(`py --version` reports the launcher's default and is not a reliable check.)

### Install dependencies
```bash
pip install -r requirements.txt
```

### Environment variables
Copy `.env.example` to `.env` and fill in real values.

| Variable | Used for | Where to get it |
|---|---|---|
| `OPENROUTER_API_KEY` | Chain tiers 1 + 4, and the reranker | openrouter.ai/keys |
| `GOOGLE_API_KEY` | Chain tiers 2 + 3 (Gemini) | aistudio.google.com/api-keys |
| `CEREBRAS_API_KEY` | Chain tier 5, and the development workhorse | cloud.cerebras.ai |
| `MODAL_API_KEY` | Chain tier 6 (paid — last resort). Not yet obtained. | modal.com |

`GOOGLE_API_KEY` is deliberately named to match what the official
`google-genai` SDK reads automatically, in case we migrate off `requests` later.

**Required OpenRouter setting:** enable *"Allow free endpoints that train on
request data"*, or every `:free` model returns an error.

---

## Conventions

### Commits
**Conventional Commits** — `<type>: <short imperative description>`, lowercase,
no full stop at the end.

```
feat: add LLM fallback chain
fix: handle empty retrieval result
docs: add CLAUDE.md
chore: add project dependencies
```

Types in use: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`.

### Branching
Solo project — commit directly to `main`. No pull-request workflow for now.
Revisit if the project gains collaborators, or if a PR is needed to run a
multi-agent code review.

### Dependencies
`requirements.txt` holds **direct dependencies only**, with pinned versions —
not the full `pip freeze` output. Rationale: readability. Once LangChain and
LangGraph arrive, a full freeze would be 100+ unreadable lines.

Planned progression (climb only when the project earns it):

| Stage | Setup | Trigger |
|---|---|---|
| Now | one `requirements.txt` | 4 packages, no tests |
| Steps 1–2 | `+ requirements-dev.txt` | when `pytest` is added |
| Step 3 | `pyproject.toml` + lock file | Docker needs reproducible builds |

Note: `requirements.txt` is generated on Windows and may contain Windows-only
packages (e.g. `colorama`). Watch for this when the Docker image is built.

### Secrets
Never commit `.env`. Never put keys in code or in this file. Verify with
`git status` before every commit.

---

## Architecture & Stack

- **Agent orchestration**: LangGraph as the core orchestrator. LangChain is used
  **selectively** — document loaders, text splitters, model interfaces only.
  Do **not** use LangChain's own agent/chain abstractions; orchestration belongs
  to LangGraph. Not CrewAI for v1.
- **Vector DB**: Supabase Postgres + pgvector
- **Experiment/observability tracking**: MLflow — both fine-tuning experiments
  and agent/RAG observability. Self-hosted or in-notebook; do **not** pay for a
  managed MLflow service.
- **Batch/offline jobs**: Airflow (offline only — never on the live request path)
- **Deployment**: Docker + Render or Fly.io
- **Session behavior**: chat continues within a case/session with persisted
  context — not reset each message

### Layer separation
Keep these three layers distinct; do not mix their responsibilities:

```
LangGraph      →  decides which steps run, and in what order   (Step 2)
    ↓
LLMClient      →  one prompt in, one answer + its model out    (Step 0)
    ↓
requests       →  the actual HTTP call to a provider
```

**Framework choice rationale:** LangGraph is provider-neutral. The
OpenAI Agents SDK and Claude Agent SDK lock to a single provider, and Google ADK
pulls toward Google Cloud — all incompatible with a multi-provider fallback
chain, which is the core of this design.

---

## LLM Serving — Fallback Chain

All model access goes through a single `LLMClient` interface (one method,
`generate(prompt) -> LLMResult`). **Nothing else in the codebase talks to a
provider directly.** This is deliberate: free endpoints appear and disappear
constantly, so a provider change must be a one-file edit, not a refactor.

`LLMResult` carries four fields: `text` (never empty — an empty answer is a
*failure*, not an answer), `model`, `tier`, and `attempts` (what each failed
tier returned). Decided 2026-08-09: the frontend must show which model answered
and which ones failed first, so model identity has to cross the seam — reaching
the log file is not enough.

**The test for anything new in this interface: it must be true for all six
providers.** Model identity and failure reasons pass — every provider reports
them. Streaming does not, so it stays out.

Order of attempt (fall through on failure or 429):

| # | Model | Provider | Why |
|---|---|---|---|
| 1 | **NVIDIA Nemotron 3 Ultra** (`:free`) | OpenRouter | Primary. 1M context, MoE (55B active / 550B total). Strong on programming and long agentic workflows — best fit for the hard comparison reasoning. |
| 2 | **Gemini 3.6 Flash** | Google AI Studio | High-volume workhorse (~1,500 RPD), free context caching, 128K+ context. Carries development and routine comparisons. |
| 3 | **Gemini 3.5 Flash** | Google AI Studio | Same free tier and context caching. Note it shares Google's quota with #2. |
| 4 | **Ling 3.0 Flash** (`:free`, by inclusionai) | OpenRouter | Second free OpenRouter option. Shares OpenRouter's ~50/day pool with #1 — see the note below. |
| 5 | **`gpt-oss-120b`** (Production) | Cerebras Cloud | 2,400 req/day — by far the largest free daily allowance. The binding limit is **5 RPM**, not the daily total. |
| 6 | Kimi K3 · Nemotron Ultra · DeepSeek V4 Pro · DeepSeek V4 Flash | Modal | **Opt-in only — never automatic.** Costs credit. Reached only when tiers 1–5 have all failed, *and* the user says yes. |

**Tier 6 is gated by the user — this is a hard rule.** Tiers 1→5 fall through
automatically. Tier 6 does not. When tier 5 fails, the chain **stops**, tells
the user that every free provider is exhausted and that continuing spends Modal
credit, and waits for a clear yes. No yes, no call.

Design consequence: `generate` cannot always return an `LLMResult`. It must be
able to report *"all free tiers exhausted"* instead — as a distinct exception,
`AllFreeTiersExhausted`, separate from the per-tier `LLMError` that the fallback
loop swallows. **The permission prompt belongs above `LLMClient`, not inside
it** — `LLMClient` reports the state, the caller asks the user and may then
re-call it with tier 6 enabled. Keep this boundary clean; `LLMClient` never
talks to the user.

**Live progress events — Step 3, not Step 0.** For the UI trace ("Asking
Nemotron 3 Ultra… failed 429 → asking Gemini 3.6 Flash"), `LLMClient` takes an
optional callback and emits one small fixed event before and after each tier.
FastAPI forwards them to the browser over SSE. This does not break the rule
above: *emitting a fact is not talking to the user.* `LLMClient` reports; the
caller decides what to display, and the caller is the only place that may *ask*
anything. Keep the event shape small and provider-neutral, for the same reason
as `LLMResult`. Word the trace honestly — at that moment the code is waiting on
HTTP, so "Asking Nemotron…" is true and "Nemotron is thinking…" is not.

**Modal's real job is the fine-tuned model** (Gemma 4 open weights + our LoRA
adapter). Tier 6 is a borrowed side-use of the same $30, not what the credit is
for. If the two ever compete, the fine-tuned demo wins.

**Two notes on quota sharing — these decide whether a fallback actually helps:**
- Tiers 1 and 4 both draw on the *same* OpenRouter daily pool, and tiers 2 and 3
  both draw on the *same* Google pool. If tier 1 fails because a single model is
  down or rate-limited, tier 4 saves the request. If it fails because the
  OpenRouter **account** daily cap is spent, tier 4 fails too — and the chain
  really starts at tier 2. The same logic applies to 2 → 3.
- This is why Cerebras sits at tier 5 and not lower: it is the first genuinely
  independent quota after the OpenRouter and Google pools are gone.

**Reranking**: NVIDIA Llama Nemotron Rerank VL 1B V2 (`:free`, OpenRouter) —
used in the RAG layer to rerank retrieved candidates before sending them to the
LLM. Retrieve broadly, rerank, then send only the top results.

**Transport**: plain `requests` for every tier in Step 0 — one uniform style,
and it keeps the underlying HTTP call visible for learning. Three of the four
providers (OpenRouter, Cerebras, Modal) speak the **OpenAI-compatible**
`/chat/completions` shape, so they differ only in base URL, API key, and model
name. Google is the one odd shape. Migrating Gemini to the `google-genai` SDK
later is optional, and would be a change *inside* `LLMClient` only.

### Constraints
- OpenRouter free tier is roughly **50 requests/day** without purchased credits
  — reserve it for hard cases and evaluation, not bulk testing.
- OpenRouter free models require the *"Allow free endpoints that train on
  request data"* privacy setting.
- Gemini free tier: prompts may be used to improve Google's products. Grounding
  with Google Search is **not available** on the free tier — fetch papers in our
  own code instead.
- Do **not** use `openrouter/free` (the auto-router) — it varies the model
  between calls, which breaks repeatable comparison output.
- **Cerebras (tier 5)**: verified limits (2026-08-08) are **5 RPM, 2,400/day,
  30K tokens/min, 1M tokens/day, 131K context** — the same quota on every model.
  5 RPM is tight; the backoff must respect it. Other models offered are
  `gemma-4-31b` and `zai-glm-4.7`, both **Preview** — Preview models can change
  or disappear, so the chain depends on the Production one only.
- **Modal (tier 6) costs money and requires user consent.** Every call is billed
  against the $30 Starter credit (shared infrastructure by token). It is the
  only paid tier, it is never entered automatically, and the chain must not
  reach it during routine work — if the logs show tier 6 being offered often,
  something above it is misconfigured.
- **Default tier 6 to off.** A missing `MODAL_API_KEY` must not crash anything;
  the chain simply ends at tier 5 with a clean "all providers failed" error.
- **Log which model actually served each request**, for debugging and evaluation.
  With six tiers this stops being a nice-to-have: without it there is no way to
  tell a healthy chain from one silently burning Modal credit. The same fact is
  also *returned* in `LLMResult.model` — the log is for us, the return value is
  for the UI.
- **Log `finish_reason` too.** `stop` means the model ended on its own; `length`
  means our `max_tokens` cut the answer mid-sentence. Without this field a
  truncated comparison looks like a complete one.
- Implement retry/backoff on 429 before falling through to the next provider.
- Disclose the data-handling implications in the README.

### Build order — do not wire all six at once

Adding a provider is a small edit once the structure exists — that is the entire
point of `LLMClient`. Get **tier 1 alone** returning text first, then add the
fallback loop, then the remaining tiers. A six-provider client written in one
go has six places to be wrong at the same time.

Also unverified, and worth confirming against Modal's own model list before
wiring tier 6: that Kimi K3, Nemotron Ultra, DeepSeek V4 Pro, and DeepSeek V4
Flash are all currently served, and their exact model IDs. *(Separate point:
CLAUDE.md rules out Kimi K3 as a **fine-tune target** because 2.8T params need
datacenter hardware. Calling it through someone else's API is a different thing
and is not affected by that.)*

**Still not in the chain:**
- **Lightning AI Model APIs** — *an option only. Not a tier. Do not research
  further until the chain works.* Found 2026-08-09. A separate product from
  Studios, and unrelated to Lightning's GPU credits: a hosted per-token API over
  open and closed models. Their wording: *"Pay by the token. No credit card. Get
  30M free tokens."* Free tier: 15 req/min, 120,000 tokens/min. If a free tier
  is ever needed above Modal, this is the first place to look — but the six-tier
  chain must exist and work before anything is added to it.
- **Nebius Token Factory** — OpenAI-compatible, free credits. Only worth adding
  if yet another separate quota is ever needed. *(Card required for Nebius AI
  Cloud, and the Token Factory signup also asks for a card — treat as blocked.)*

---

## Platform Accounts — Verified August 2026

All accounts below were created and confirmed working on 2026-08-08. None
required a credit or debit card.

| Platform | Role in this project | Limits | Card? |
|---|---|---|---|
| **OpenRouter** | Chain tiers 1 + 4, reranker | ~50 req/day | No |
| **Google AI Studio** | Chain tiers 2 + 3 | ~1,500 RPD | No |
| **Cerebras Cloud** | Chain tier 5, development workhorse, evaluation baseline | 5 RPM / 2,400 per day | No |
| **Kaggle** | Fine-tuning (Step 4) | ~30 GPU-hrs/week, 2×T4 or P100, 12h sessions | No (phone verification) |
| **Lightning AI** | One-shot escape hatch for a bigger GPU (see note below) | **5 credits, one-time** (~2 A100-hrs); 1 CPU Studio free with 4-hr restarts | No (phone verification) |
| **Lightning Model APIs** | Chain candidate — not yet added | 30M free tokens (one-time), 15 RPM / 120K tok-min | No |
| **Hugging Face** | LoRA adapter hosting + **the public demo** | ZeroGPU: max 2 Spaces, small daily GPU-seconds quota | No |
| **Modal** | Chain tier 6 (last resort) + custom-weights API endpoint | $30 credit (Starter) | No |

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

**Use it for:** the 26B OOM test (see [Fine-Tuning](#fine-tuning-plan)) — and
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

---

## Build Plan — Walking Skeleton

Build a thin, crude, end-to-end slice first — every layer touched, nothing
polished — before deepening any single layer. This is deliberate: it surfaces
integration mismatches (model output vs. API shape vs. DB schema) early, when
they are cheap to fix, instead of after each layer is separately "finished."

| Step | Goal | Key tools |
|---|---|---|
| **0** | Walking skeleton: one hardcoded paper+code pair → dumb retrieval → single-pass agent (not the full graph) → bare API endpoint. No frontend polish, no fine-tuning. | `requests`, FastAPI |
| **1** | Real retrieval: chunking, embeddings, reranking | Supabase + pgvector |
| **2** | Full agent orchestration + observability | LangGraph, MLflow |
| **3** | Real deployment, session persistence, frontend polish | Docker, Render/Fly.io |
| **4** | Fine-tuning — **last** | Unsloth, Kaggle |

**Step 0's real goal** is to prove the core idea produces something useful, and
that every layer actually connects — before investing time in any one layer.

Rules for the sequence:
- **Never let one layer race far ahead of the others.** Run integration/smoke
  tests against the existing skeleton as each layer grows.
- **This rule applies to research too.** Investigating Step 4 infrastructure
  while Step 0 is unwritten is the same mistake in a different form. The
  platform question is now closed — see
  [Platform Accounts](#platform-accounts--verified-august-2026).
- **Fine-tuning stays last** — it depends on the core approach already being
  validated end-to-end.
- **MCP is a stretch goal**, not part of the initial skeleton (see Open Risks).

Parallel track: **dataset construction** does not depend on the agent/RAG system
and can start at any time.

Later, separate step: Persian and other-language translation of the app's
responses (not part of the fine-tune).

---

## Fine-Tuning Plan

- **Method**: QLoRA via Unsloth. Full fine-tuning is infeasible on free-tier
  hardware at any model size considered here.
- **Try first**: Gemma-4-26B-A4B (MoE, 25.2B total / ~3.8B active) — the
  stronger target, ~13–16GB in 4-bit.
- **Fall back to**: Gemma-4-E4B if the 26B proves too tight on Kaggle's 16GB
  GPU. E4B fits comfortably and is the safe option.
- *Risk note (unresolved)*: the 26B-first ordering is the ambitious choice.
  Loading it in 4-bit plausibly fits 16GB, but QLoRA training adds activations,
  gradients, and optimizer state on top — it may OOM. **Test with a tiny toy run
  early**; if it OOMs, drop to E4B rather than fighting it.
  **Escape hatch:** Lightning AI gives **~2 hours on an A100 40GB — once, not
  monthly** (5 one-time credits; corrected 2026-08-09). Use it to check whether
  the 26B trains *at all*, separately from whether it fits Kaggle's 16GB. Two
  hours is very little and does not come back — do not spend any of it exploring
  the interface. Start a **CPU** Studio first, install and prepare everything,
  then switch that same Studio to the A100 only when the code is ready to run.
  See [Lightning AI credit maths](#lightning-ai--read-the-credit-maths-before-using-it).
- **Ruled out**: Gemma-4-31B dense (does not fit a single free-tier GPU;
  multi-GPU is fragile and not worth it for a ~150–300 example dataset) and
  Kimi K3 (2.8T params, needs datacenter-scale infrastructure).
- Also comparing **Qwen3-4B** against the Gemma candidates.
- **Evaluation**: fine-tuned model vs. base model, and vs. `gemma-4-31b`.
  **Run the baseline on Cerebras**, not OpenRouter — 2,400 requests/day instead
  of ~50 makes a real evaluation possible in one sitting. Run the fine-tuned
  model on Modal or ZeroGPU. Where a like-for-like comparison matters, run both
  the fine-tuned model *and* the base model on Modal, on the same GPU with the
  same settings, so differences come from the fine-tuning and not the hardware.
- **Dataset**: ~150–300 examples, built from ~100 existing notebooks across
  projects, Kaggle competition write-ups, real papers where they genuinely
  exist, and notebook-vs-notebook pairs (one side rewritten as a paper-style
  paragraph).
- **Platform**: Kaggle Notebooks (free, ~30 GPU-hrs/week). Checkpoint the LoRA
  adapter regularly to survive session limits; resume across sessions rather
  than restarting.
- **Saving**: push LoRA adapters (small) to Hugging Face Hub during iteration;
  merge into a full model only at final deployment.

### Serving the fine-tuned model — demo only

**The live app always uses the hosted fallback chain.** It must keep working
whether or not the fine-tuned model is running. The fine-tuned model is a
portfolio artifact, never part of the live reasoning path.

Two serving paths, both free and both verified 2026-08-08:

**Primary — Hugging Face Space on ZeroGPU.** Permanent `*.hf.space` URL, works
without the user being present. This replaces the earlier Kaggle-tunnel plan.
- ZeroGPU allocates a shared GPU only *during* a decorated function call, then
  takes it back. The "large" slice is ~48GB VRAM — enough for the 26B MoE in
  4-bit, and far more than E4B needs.
- **Gradio SDK only.** Docker and CPU Basic Spaces now require a paid plan;
  Static Spaces are free but have no server, so they cannot run a model.
  A FastAPI server therefore cannot be written directly on a Space — but Gradio
  runs *on* FastAPI and exposes an HTTP API automatically, so the endpoint is
  still callable from code (`gradio_client` or the `/api/predict` route).
- Free accounts: max 2 ZeroGPU Spaces, account must be >30 days old with a
  verified email. Daily quota is measured in **GPU-seconds and is small**; a
  call reserves the full requested `duration` up front, so set a realistic small
  value rather than leaving the default.
- **Known unknown, test early:** Unsloth alters CUDA behaviour and ZeroGPU
  allocates the GPU unusually. For *serving*, prefer plain `transformers` +
  `peft` to load base + adapter, and keep Unsloth for *training* only. Also note
  the model cannot simply be loaded once at startup — the GPU only exists inside
  the decorated function. This is the most common place people get stuck.

**Secondary — Modal, "Custom weights".** Gives a real HTTPS endpoint on a
container you define, so a FastAPI-shaped API is possible exactly as originally
planned, on a GPU large enough for the 26B.
- Everything on Modal is billed from the $30 Starter credit — dedicated
  infrastructure by GPU-second, shared infrastructure by token.
- **Spend free quota first.** Modal is chain **tier 6** — reached only after
  OpenRouter, Google, and Cerebras have all failed. Never call it as a general
  provider for base models while those three still have quota, and never point
  development or bulk testing at it.
- **The $30 now has two jobs**, and they compete: serving the fine-tuned model
  demo, *and* backstopping the fallback chain. Serving the demo is the job
  nothing free can do, so it has priority. If chain tier 6 starts eating the
  credit, remove tier 6 rather than lose the demo.
- **Unverified:** whether the $30 renews monthly. Check the balance in early
  September 2026 before planning around it — and check it again once tier 6 has
  actually been exercised.
- Always confirm the app has scaled back to zero after testing.

**Considered and rejected for serving — Lightning AI.** *(Reason corrected
2026-08-09.)*

The earlier reason written here — "a Studio is a development machine, not a
host" — was **wrong**. Lightning's own free-tier feature table ticks *"Deploy
no-code model endpoints"* and *"Deploy full control model endpoints"*, and their
inference product (LitServe, containers as autoscaling APIs) is built exactly
for this. It **can** host a fine-tuned model with a real endpoint.

The real reason it is rejected is **arithmetic, not capability**: there is no
recurring free GPU allowance. 5 one-time credits ≈ **~2 hours on an A100**. A
served endpoint bills for every hour it is *up*, so the demo would die within a
day and never come back — and the credits never refill.

ZeroGPU wins because it bills nothing while idle: the GPU is only attached
*during* a call. That is the property serving needs, and Lightning's Studio
credits do not have it.

Lightning stays a **one-shot training escape hatch** only.

**Fallback — Kaggle notebook + Cloudflare Tunnel.** Still works for recording a
demo video with 2×T4. Non-permanent URL, 12h sessions, and Kaggle's AUP forbids
"server farming" — acceptable for a short recorded demo, never as a hosted
service. Do not point the deployed website at it.

**The portfolio artifact** is: LoRA adapter on the Hugging Face Hub + training
notebook + evaluation results + the live ZeroGPU Space (and a recorded video).

---

## Open Risks / Revisit Before or During the Build

*(flagged during planning — not yet resolved)*

- **Timeline is tight**: first exposure to RAG + agents + MCP + fine-tuning all
  at once. One month may be optimistic — consider extending if the
  walking-skeleton step reveals the core approach needs real rework, not just
  deepening.
- **MCP could be a stretch goal** rather than a hard week-4 deliverable — it is
  the least essential of the four skill gaps to the core product story.
- **Dataset construction is tedious and should not wait for week 4** — start it
  in parallel with week 1, since it does not depend on the agent/RAG system.
- **Risk sequencing**: fine-tuning is the least-familiar skill and is scheduled
  last. Consider a small early de-risking experiment (tiny toy fine-tune) before
  committing the full week-4 timeline.
- **Research can substitute for building.** Searching feels productive and
  produces visible output, but only writing code moves the project. If a session
  ends with more browser tabs than commits, that is the signal.
- **Free tiers change constantly.** Every number in this file was true on
  2026-08-08. Re-check against official pages before depending on any of them.

---

## Explicitly Out of Scope for v1

- Full (non-adapter) fine-tuning of any candidate model
- Gemma-4-31B and Kimi K3 as fine-tune targets
- Serving the fine-tuned model in the live application path
- Running any model on the local machine (hardware cannot support it)
- Any platform requiring a credit or debit card
- CrewAI (LangGraph is the v1 orchestrator)
- **v2 idea, not v1**: an autonomous "co-scientist" loop — agents that design,
  run, and critique experiments in a closed loop with no human involved. Same
  RAG/agent core as v1, extended after v1 ships. *Note:* v2 would execute
  untrusted code, so sandboxing (Incus, containers, VMs) becomes a real design
  question there — it is not needed in v1, which only reads code.

### Considered and rejected project ideas
MedAssist, DataPilot, DocDesk, CareTimeline/RepoMedic — considered before
settling on LabPilot.

---

*Keep this file current. Ask Claude to edit it directly ("update CLAUDE.md —
we're now using X instead of Y") rather than re-explaining context in each new
session.*

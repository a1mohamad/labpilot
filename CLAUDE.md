# CLAUDE.md — LabPilot

Project instructions for Claude Code, and orientation for any human reader.
Read the two rule sections first — they change *how* everything below is done.

**Contents:** [Working Rules](#working-rules-read-first) · [Overview](#project-overview) ·
[Status](#current-status) · [Environment](#development-environment) ·
[Conventions](#conventions) · [Architecture](#architecture--stack) ·
[LLM Serving](#llm-serving--fallback-chain) · [Build Plan](#build-plan--walking-skeleton) ·
[Fine-Tuning](#fine-tuning-plan) · [Risks](#open-risks--revisit-before-or-during-the-build) ·
[Out of Scope](#explicitly-out-of-scope-for-v1)

---

## Working Rules (Read First)

### Learning mode — this is a learning project, not a delivery project
This is the user's first project in RAG, agents, MCP, and LLM fine-tuning.
The goal is to **learn these concepts**, not only to end up with a finished app.

- **Explain before building.** Before any new piece (a RAG step, an agent node,
  an MCP integration, a fine-tuning step), first explain the concept in very
  simple terms — assume the user is a complete beginner in it. Simple
  *language*, never simplified or wrong *ideas*.
- **Do not write code by default.** Describe what needs to be done and let the
  user write and apply it themselves. Learning happens in the writing.
- **Exception:** write code directly only when the user explicitly asks — for
  example *"please code this for me."*
- This applies at **every stage** of the project, not only the first step.

### Communication
English proficiency is between B1 and B2, not a native speaker.

- Use clear, simple English words and short sentences.
- Simplify the *language*, not the *concepts*.
- Avoid idioms, slang, and heavily casual phrasing.

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

Next piece to build: the `LLMClient` — see [LLM Serving](#llm-serving--fallback-chain).

---

## Development Environment

Windows 11. **Git Bash** is the preferred shell (PowerShell also works, but the
commands below assume Git Bash).

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
Copy `.env.example` to `.env` and fill in real values. Two keys are needed:

| Variable | Used for | Where to get it |
|---|---|---|
| `OPENROUTER_API_KEY` | Fallback models 1–2 + the reranker | openrouter.ai/keys |
| `GOOGLE_API_KEY` | Fallback models 3–4 (Gemini) | aistudio.google.com/api-keys |

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
  and agent/RAG observability
- **Batch/offline jobs**: Airflow (offline only — never on the live request path)
- **Deployment**: Docker + Render or Fly.io
- **Session behavior**: chat continues within a case/session with persisted
  context — not reset each message

### Layer separation
Keep these three layers distinct; do not mix their responsibilities:

```
LangGraph      →  decides which steps run, and in what order   (Step 2)
    ↓
LLMClient      →  sends one prompt, returns one answer         (Step 0)
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
`generate(prompt) -> text`). **Nothing else in the codebase talks to a provider
directly.** This is deliberate: free endpoints appear and disappear constantly,
so a provider change must be a one-file edit, not a refactor.

Order of attempt (fall through on failure or 429):

| # | Model | Why |
|---|---|---|
| 1 | **NVIDIA Nemotron 3 Ultra** (`:free`, OpenRouter) | Primary. 1M context, MoE (55B active / 550B total). Strong on programming and long agentic workflows — best fit for the hard comparison reasoning. |
| 2 | **Ling 3.0 Flash** (`:free`, OpenRouter, by inclusionai) | Second free OpenRouter option. |
| 3 | **Gemini 3.6 Flash** | High-volume workhorse (~1,500 RPD), free context caching, 128K+ context. Used for development and routine comparisons. |
| 4 | **Gemini 3.5 Flash** | Final fallback. Also free tier with free context caching. |

**Reranking**: NVIDIA Llama Nemotron Rerank VL 1B V2 (`:free`, OpenRouter) —
used in the RAG layer to rerank retrieved candidates before sending them to the
LLM. Retrieve broadly, rerank, then send only the top results.

**Transport**: plain `requests` for all four models in Step 0 — one uniform
style, and it keeps the underlying HTTP call visible for learning. Migrating
Gemini to the `google-genai` SDK later is optional, and would be a change
*inside* `LLMClient` only.

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
- **Log which model actually served each request**, for debugging and evaluation.
- Implement retry/backoff on 429 before falling through to the next provider.
- Disclose the data-handling implications in the README.

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
- **Ruled out**: Gemma-4-31B dense (does not fit a single free-tier GPU;
  multi-GPU is fragile and not worth it for a ~150–300 example dataset) and
  Kimi K3 (2.8T params, needs datacenter-scale infrastructure).
- Also comparing **Qwen3-4B** against the Gemma candidates.
- **Evaluation**: fine-tuned model vs. base model, and vs.
  `google/gemma-4-31b-it:free` and `google/gemma-4-26b-a4b-it:free` on
  OpenRouter — both free, so no hosting needed for the comparison.
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
The fine-tuned model is **not** part of the live application path. No free host
can serve a 4B+ model: Hugging Face now requires a paid plan for Gradio/Docker
Spaces, and free app hosts (Render, Koyeb) cap at ~512MB RAM.

- **The live app always uses the hosted fallback chain.** It must keep working
  whether or not the fine-tuned model is running.
- **For demonstration**: load base model + LoRA adapter in a notebook (Kaggle or
  Colab), serve it behind a small FastAPI endpoint, expose it with a Cloudflare
  Tunnel. Record a video and put it in the README.
- *Caution*: demo-only, run interactively while present. Colab's terms disallow
  using managed runtimes as a web service for something else, and the tunnel URL
  changes on every restart. **Never point the deployed website at it.**
- **The portfolio artifact** is: LoRA adapter on the Hugging Face Hub + training
  notebook + evaluation results + the recorded demo. That demonstrates the
  fine-tuning skill without depending on infrastructure that does not exist for
  free.

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

---

## Explicitly Out of Scope for v1

- Full (non-adapter) fine-tuning of any candidate model
- Gemma-4-31B and Kimi K3 as fine-tune targets
- Serving the fine-tuned model in the live application path
- CrewAI (LangGraph is the v1 orchestrator)
- **v2 idea, not v1**: an autonomous "co-scientist" loop — agents that design,
  run, and critique experiments in a closed loop with no human involved. Same
  RAG/agent core as v1, extended after v1 ships.

### Considered and rejected project ideas
MedAssist, DataPilot, DocDesk, CareTimeline/RepoMedic — considered before
settling on LabPilot.

---

*Keep this file current. Ask Claude to edit it directly ("update CLAUDE.md —
we're now using X instead of Y") rather than re-explaining context in each new
session.*

# LabPilot — Project Instructions for Claude

## Project Overview
LabPilot is an agent-based tool that compares two pieces of work — a research
paper vs. code, or code vs. code — and explains why their results diverge,
then proposes the next experiment to test. It's a portfolio capstone project
deliberately scoped to close specific skill gaps: RAG, vector databases,
agent orchestration (including MCP), and LLM fine-tuning.

## Comparison Modes
- **Paper vs. Code** — compare a paper's claims/methodology against an implementation
- **Code vs. Code** — compare two implementations
- The "Code" side accepts either a single file/notebook or a full repository —
  same underlying comparison logic either way, just more files to retrieve from.

## What the Output Should Cover
For each comparison, surface:
1. Bugs or implementation errors
2. Differing approaches / design choices between the two sides
3. Missing details (hyperparameters, preprocessing steps, seeds, library
   versions) that the code had to assume
4. A causal explanation for *why* the results likely diverge — not just "these differ"
5. A concrete suggestion for the next experiment to run

## Edge Cases to Handle Explicitly
- **Mismatched domains** (e.g. an unrelated paper + repo): detect and report
  "no meaningful correspondence found" — never hallucinate a comparison.
- **Notebook vs. large repo**: rely on the RAG retrieval layer to narrow the
  repo down to relevant files. Never dump a whole repo into context.
- **Cross-language comparisons** (e.g. Python vs. C++): route the harder
  abstract/algorithmic reasoning to the top of the fallback chain
  (Nemotron 3 Ultra), not to the fine-tuned small model. The fine-tuned
  model is a demo artifact, not part of the live reasoning path.

## Architecture & Stack
- **Agent orchestration**: LangGraph as the core orchestrator; LangChain used
  selectively (document loaders, text splitters, model interfaces) — not CrewAI for v1.
- **Vector DB**: Supabase Postgres + pgvector
- **Experiment/observability tracking**: MLflow — both fine-tuning experiments
  and agent/RAG observability
- **Batch/offline jobs**: Airflow (offline only — not on the live request path)
- **Deployment**: Docker + Render or Fly.io
- **Session behavior**: chat continues within a case/session with persisted
  context — not reset each message

## LLM Serving — Fallback Chain
All model access goes through a single `LLMClient` interface (one method,
`generate(prompt) -> text`). Nothing else in the codebase talks to a provider
directly. This is deliberate: free endpoints appear and disappear constantly,
so a provider change must be a one-file edit, not a refactor.

Order of attempt (fall through on failure or 429):
1. **NVIDIA Nemotron 3 Ultra (`:free`, OpenRouter)** — primary. 1M context,
   MoE (55B active / 550B total), strong on programming and long-running
   agentic workflows. Best fit for the hard comparison reasoning.
2. **Ling 3.0 Flash (`:free`, OpenRouter, by inclusionai)** — second free
   OpenRouter option.
3. **Gemini 3.6 Flash** — third. Free tier, high volume (~1,500 RPD), free
   context caching, 128K+ context. This is the high-volume workhorse for
   development and routine comparisons.
4. **Gemini 3.5 Flash** — final fallback. Also free tier with free context caching.

**Reranking**: NVIDIA Llama Nemotron Rerank VL 1B V2 (`:free`, OpenRouter) —
used in the RAG layer to rerank retrieved candidates before sending them to
the LLM. Retrieve broadly, rerank, then send only the top results.

Notes and constraints:
- OpenRouter free tier is roughly **50 requests/day** without purchased
  credits — small, so reserve it for hard cases and evaluation, not bulk testing.
- OpenRouter free models require the "Allow free endpoints that train on
  request data" privacy setting to be enabled.
- Gemini free tier: prompts may be used to improve Google's products; Grounding
  with Google Search is **not available** on free tier (fetch papers in our
  own code instead).
- Do **not** use `openrouter/free` (the auto-router) — it varies the model
  between calls, which breaks repeatable comparison output.
- Log which model actually served each request, for debugging and evaluation.
- Implement retry/backoff on 429 before falling through to the next provider.
- Disclose the data-handling implications in the README.

## Fine-Tuning Plan
- Method: QLoRA via Unsloth (not full fine-tuning — infeasible on free-tier
  hardware at any model size considered here).
- **Try first**: Gemma-4-26B-A4B (MoE, 25.2B total / ~3.8B active) — the
  stronger target, ~13-16GB in 4-bit.
- **Fall back to**: Gemma-4-E4B if the 26B proves too tight on Kaggle's 16GB
  GPU. E4B fits comfortably and is the safe option.
- *Risk note (unresolved)*: the 26B-first ordering is the more ambitious
  choice. Loading it in 4-bit plausibly fits 16GB, but QLoRA training adds
  activations, gradients, and optimizer state on top — it may OOM. Test this
  early with a tiny toy run before committing time; if it OOMs, drop to E4B
  rather than fighting it.
- **Ruled out for this project**: Gemma-4-31B dense (doesn't fit a single
  free-tier GPU; multi-GPU is fragile and likely not worth it for a
  ~150-300 example dataset) and Kimi K3 (2.8T params, needs datacenter-scale
  infrastructure — not a candidate at any budget considered here).
- Also comparing Qwen3-4B against the Gemma candidates.
- **Evaluation**: compare the fine-tuned model against the base model, and
  against `google/gemma-4-31b-it:free` and `google/gemma-4-26b-a4b-it:free`
  on OpenRouter — both free, so no hosting needed for the comparison.
- **Dataset**: built from ~100 existing notebooks across projects, Kaggle
  competition write-ups, real papers where they genuinely exist, and
  notebook-vs-notebook pairs (one side rewritten as a paper-style paragraph);
  targeting ~150-300 examples.
- **Platform**: Kaggle Notebooks (free, ~30 GPU-hrs/week). Checkpoint the LoRA
  adapter regularly to survive session limits; resume across sessions rather
  than restarting.
- **Saving**: push LoRA adapters (small) to Hugging Face Hub during iteration;
  merge into a full model only at final deployment.

## Fine-Tuned Model Serving — Demo Only
The fine-tuned model is **not** part of the live application path. No free
host can serve a 4B+ model: Hugging Face now requires a paid plan to create
Gradio/Docker Spaces, and free app hosts (Render, Koyeb) cap at ~512MB RAM.

Instead:
- **The live app always uses the hosted fallback chain above.** It must keep
  working whether or not the fine-tuned model is running.
- **For demonstration**: load base model + LoRA adapter in a notebook
  (Kaggle or Colab), serve it behind a small FastAPI endpoint, expose it with
  a Cloudflare Tunnel, and use that to prove the fine-tune works. Record a
  video of this and put it in the README.
- *Caution*: this is demo-only, run interactively while present. Colab's terms
  disallow using managed runtimes as a web service for something else, and
  the tunnel URL changes on every restart. Do not point the deployed website
  at it as a dependency.
- **The portfolio artifact** is: LoRA adapter on the Hugging Face Hub +
  training notebook + evaluation results vs. base and vs. the free Gemma
  models + the recorded demo. That fully demonstrates the fine-tuning skill
  without depending on infrastructure that doesn't exist for free.

## Build Plan — Walking Skeleton
Build a thin, crude, end-to-end slice first — every layer touched, nothing
polished — before deepening any single layer. This is deliberate: it surfaces
integration mismatches (model output vs. API shape vs. DB schema, etc.) early,
when they're cheap to fix, instead of after each layer is separately "finished."

- **Step 0 (first)**: one hardcoded paper+code pair → dumb/minimal retrieval →
  a single-pass agent (not the full LangGraph graph yet) → a bare API
  endpoint → no frontend polish. Hosted LLM, no fine-tuning yet. Goal: prove
  the core idea produces something useful, and that every layer actually
  connects, before investing real time in any one of them.
- **Then deepen layer by layer**, running integration/smoke tests against the
  existing skeleton as each layer grows — never let one layer race far ahead
  of the others: fuller retrieval, the full LangGraph orchestration, real
  deployment (Docker + Render/Fly.io), frontend polish.
- **Fine-tuning (QLoRA) stays last** — it depends on the core approach already
  being validated end-to-end, same as originally planned.
- **MCP** stays a stretch goal, not part of the initial skeleton (see Open Risks).
- Later, separate step: Persian + other language translation of the app's
  responses (not part of the fine-tune).

## Open Risks / Revisit Before or During the Build
*(flagged during planning — not yet resolved)*
- **Timeline is tight**: this is a first exposure to RAG + agents + MCP +
  fine-tuning all at once. One month may be optimistic — consider extending
  the timeline if the walking-skeleton step reveals the core approach needs
  real rework, not just deepening.
- **MCP could be a stretch goal** rather than a hard week-4 deliverable —
  it's the least essential of the four skill gaps to the core product story.
- **Dataset construction is tedious and shouldn't wait for week 4** — consider
  starting it in parallel with week 1, since it doesn't depend on the
  agent/RAG system being built yet.
- **Risk sequencing**: fine-tuning is the least-familiar skill and currently
  scheduled last. Consider a small early de-risking experiment (tiny toy
  fine-tune) before committing the full week-4 timeline to it.

## Explicitly Out of Scope for v1
- Full (non-adapter) fine-tuning of any candidate model
- Gemma-4-31B and Kimi K3 as fine-tune targets
- Serving the fine-tuned model in the live application path
- CrewAI (LangGraph is the v1 orchestrator)
- **v2 idea, not v1**: an autonomous "co-scientist" loop — agents that
  design, run, and critique experiments in a closed loop with no human in
  the loop. Same RAG/agent core as v1, extended after v1 ships.

## Communication
English proficiency is between B1 and B2, not a native speaker. Use clear,
simpler English phrasing and vocabulary — not shortened, not simplified
concepts, just simpler language. Avoid idiom-heavy or overly casual phrasing.

## Learning Mode (How to Work on This Project)
This is the user's first project in RAG, agents, MCP, and LLM fine-tuning.
The explicit goal is to learn these concepts, not just to get a finished app.

- **Before building any new piece** (a RAG step, an agent node, an MCP
  integration, a fine-tuning step, etc.), first explain the concept in very
  simple terms — assume the user is a beginner ("noob") in that concept.
  Simple language, not simplified/wrong ideas.
- **Do not write and hand over code by default.** Explain what needs to be
  done and let the user write and apply it themselves, so they learn by
  doing.
- **Exception**: only write code directly when the user explicitly asks,
  e.g. "please code this for me."
- This applies to the whole build process, not just the walking-skeleton
  step — keep it in mind at every stage of the project.

## Considered and Rejected Project Ideas
MedAssist, DataPilot, DocDesk, CareTimeline/RepoMedic — considered before
settling on LabPilot.

---
*Update this file as decisions change. Ask Claude to edit it directly
("update CLAUDE.md — we're now using X instead of Y") rather than
re-explaining context each new session.*

# Build plan

[Docs home](../README.md)

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
| **3** | Real deployment, session persistence, frontend polish. **At its END: the daily update of the chain and the routes ([section 32](../step3/daily-chain-update.md#32-the-daily-update-of-the-chain-and-the-routes--an-idea-of-the-user-2026-11-18-for-the-end-of-step-3))** | Docker, Render/Fly.io, Airflow or a scheduled workflow |
| **4** | Fine-tuning — **last** | Unsloth, Kaggle |

**Step 0's real goal** is to prove the core idea produces something useful, and
that every layer actually connects — before investing time in any one layer.

Rules for the sequence:
- **Never let one layer race far ahead of the others.** Run integration/smoke
  tests against the existing skeleton as each layer grows.
- **This rule applies to research too.** Investigating Step 4 infrastructure
  while Step 0 is unwritten is the same mistake in a different form. The
  platform question is now closed — see
  [Platform Accounts](../llm/platform-accounts.md#platform-accounts--verified-august-2026).
- **Fine-tuning stays last** — it depends on the core approach already being
  validated end-to-end.
- **MCP is a stretch goal**, not part of the initial skeleton (see Open Risks).

Parallel track: **dataset construction** does not depend on the agent/RAG system
and can start at any time.

Later, separate step: Persian and other-language translation of the app's
responses (not part of the fine-tune).


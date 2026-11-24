# Architecture and stack

[Docs home](../README.md)

## Architecture & Stack

- **Agent orchestration**: LangGraph as the core orchestrator. LangChain is used
  **selectively** — ~~document loaders,~~ text splitters and model interfaces
  only. Do **not** use LangChain's own agent/chain abstractions; orchestration
  belongs to LangGraph. Not CrewAI for v1.
  **Document loaders were removed from this list on 2026-08-20** — they live in
  `langchain-community`, which LangGraph does not need, and they require the
  underlying parser to be installed anyway. See
  [Do not use LangChain's document loaders](../step1/document-formats.md#do-not-use-langchains-document-loaders--corrected-2026-08-20).
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


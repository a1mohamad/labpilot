# Memory budget

[Docs home](../README.md)

### Memory budget — Render free tier, 512MB

*Recorded 2026-08-11. Estimates, not measurements — verify at Step 3 with
`docker stats` on a real ingest.*

| Piece | Estimate |
|---|---|
| Python 3.13 + FastAPI + uvicorn | ~90MB |
| LangGraph + minimal LangChain | ~120–200MB |
| psycopg / Supabase client, misc | ~30MB |
| Working memory during ingest | ~50MB |
| *(ONNX reranker, if shipped)* | *~120MB* |

Without the local reranker that is ~290–370MB against a hard 512MB ceiling.
Exceeding it does not slow down — it **kills the process**.

> **CORRECTED 2026-09-23 (Step 2 slice 0, measured in the real container): the
> whole process is 51.6 MiB idle and 74 MiB after a 928-chunk repository ingest,
> about 6x BELOW the estimate above.** Headroom is ~438 MB, importing LangGraph
> adds only ~55 MB, and rule 4 below (leave the local reranker out) rested on the
> wrong number and is re-opened. The ~290-370MB table above is kept as the
> original estimate only. See
> [Step 2 section 10](../step2/10-slice-0-memory.md#10-slice-0-is-closed-and-the-memory-budget-was-6x-wrong--2026-09-23).

Four rules that keep it under:

1. **Never install `torch`.** ~800MB installed, 300–500MB resident. This is the
   single decision that would end the free tier instantly. Use ONNX/`fastembed`
   if a local model is ever needed.
2. **Keep LangChain minimal** — loaders, splitters and model interfaces only.
   Already a design rule; it is now also a memory requirement.
3. **Stream the repo walk** (above).
4. **Leave the local reranker out of the container.** Reranking is the one stage
   whose total failure is *degraded, not fatal*, so it is the correct thing to
   drop first.

Two Render facts that shape Step 3: free instances **spin down when idle** and
cold-start on the next request, and **ingest runs in the same process** as the
API — one service, no separate worker — so a 20-minute embed occupies the same
512MB the API is serving from.

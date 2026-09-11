from __future__ import annotations

from labpilot.rerank.cloudflare import CloudflareReranker
from labpilot.rerank.cohere import CohereReranker
from labpilot.rerank.voyage import VoyageReranker

COHERE_URL = "https://api.cohere.com/v2/rerank"
VOYAGE_URL = "https://api.voyageai.com/v1/rerank"
CLOUDFLARE_URL = "https://api.cloudflare.com/client/v4/accounts"

# 1,000 calls a MONTH, and that bucket is shared with chat and embed. Tests
# must never reach it: they mock HTTP at the `responses` boundary, and the one
# live test is marked smoke and opt-in.
COHERE_RERANK = CohereReranker(
    name="Cohere Rerank v4 Fast",
    url=COHERE_URL,
    model="rerank-v4.0-fast",
)

# 200M tokens, granted ONCE and never renewed - about 16,000 calls at our
# measured ~12,450 tokens per 50-document call.
#
# SERIES 3, and that is a correction rather than a preference. CLAUDE.md chose
# `rerank-2.5-lite` on 2026-08-11; Voyage's own dashboard says the free grant
# covers "Voyage series 3 models", which 2.5 is not. Both were probed live on
# 2026-09-11 and both answer, so the older one was costing us the grant while
# also being a generation behind.
#
# A card-free account is capped at 10,000 TPM and 3 RPM for EVERY rerank model,
# read from that same dashboard and confirmed by a live 429. That cap is
# per-minute and a single call counts against it whole, so a 50-document call
# of our chunks (~16,900 tokens) is refused NO MATTER how long you wait -
# measured: 50 refused, 40 refused, 30 passes. Voyage therefore cannot serve
# SEARCH_LIMIT today, and the chain falls through to Cloudflare for one wasted
# request. Slice 8 owns whether that is worth reordering for.
#
# `rerank-3` (the non-lite variant) also answers and scored marginally higher
# on the probe. It consumes the same tokens, so it is a real slice 8 candidate.
VOYAGE_RERANK_3 = VoyageReranker(
    name="Voyage Rerank 3",
    url=VOYAGE_URL,
    model="rerank-3",
)

VOYAGE_RERANK_3_LITE = VoyageReranker(
    name="Voyage Rerank 3 Lite",
    url=VOYAGE_URL,
    model="rerank-3-lite",
)

# ~2,840 calls a DAY, which is the largest renewing budget here by a wide
# margin, and the instrument the slice 6 measurement actually ran on.
CLOUDFLARE_RERANK = CloudflareReranker(
    name="BGE Reranker Base",
    url=CLOUDFLARE_URL,
    model="@cf/baai/bge-reranker-base",
)

# The order is CLAUDE.md's and stays, on the rule "spend the bucket that
# expires anyway, bank the one-time grant". It has NEVER been measured - it is
# a quota-shape argument, and a quota-shape argument is no evidence that these
# three rank alike. Slice 8 owns it, and the candidate order it must beat this
# one against is recorded in CLAUDE.md: local ONNX, then Cloudflare, then
# Voyage, then Cohere - the exact opposite of this, because per QUERY rather
# than per report, Cohere's 1,000 a month is the smallest budget of the three.
#
# `ministral-3b-2512` is tier 4 in CLAUDE.md and is DELIBERATELY ABSENT. It is
# LLM-as-reranker: a different mechanism needing a prompt, a parse and its own
# failure modes, reached only when all three cross-encoders are gone. Recorded
# as unbuilt rather than half-built, like HNSW on the shelf.
RERANK_CHAIN = (
    COHERE_RERANK,
    VOYAGE_RERANK_3,
    VOYAGE_RERANK_3_LITE,
    CLOUDFLARE_RERANK,
)

# The two Voyage tiers share one API key, one 200M grant and one 10K TPM
# ceiling, so a rate-limit refusal will almost always hit BOTH - the chain
# spends two requests to learn one fact. That is accepted rather than
# overlooked: a 429 costs no tokens, so the price is latency and not quota,
# and the pair buys real redundancy against a single model being withdrawn or
# briefly broken. If it ever matters, the fix is pool-aware skipping like
# llm/chain.py has, not reordering.
#
# NOT MEASURED, and deliberately so. `rerank-3` scored marginally higher than
# `rerank-3-lite` on the 2026-09-11 probe (0.8594 against 0.8516 on one pair),
# which is a reason to try it first and NOT evidence that it ranks better.
# Slice 8 scores them properly.

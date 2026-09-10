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
VOYAGE_RERANK = VoyageReranker(
    name="Voyage Rerank 2.5 Lite",
    url=VOYAGE_URL,
    model="rerank-2.5-lite",
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
    VOYAGE_RERANK,
    CLOUDFLARE_RERANK,
)

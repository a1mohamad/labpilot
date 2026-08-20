from __future__ import annotations

from labpilot.embed.cloudflare import CloudflareEmbedder
from labpilot.embed.cohere import CohereEmbedder
from labpilot.embed.google import GoogleEmbedder
from labpilot.embed.mistral import MistralEmbedder

MISTRAL_URL = "https://api.mistral.ai/v1/embeddings"
CLOUDFLARE_URL = "https://api.cloudflare.com/client/v4/accounts"
GOOGLE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
COHERE_URL = "https://api.cohere.com/v2/embed"

CODESTRAL_EMBED = MistralEmbedder(
    name="Codestral Embed",
    url=MISTRAL_URL,
    model="codestral-embed",
    dim=1536,
)

MISTRAL_EMBED = MistralEmbedder(
    name="Mistral Embed",
    url=MISTRAL_URL,
    model="mistral-embed",
    dim=1024,
)

# BGE truncates at 512 tokens and says nothing about it, so the limit is
# declared here and refused locally instead of arriving as a weaker vector.
BGE_BASE = CloudflareEmbedder(
    name="BGE Base EN v1.5",
    url=CLOUDFLARE_URL,
    model="@cf/baai/bge-base-en-v1.5",
    dim=768,
    max_input_tokens=512,
)

# UNVERIFIED. Written from Google's documentation because the API answers
# 400 FAILED_PRECONDITION - "User location is not supported" from here as of
# 2026-08-20, on generation and embedding alike. dim=3072 is the documented
# default and has never been observed; a wrong value fails loudly in
# _validated rather than silently, which is why it is safe to ship unproven.
GEMINI_EMBEDDING = GoogleEmbedder(
    name="Gemini Embedding 001",
    url=GOOGLE_URL,
    model="gemini-embedding-001",
    dim=3072,
    max_input_tokens=2048,
)

# Deliberately last, and not because it is weak. Cohere's 1,000 calls/month are
# ONE bucket shared by chat, embed and rerank - and Cohere is the reranker
# primary. A corpus embedded here keeps spending that bucket on every query
# forever. The monthly ceiling is confirmed by its own response header,
# x-endpoint-monthly-call-limit: 1000.
COHERE_EMBED = CohereEmbedder(
    name="Cohere Embed v4",
    url=COHERE_URL,
    model="embed-v4.0",
    dim=1536,
)

# Measured models first, in measured order; unmeasured after them; Cohere last
# for the quota reason above. One structural override: BGE sits second because
# it is the only early entry on a different platform - codestral and
# mistral-embed share one API key, so a Mistral outage would take both.
MIGRATION = (
    CODESTRAL_EMBED,
    BGE_BASE,
    MISTRAL_EMBED,
    GEMINI_EMBEDDING,
    COHERE_EMBED,
)

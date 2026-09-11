from __future__ import annotations

import dataclasses

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

# UNVERIFIED against our own fixture, and shipped anyway - the same gamble as
# `gemini-embedding-001` on 2026-08-20, and safe for the same reason: `dim` is
# documented rather than observed, so a wrong value raises loudly in
# `_validated` on the first real call instead of storing a wrong-width vector.
#
# It is ranked above 001 on Google's own evidence, NOT ours: version 2 against
# version 001 in the model listing, MTEB mean-by-task 69.9 against 68.32, and a
# 8,192 token input limit against 2,048. This file's rule is that MIGRATION is
# ordered by MEASURED recall, so **slice 8 owes this model a score** - it is
# the only entry here ranked on somebody else's benchmark.
#
# The bigger input limit removes a constraint CLAUDE.md recorded as permanent:
# 001's 2,048 tokens meant our 510-token chunk cap could never rise. 8,192 does
# not bind at any chunk size we would choose.
#
# THE TWO SPACES ARE INCOMPATIBLE - Google says so explicitly. That is not a
# footnote here, it is the whole reason MIGRATION is a migration: moving from
# 001 to 2 means re-embedding every corpus, and only the SAME model on the
# other key is a free continuation.
GEMINI_EMBED_2 = GoogleEmbedder(
    name="Gemini Embedding 2",
    url=GOOGLE_URL,
    model="gemini-embedding-2",
    dim=3072,
    max_input_tokens=8192,
)

GEMINI_EMBED_2_KEY2 = dataclasses.replace(
    GEMINI_EMBED_2,
    name="Gemini Embedding 2 (key 2)",
    api_key_env="GOOGLE_API_KEY_2",
)

# Proven live 2026-08-27: 200, dim 3072 observed. Kept below embedding-2 but
# above Cohere, because it is measured on OUR fixture and is the only model
# with perfect recall@5 there (1.000, against codestral's 0.941).
GEMINI_EMBED_001 = GoogleEmbedder(
    name="Gemini Embedding 001",
    url=GOOGLE_URL,
    model="gemini-embedding-001",
    dim=3072,
    max_input_tokens=2048,
)

# THE ONE TRUE FALLBACK SHAPE IN THIS LIST, and it is worth being precise.
#
# MIGRATION is a migration order, not a fallback chain: every step between
# different MODELS means re-embedding the whole corpus. The SAME model on a
# SECOND ACCOUNT is the exception - identical model, identical vectors,
# verified bit-identical on 2026-09-11 - so a corpus half-ingested on key 1 can
# be FINISHED on key 2 and still be one coherent space.
#
# A real second budget too: Google bills per project per model, so each of
# these four Google entries is its own 1,000 requests a day.
GEMINI_EMBED_001_KEY2 = dataclasses.replace(
    GEMINI_EMBED_001,
    name="Gemini Embedding 001 (key 2)",
    api_key_env="GOOGLE_API_KEY_2",
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
    GEMINI_EMBED_2,
    GEMINI_EMBED_2_KEY2,
    GEMINI_EMBED_001,
    GEMINI_EMBED_001_KEY2,
    COHERE_EMBED,
)

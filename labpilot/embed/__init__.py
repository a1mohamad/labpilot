from labpilot.embed.base import HTTPEmbedder
from labpilot.embed.batching import embed_batches, looks_like_too_many_tokens
from labpilot.embed.cloudflare import CloudflareEmbedder
from labpilot.embed.cohere import CohereEmbedder
from labpilot.embed.contracts import EmbeddingBatch, Rate, Task, Vector
from labpilot.embed.defaults import MAX_BATCH_SIZE
from labpilot.embed.errors import EmbeddingError
from labpilot.embed.google import GoogleEmbedder
from labpilot.embed.mistral import MistralEmbedder
from labpilot.embed.registry import (
    BGE_BASE,
    CODESTRAL_EMBED,
    COHERE_EMBED,
    GEMINI_EMBED_001,
    GEMINI_EMBED_001_KEY2,
    GEMINI_EMBED_2,
    GEMINI_EMBED_2_KEY2,
    MIGRATION,
    MISTRAL_EMBED,
    RATES,
    by_speed,
)

__all__ = [
    "BGE_BASE",
    "CODESTRAL_EMBED",
    "COHERE_EMBED",
    "GEMINI_EMBED_001",
    "GEMINI_EMBED_001_KEY2",
    "GEMINI_EMBED_2",
    "GEMINI_EMBED_2_KEY2",
    "MAX_BATCH_SIZE",
    "MIGRATION",
    "MISTRAL_EMBED",
    "RATES",
    "CloudflareEmbedder",
    "CohereEmbedder",
    "EmbeddingBatch",
    "EmbeddingError",
    "GoogleEmbedder",
    "HTTPEmbedder",
    "MistralEmbedder",
    "Rate",
    "Task",
    "Vector",
    "by_speed",
    "embed_batches",
    "looks_like_too_many_tokens",
]

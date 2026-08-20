from __future__ import annotations

from labpilot.embed.mistral import MistralEmbedder

MISTRAL_URL = "https://api.mistral.ai/v1/embeddings"

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

MIGRATION = (CODESTRAL_EMBED, MISTRAL_EMBED)

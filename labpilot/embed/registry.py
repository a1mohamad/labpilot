from __future__ import annotations

from labpilot.embed.cloudflare import CloudflareEmbedder
from labpilot.embed.mistral import MistralEmbedder

MISTRAL_URL = "https://api.mistral.ai/v1/embeddings"
CLOUDFLARE_URL = "https://api.cloudflare.com/client/v4/accounts"

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

# Order is capability first, with one structural override: BGE sits second
# because it is the only entry on a different platform. codestral and
# mistral-embed share one API key, so a Mistral outage would take both.
# Its 0.824 recall@5 against mistral-embed's 0.765 is one query out of
# seventeen - noise, and not the reason it was promoted.
MIGRATION = (CODESTRAL_EMBED, BGE_BASE, MISTRAL_EMBED)

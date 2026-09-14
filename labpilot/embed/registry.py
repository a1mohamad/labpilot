from __future__ import annotations

import dataclasses
from collections.abc import Sequence

from labpilot.embed.base import HTTPEmbedder
from labpilot.embed.cloudflare import CloudflareEmbedder
from labpilot.embed.cohere import CohereEmbedder
from labpilot.embed.contracts import Rate, Spec
from labpilot.embed.google import GoogleEmbedder
from labpilot.embed.mistral import MistralEmbedder

MISTRAL_URL = "https://api.mistral.ai/v1/embeddings"
CLOUDFLARE_URL = "https://api.cloudflare.com/client/v4/accounts"
GOOGLE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
COHERE_URL = "https://api.cohere.com/v2/embed"

# EVERY MODEL'S FACTS IN ONE PLACE, so they can be read against each other
# instead of hunted through eight constructors. Only what the PROVIDER decides
# lives here; the display name, the URL and the key stay on the entry.
#
# `measured_tokens_per_minute` IS OURS, NOT THE VENDOR'S, and that distinction
# is why it exists. Measured 2026-09-13/14 from a Frankfurt VPN exit, varying
# batch sizes, averaged over every run we have:
#
#   codestral-embed   620k / 600k / 590k / 474k over 1, 4, 37 and 18 requests.
#                     Mean of the three MULTI-REQUEST runs = 554k. Its
#                     DOCUMENTED quota is 50,000 and we exceeded it 11.8x for
#                     71 seconds with zero refusals, so the published number
#                     predicts nothing on this account.
#   mistral-embed     520k over 25 requests today, and 504k across slice 4's
#                     separate 849-request, 45-minute five-repo ingest. Two
#                     sessions weeks apart, mean 512k.
#   gemini-*          Google ENFORCES its published 30,000 exactly. A single
#                     unthrottled batch measured 274k, and averaging that in
#                     would be nonsense - it never met the limit that governs
#                     the other run. Only the throttled measurement counts.
#   embed-v4.0        641k over 6 requests, BURST ONLY: capped at 6 to protect
#                     a 1,000-a-MONTH budget, so no limit was reached. Its 10
#                     requests/minute is what actually binds.
#   bge-base          288k, 926k and 732k - a 3.2x spread on the SAME work, so
#                     the roughest number here. Academic anyway: the daily
#                     neuron budget stops it long before a rate does.
#
# These are MEANS, not promises - our best estimate of the truth, UNBIASED on
# purpose. Padding belongs at the display, never in the estimator, or we
# abandon the strongest model earlier than the data justifies. One account,
# one VPN, two days.

SPECS: dict[str, Spec] = {
    "codestral-embed": Spec(
        dim=1536,
        rate=Rate(tokens_per_minute=50_000, requests_per_minute=60),
        measured_tokens_per_minute=550_000,
    ),
    "mistral-embed": Spec(
        dim=1024,
        rate=Rate(tokens_per_minute=20_000_000, requests_per_minute=60),
        measured_tokens_per_minute=510_000,
    ),
    "@cf/baai/bge-base-en-v1.5": Spec(
        dim=768,
        max_input_tokens=512,
        rate=Rate(requests_per_minute=16, daily_token_budget=684_000),
        measured_tokens_per_minute=650_000,
    ),
    "gemini-embedding-2": Spec(
        dim=3072,
        max_input_tokens=8192,
        rate=Rate(tokens_per_minute=30_000, requests_per_minute=100),
        measured_tokens_per_minute=29_000,
    ),
    "gemini-embedding-001": Spec(
        dim=3072,
        max_input_tokens=2048,
        rate=Rate(tokens_per_minute=30_000, requests_per_minute=100),
        measured_tokens_per_minute=29_000,
    ),
    "embed-v4.0": Spec(
        dim=1536,
        rate=Rate(requests_per_minute=10),
        measured_tokens_per_minute=640_000,
    ),
}


def _spec(model: str) -> dict[str, object]:
    """The provider's half of a constructor call.

    A model missing from SPECS is a KeyError at IMPORT, not a wrong vector at
    runtime - which is the point of the table. You cannot add an entry and
    forget its facts.
    """
    spec = SPECS[model]
    return {
        "model": model,
        "dim": spec.dim,
        "max_input_tokens": spec.max_input_tokens,
        "rate": spec.rate,
        "measured_tokens_per_minute": spec.measured_tokens_per_minute,
    }


CODESTRAL_EMBED = MistralEmbedder(
    name="Codestral Embed",
    url=MISTRAL_URL,
    **_spec("codestral-embed"),
)

MISTRAL_EMBED = MistralEmbedder(
    name="Mistral Embed",
    url=MISTRAL_URL,
    **_spec("mistral-embed"),
)

# BGE truncates at 512 tokens and says nothing about it, so the limit is
# declared in SPECS and refused locally instead of arriving as a weaker vector.
#
# THE GUARD IS ENFORCED IN THE WRONG UNITS, and that is an open defect.
# _check_texts measures with our own chars/3 estimate, while BGE's tokenizer
# runs ~2.36x that on our corpus - 39,936 BGE tokens against codestral's
# 14,979 for the identical text, slice 1b. So its real limit is about 217 of
# OUR tokens, and 73.8% of this repository's chunks would pass the guard and
# be silently truncated. Nothing is truncated today because BGE has no caller.
# Slice 8 owns the fix, and owes BGE three numbers: speed, strength, and its
# real tokenizer ratio.
BGE_BASE = CloudflareEmbedder(
    name="BGE Base EN v1.5",
    url=CLOUDFLARE_URL,
    **_spec("@cf/baai/bge-base-en-v1.5"),
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
    **_spec("gemini-embedding-2"),
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
    **_spec("gemini-embedding-001"),
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

# LAST IN THE STRENGTH ORDER, and not because it is weak. Cohere's 1,000 calls
# a month are ONE bucket, an embedded corpus spends it on every future query
# forever, and it is the smallest renewing budget here by roughly 120x against
# the four Google entries.
#
# Its old reason is DEAD and should not be quoted: this file used to say
# "Cohere is the reranker primary", and slice 6 demoted it to rerank tier 7 of
# 8 behind four Google LLM tiers worth ~29,800 calls a day. What still carries
# the decision is the budget, not the reranker.
#
# In the SPEED order it sits near the FRONT: 10 requests/minute x a 96-chunk
# batch is ~960 chunks/minute, far quicker than codestral. That is the whole
# reason one list is sorted two ways instead of being split in two.
COHERE_EMBED = CohereEmbedder(
    name="Cohere Embed v4",
    url=COHERE_URL,
    **_spec("embed-v4.0"),
)

# THE STRENGTH ORDER. Measured models first, in measured order; unmeasured
# after them; Cohere last for the quota reason above. One structural override:
# BGE sits second because it is the only early entry on a different platform -
# codestral and mistral-embed share one API key, so a Mistral outage would take
# both.
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


def by_speed(
    *, tokens: int, chunks: int, candidates: Sequence[HTTPEmbedder] = MIGRATION
) -> tuple[HTTPEmbedder, ...]:
    """The SAME list, re-ordered by how fast each model ingests THIS corpus.

    Not a second list, and that is the point. A two-pool version was proposed
    first and was wrong: two fast models, both spent, and nowhere left to go.
    Here only a model's PLACE moves, so the walk can never dead-end.

    `sorted` is stable, so models of equal speed keep MIGRATION's order - which
    means ties break by STRENGTH, for free. MIGRATION stays the strength
    ordering; there is no second list to keep in step with it.
    """
    return tuple(
        sorted(
            candidates, key=lambda e: e.embedding_minutes(tokens=tokens, chunks=chunks)
        )
    )

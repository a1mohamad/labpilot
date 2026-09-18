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
        # daily_text_budget, not daily_token_budget: Google counts one TEXT as
        # one request, so a 96-text batch spends 96 of the day's 1,000. Read
        # from the account's own rate-limit page and confirmed by two 429s on
        # 2026-09-18 - a warm died on its SECOND corpus, and 001 exhausted
        # after 943 chunks.
        rate=Rate(
            tokens_per_minute=30_000,
            requests_per_minute=100,
            daily_text_budget=1_000,
        ),
        measured_tokens_per_minute=29_000,
    ),
    "gemini-embedding-001": Spec(
        dim=3072,
        max_input_tokens=2048,
        # Same per-TEXT billing as embedding-2, and a separate 1,000 a day:
        # Google's quota is per project per MODEL.
        rate=Rate(
            tokens_per_minute=30_000,
            requests_per_minute=100,
            daily_text_budget=1_000,
        ),
        measured_tokens_per_minute=29_000,
    ),
    "embed-v4.0": Spec(
        dim=1536,
        # Cohere bills per CALL, and a call carries up to 96 texts - so unlike
        # Google the limit is NOT per text. 1,000 calls a MONTH, shared with
        # reranking and chat, is ~96,000 chunks a month; a single ingest is
        # gated by the token rate instead. The monthly ceiling is a BUDGET
        # question for the caller, not a per-ingest refusal, so it is
        # deliberately not modelled as daily_text_budget here - doing so would
        # refuse a corpus this model can in fact embed today.
        #
        # 100,000 tokens/minute is the TRIAL cap, measured 2026-09-16 by
        # hitting it. The registry previously carried 640,000, which was a
        # burst that never met a limit - 6.4x optimistic.
        rate=Rate(requests_per_minute=10, tokens_per_minute=100_000),
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

# MEASURED AND DEMOTED, 2026-09-18. This entry used to sit ABOVE 001 on
# Google's own evidence rather than ours - version 2 against version 001 in the
# model listing, MTEB mean-by-task 69.9 against 68.32 - and the comment here
# said plainly that it was the only entry in MIGRATION ranked on somebody
# else's benchmark, with "slice 8 owes this model a score".
#
# Slice 8 scored it. It LOST, on our own fixture, on 3 of the 4 corpora where
# both models ran:
#
#     corpus      001     2
#     websocket   0.530   0.364     001
#     requests    0.650   0.559     001
#     geo         0.493   0.341     001
#     quora       0.674   0.702       2
#
# v2's G21 reached the same verdict and the order was never actually changed in
# this file, so the finding sat unshipped for a whole run while the routing
# kept preferring the weaker model. It is corrected below: 001 now sits above
# 2, which is what MIGRATION's own rule - order by MEASURED recall - requires.
#
# What 2 keeps is a bigger input limit, 8,192 tokens against 001's 2,048. That
# does not bind at any chunk size we would choose (the cap is 510), so it does
# not buy back the ranking.
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

# Proven live 2026-08-27: 200, dim 3072 observed. PROMOTED ABOVE embedding-2 on
# 2026-09-18, because it beats it on our own fixture on 3 of the 4 corpora where
# both ran - see the note on GEMINI_EMBED_2. It is also the only model with
# perfect recall@5 on the original fixture (1.000, against codestral's 0.941).
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

# THE STRENGTH ORDER, RE-SORTED ON MEASUREMENT 2026-09-18 (slice 8 v3).
#
# It used to read codestral, BGE, mistral, google, cohere - which put the
# WEAKEST measured model third. Head to head, on the corpora where each pair
# both ran:
#
#     mistral vs gemini-001   n=7    mistral 1, google 6    0.503 vs 0.602
#     mistral vs cohere       n=13   mistral 3, cohere 10   0.511 vs 0.593
#     mistral vs gemini-2     n=11   mistral 4, google 7    0.537 vs 0.563
#
# mistral-embed loses to EVERY other embedder it has been compared with, so it
# moves to the back. Measured mean MRR over the 20-corpus zoo:
#
#     codestral 0.634 > gemini-001 0.602 > cohere 0.593 > gemini-2 0.563
#                     > mistral 0.511
#
# COHERE IS NO LONGER LAST, and the reason it was has weakened. Its quota is a
# real cost - 1,000 calls a MONTH shared with reranking - but it is BILLED PER
# CALL at up to 96 texts, so a small corpus is a handful of calls. The models
# that genuinely cannot finish a large ingest now say so through
# `daily_text_budget`, which is where a hard limit belongs; an ordering is for
# strength.
#
# Two structural overrides remain, and both are deliberate:
#   - BGE sits second because it is the only early entry on a DIFFERENT
#     platform. codestral and mistral-embed share one API key, so a Mistral
#     outage would otherwise take the top two. It is also the one model in this
#     list NOBODY HAS EVER SCORED - on any corpus, in v2 or v3 - so position 2
#     is a robustness argument, not a recall one.
#   - mistral-embed stays IN the list despite being last on quality, because it
#     is the only model that can ingest 10,000 chunks quickly: google cannot
#     today at all, and cohere is 21 minutes. A walk must not dead-end.
MIGRATION = (
    CODESTRAL_EMBED,
    BGE_BASE,
    GEMINI_EMBED_001,
    GEMINI_EMBED_001_KEY2,
    COHERE_EMBED,
    GEMINI_EMBED_2,
    GEMINI_EMBED_2_KEY2,
    MISTRAL_EMBED,
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

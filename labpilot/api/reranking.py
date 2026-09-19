"""The rerank chain, assembled where both adapters are visible.

`rerank/` may not import `llm/` - two adapters that know each other are welded
together and neither can be replaced - so LLM_RERANK_ORDER can only name its
tiers as STRINGS, and LLMReranker takes a `complete` callable instead of a
provider. This is the layer that closes that gap: entry is the only one
allowed to see both.

The ORDER is not ours. It stays in rerank/, measured on quora at a
30-document window against vector alone's MRR of 0.608 - so this module
supplies providers for names it does not choose, and
test_rerank_binding.py fails the build if a name has no provider.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence

from labpilot.llm import (
    GEMINI_3_1_FLASH_LITE,
    GEMINI_3_5_FLASH_LITE,
    GEMMA_4_26B,
    GEMMA_4_31B,
    GeminiProvider,
)
from labpilot.llm.registry import GOOGLE_KEYS
from labpilot.rerank import (
    JEV_RERANK,
    LLM_RERANK_ORDER,
    RERANK_CHAIN,
    LLMReranker,
    Ranking,
    Reranker,
    rerank,
)

# HOW A GEMINI MODEL MUST BE CONFIGURED FOR RANKING, and it is worth more than
# the choice of model. Measured 2026-09-11, same model and same corpus:
#
#     gemini-3.5-flash-lite  TUNED    MRR 0.799
#     gemini-3.5-flash-lite  UNTUNED  MRR 0.706
#
# 0.093 apart - a wider gap than between flash-lite and Cohere's purpose-built
# cross-encoder. Both settings were measured:
#
#   thinking=None    every Gemini tier ships MEDIUM, which on a RANKING task
#                    cost 3x the latency and 930 thought tokens for an
#                    IDENTICAL 109-token answer.
#   a JSON schema    gemma went 45.5s -> 14.4s, and the reply stopped being
#                    prose wrapped around an answer.
# The SECOND Google account. Google bills per project per model, so this is
# a whole extra allowance of every model, not a spare key.
SECOND_KEY = GOOGLE_KEYS[1]

RANKING_CONFIG = {
    "thinking": None,
    "generation_config": {
        "responseMimeType": "application/json",
        "responseSchema": {"type": "ARRAY", "items": {"type": "INTEGER"}},
    },
}

PROVIDERS = {
    provider.model: provider
    for provider in (
        GEMINI_3_5_FLASH_LITE,
        GEMINI_3_1_FLASH_LITE,
        GEMMA_4_26B,
        GEMMA_4_31B,
    )
}


def _listwise(provider: GeminiProvider) -> LLMReranker:
    """One tier, re-configured for ranking and wrapped in a plain callable.

    A FACTORY and not a loop body, deliberately. Building the lambda inline in
    a comprehension would close over the loop variable, so every tier would end
    up calling the LAST provider - and each one would still report its own name,
    which is the kind of failure that reads as a bad model.
    """
    tuned = dataclasses.replace(provider, **RANKING_CONFIG)

    return LLMReranker(
        complete=lambda prompt, budget: tuned.complete(prompt, max_tokens=budget).text,
        name=tuned.name,
        model=tuned.model,
    )


def _both_accounts(provider: GeminiProvider) -> tuple[LLMReranker, ...]:
    """The tier, then THE SAME MODEL ON THE SECOND ACCOUNT.

    ADDED 2026-09-19, and it was a real hole. Google bills per PROJECT per
    MODEL, so a second account is a second full allowance of every model - the
    generator chain has used both keys since 2026-09-11 and this one never did.
    All four LLM rerank tiers sat on GOOGLE_API_KEY alone, so the rerank path
    had HALF the budget it could have.

    It was found by running into it: measuring RERANK_TOP_N, the chain refused
    with `GenerateRequestsPerDayPerProjectPerModel-FreeTier, limit: 500` while
    the identical model answered 200 on the other key.

    ADJACENT on purpose, exactly as in the generator chain. A spent pool is
    skipped for free, so the strongest thing still available after flash-lite
    runs out is flash-lite on the other account - not a weaker model.
    """
    twin = dataclasses.replace(
        provider,
        name=f"{provider.name} (key 2)",
        api_key_env=SECOND_KEY,
        quota_pool=f"{SECOND_KEY}:{provider.model}",
    )
    return (_listwise(provider), _listwise(twin))


# The four LLM tiers BEAT every purpose-built cross-encoder measured, so they
# lead - eight entries, because each one is built on BOTH Google accounts.
# RERANK_CHAIN follows, and since 2026-09-19 every tier in it is measured ABOVE
# vector alone: bge-reranker-base was deleted rather than reordered, on v1's F6
# condition, so the chain no longer ends in something worse than not reranking.
# It still ends in skip(), which is what "no reranker was available" means.
#
# ELEVEN tiers, with Cohere at 9. That is the budget half of v2's G20: Cohere
# never hurt a corpus and repairs flash-lite's worst case, so it belongs early
# among the CROSS-ENCODERS - and it is 1,000 calls a MONTH against flash-lite's
# 1,000 a day across two keys, so it belongs behind every LLM tier.
# JEV SITS THIRD, AND THE THIRD IS DELIBERATE - it was asked for second.
#
# Position 2 is flash-lite ON THE SECOND GOOGLE ACCOUNT: the same model, a
# separate free allowance. Putting a PAID tier between two keys of one free
# model would spend money before spending an allowance we already have, and
# it would break the reason `_both_accounts` keeps the twins adjacent. So
# "the second option" and "the third tier" are the same place here: after
# flash-lite, both keys, and ahead of everything else.
#
# The measurement says third and nothing stronger. Two corpora, 30-document
# window, against vector alone:
#
#                          quora        geo        wins
#   gemini-3.5-flash-lite  0.799      0.681         quora
#   JEV                    0.770      0.712         geo
#
# One each, means 0.740 and 0.741 - indistinguishable. Jev is the steadier of
# the two and wins the corpus with real headroom; flash-lite leads on budget,
# which is this project's own tie-break (it is why Cohere sits above Voyage).
# Below them, Jev beats every remaining tier on every corpus measured.
#
# IT IS THE FIRST NON-GOOGLE TIER, and that is worth as much as the ranking.
# Eight of the eleven tiers here are Google, and this project has already lost
# every Google endpoint for a week to a refused VPN exit. When that happens
# the rerank chain falls to Cohere's 1,000 a MONTH and a Voyage that cannot
# take a 50-document window. Jev is the only independent capacity in it.
#
# IT IS ALSO THE FIRST PAID TIER IN ANY CHAIN HERE. If the balance runs out it
# answers 402, the chain moves on, and the cost is one wasted request - the
# same shape as a spent pool. See rerank/jev.py for the billing detail.
LEAD_MODEL, *REMAINING_MODELS = LLM_RERANK_ORDER

CHAIN: tuple[Reranker, ...] = (
    *_both_accounts(PROVIDERS[LEAD_MODEL]),
    JEV_RERANK,
    *(tier for model in REMAINING_MODELS for tier in _both_accounts(PROVIDERS[model])),
    *RERANK_CHAIN,
)


def rank(query: str, documents: Sequence[str], *, top_n: int | None = None) -> Ranking:
    """The chain the ask path actually uses."""
    return rerank(query, documents, chain=CHAIN, top_n=top_n)

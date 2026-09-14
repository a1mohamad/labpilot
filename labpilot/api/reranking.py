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
from labpilot.rerank import (
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


# The four LLM tiers BEAT every purpose-built cross-encoder measured, so they
# lead. RERANK_CHAIN follows, and its last tier (bge-reranker-base, 0.520) is
# below vector alone at 0.608 - kept only because one saturated corpus is thin
# evidence and its budget cannot run out. Slice 8 decides whether to delete it.
CHAIN: tuple[Reranker, ...] = (
    tuple(_listwise(PROVIDERS[model]) for model in LLM_RERANK_ORDER) + RERANK_CHAIN
)


def rank(query: str, documents: Sequence[str], *, top_n: int | None = None) -> Ranking:
    """The chain the ask path actually uses."""
    return rerank(query, documents, chain=CHAIN, top_n=top_n)

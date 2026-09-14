"""Every LLM reranker tier must have a provider something can actually build.

WHY THIS EXISTS
===============
`rerank/` is an adapter and `llm/` is an adapter, so rerank/ may not import
llm/ - test_architecture holds that line. The consequence is that
LLM_RERANK_ORDER can only name its four tiers as STRINGS, and a string cannot
be checked by the package that holds it.

So the four best rerankers in the project are named in one package and built in
another, with nothing joining the two. That gap was real, not theoretical:
`gemma-4-26b-a4b-it` was named in LLM_RERANK_ORDER, measured second best of
everything slice 6 scored, and had NO provider in llm/registry.py at all. It
existed only as a dataclasses.replace inside tests/smoke/, so the one place it
could be used was the weekly smoke run.

Nothing failed. The suite stayed green, both ruff commands stayed green, and
the binding step simply could not have been written. Same shape as the
`__all__` bug that test_public_api exists for: a name promised in one file and
absent from another, where the only symptom is a feature nobody can build.

The providers are deliberately NOT read from CHAIN. A reranker does not have to
be a generator tier - GEMMA_4_26B is not one, and putting it in CHAIN would be
a separate decision needing evidence this project does not have. So the check
reads the registry MODULE, which is where a provider really lives.
"""

from __future__ import annotations

import pytest

from labpilot.llm import registry
from labpilot.llm.gemini import GeminiProvider
from labpilot.llm.openai_compatible import OpenAICompatibleProvider
from labpilot.rerank import LLM_RERANK_ORDER

PROVIDERS = (GeminiProvider, OpenAICompatibleProvider)


def _models_llm_can_serve() -> dict[str, str]:
    """model id -> the registry name that holds it."""
    return {
        value.model: name
        for name, value in vars(registry).items()
        if isinstance(value, PROVIDERS)
    }


@pytest.mark.parametrize("model", LLM_RERANK_ORDER)
def test_every_llm_rerank_tier_has_a_provider_in_the_llm_registry(model):
    served = _models_llm_can_serve()

    assert model in served, (
        f"rerank/LLM_RERANK_ORDER names {model!r}, but no provider in "
        f"labpilot/llm/registry.py serves that model, so the entry layer "
        f"cannot build an LLMReranker for it and the tier is unreachable. "
        f"llm/ serves: {sorted(served)}"
    )

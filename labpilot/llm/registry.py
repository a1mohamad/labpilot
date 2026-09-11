from __future__ import annotations

import dataclasses

from labpilot.llm.gemini import GeminiProvider
from labpilot.llm.openai_compatible import OpenAICompatibleProvider

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GOOGLE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
CLOUDFLARE_URL = (
    "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/chat/completions"
)

MISTRAL_REASONING: dict[str, object] = {"reasoning_effort": "high", "top_p": 1}
OPENROUTER_REASONING: dict[str, object] = {"reasoning": {"effort": "high"}}
OPENAI_REASONING: dict[str, object] = {"reasoning_effort": "high"}

GOOGLE_CONTEXT = 1_048_576
GOOGLE_OUTPUT = 65_536


# A SECOND Google account, and it is a second quota rather than a spare key.
# Google bills per PROJECT per MODEL - the 429 body says
# GenerateRequestsPerDayPerProjectPerModel-FreeTier - so every model gets a
# fresh daily allowance on the second key: another 20/day per Flash model,
# another 500 per Flash-Lite, another 14,400 per Gemma.
#
# That is why `quota_pool` has to carry the KEY as well as the model. The pool
# is what runs out; the key is only how we authenticate. Collapsing them would
# mark BOTH accounts dead the first time either one is spent - the exact
# mistake quota_pool was created to fix on 2026-08-16, one level up.
GOOGLE_KEYS = ("GOOGLE_API_KEY", "GOOGLE_API_KEY_2")


def _gemini(
    *,
    name: str,
    model: str,
    tier: int = 0,
    api_key_env: str = GOOGLE_KEYS[0],
    context_window: int = GOOGLE_CONTEXT,
    max_output_tokens: int = GOOGLE_OUTPUT,
    max_input_tokens: int | None = None,
    thinking: str | None = "MEDIUM",
) -> GeminiProvider:
    return GeminiProvider(
        name=name,
        tier=tier,
        url=GOOGLE_URL,
        model=model,
        api_key_env=api_key_env,
        quota_pool=f"{api_key_env}:{model}",
        context_window=context_window,
        max_output_tokens=max_output_tokens,
        max_input_tokens=max_input_tokens,
        thinking=thinking,
    )


def _second_account(provider: GeminiProvider) -> GeminiProvider:
    """The same model on the other key, as its own tier with its own pool."""
    return dataclasses.replace(
        provider,
        name=f"{provider.name} (key 2)",
        api_key_env=GOOGLE_KEYS[1],
        quota_pool=f"{GOOGLE_KEYS[1]}:{provider.model}",
    )


GEMINI_3_7_FLASH = _gemini(name="Gemini 3.7 Flash", model="gemini-3.7-flash")
GEMINI_3_6_FLASH = _gemini(name="Gemini 3.6 Flash", model="gemini-3.6-flash")
GEMINI_3_5_FLASH = _gemini(name="Gemini 3.5 Flash", model="gemini-3.5-flash")

GLM_5_2 = OpenAICompatibleProvider(
    name="GLM-5.2",
    tier=4,
    url=MISTRAL_URL,
    model="glm-5-2",
    api_key_env="MISTRAL_API_KEY",
    context_window=1_048_576,
    max_output_tokens=1_048_576,
    extra_body=MISTRAL_REASONING,
)

NEMOTRON_3_ULTRA = OpenAICompatibleProvider(
    name="Nemotron 3 Ultra",
    tier=5,
    url=OPENROUTER_URL,
    model="nvidia/nemotron-3-ultra-550b-a55b:free",
    api_key_env="OPENROUTER_API_KEY",
    context_window=1_000_000,
    max_output_tokens=65_536,
    extra_body=OPENROUTER_REASONING,
)

GEMINI_3_5_FLASH_LITE = _gemini(
    name="Gemini 3.5 Flash-Lite", model="gemini-3.5-flash-lite"
)

MISTRAL_MEDIUM = OpenAICompatibleProvider(
    name="Mistral Medium",
    tier=7,
    url=MISTRAL_URL,
    model="mistral-medium-latest",
    api_key_env="MISTRAL_API_KEY",
    context_window=262_144,
    max_output_tokens=262_144,
    extra_body=MISTRAL_REASONING,
)

GEMINI_3_1_FLASH_LITE = _gemini(
    name="Gemini 3.1 Flash-Lite", model="gemini-3.1-flash-lite"
)

NEMOTRON_3_SUPER = OpenAICompatibleProvider(
    name="Nemotron 3 Super",
    tier=10,
    url=OPENROUTER_URL,
    model="nvidia/nemotron-3-super-120b-a12b:free",
    api_key_env="OPENROUTER_API_KEY",
    context_window=262_144,
    max_output_tokens=262_144,
    extra_body=OPENROUTER_REASONING,
)

GPT_OSS_120B = OpenAICompatibleProvider(
    name="GPT-OSS 120B",
    tier=11,
    url=CLOUDFLARE_URL,
    model="@cf/openai/gpt-oss-120b",
    api_key_env="CLOUDFLARE_API_KEY",
    account_env="CLOUDFLARE_ACCOUNT_ID",
    context_window=128_000,
    max_output_tokens=128_000,
    extra_body=OPENAI_REASONING,
)

MAGISTRAL_SMALL = OpenAICompatibleProvider(
    name="Magistral Small",
    tier=13,
    url=MISTRAL_URL,
    model="magistral-small-latest",
    api_key_env="MISTRAL_API_KEY",
    context_window=262_144,
    max_output_tokens=262_144,
    extra_body=MISTRAL_REASONING,
)

NORTH_MINI_CODE = OpenAICompatibleProvider(
    name="North Mini Code",
    tier=9,
    url=OPENROUTER_URL,
    model="cohere/north-mini-code:free",
    api_key_env="OPENROUTER_API_KEY",
    context_window=256_000,
    max_output_tokens=64_000,
    extra_body=OPENROUTER_REASONING,
)

DEVSTRAL_2 = OpenAICompatibleProvider(
    name="Devstral 2",
    tier=14,
    url=MISTRAL_URL,
    model="devstral-2512",
    api_key_env="MISTRAL_API_KEY",
    context_window=262_144,
    max_output_tokens=16_384,
)

# thinking=None is NOT a preference. Gemma answers HTTP 400 - "Thinking level
# is not supported for this model" - to every request that carries the field,
# so tier 8 was dead on every call, measured 2026-09-11. Removing the field
# makes it answer normally.
#
# This is the largest generator budget in the project - 14,400 requests a DAY,
# against 20/day for each Flash model - and CLAUDE.md's Step 2 routing leads
# both GATE_CHAIN and SUMMARY_CHAIN with it. So the cheapest, highest-volume
# tier had been broken since `thinking` was added in slice 4.
#
# The weekly smoke test DID cover it and DID fail. Nobody read the result. The
# guard worked; the reporting did not.
GEMMA_4_31B = _gemini(
    name="Gemma 4 31B",
    model="gemma-4-31b-it",
    context_window=262_144,
    max_output_tokens=32_768,
    max_input_tokens=16_000,
    thinking=None,
)

GPT_OSS_120B_GROQ = OpenAICompatibleProvider(
    name="GPT-OSS 120B (Groq)",
    tier=12,
    url=GROQ_URL,
    model="openai/gpt-oss-120b",
    api_key_env="GROQ_API_KEY",
    context_window=8_000,
    max_output_tokens=8_000,
    extra_body=OPENAI_REASONING,
)


def _ordered(*providers: GeminiProvider | OpenAICompatibleProvider):
    """Tier is the POSITION, never a number somebody typed.

    Reordering CHAIN without renumbering `tier=` was a real bug on 2026-08-11:
    the tuple was put in the right order while the fields kept their old
    values, so the chain read 2, 2, 3, 1, 4, 6 and only an invariant test
    noticed. Deriving it here makes that class of bug impossible rather than
    merely tested for.
    """
    return tuple(
        dataclasses.replace(provider, tier=position)
        for position, provider in enumerate(providers, 1)
    )


# Each Google model appears TWICE, on two accounts, adjacent. Adjacency is
# right here for the same reason the 2026-08-16 rewrite made it harmless: a
# spent pool is skipped for free, so the twin costs nothing when the first key
# still works and is the strongest available model when it does not. Ordering
# by capability then means "the same model on the other account" beats
# "a weaker model on this one".
CHAIN = _ordered(
    GEMINI_3_7_FLASH,
    _second_account(GEMINI_3_7_FLASH),
    GEMINI_3_6_FLASH,
    _second_account(GEMINI_3_6_FLASH),
    GEMINI_3_5_FLASH,
    _second_account(GEMINI_3_5_FLASH),
    GLM_5_2,
    NEMOTRON_3_ULTRA,
    GEMINI_3_5_FLASH_LITE,
    _second_account(GEMINI_3_5_FLASH_LITE),
    MISTRAL_MEDIUM,
    GEMMA_4_31B,
    _second_account(GEMMA_4_31B),
    NORTH_MINI_CODE,
    NEMOTRON_3_SUPER,
    GPT_OSS_120B,
    GPT_OSS_120B_GROQ,
    MAGISTRAL_SMALL,
    DEVSTRAL_2,
    GEMINI_3_1_FLASH_LITE,
    _second_account(GEMINI_3_1_FLASH_LITE),
)

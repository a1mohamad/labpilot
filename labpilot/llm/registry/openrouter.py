"""The tiers of Openrouter."""

from __future__ import annotations

from labpilot.llm.openai_compatible import OpenAICompatibleProvider
from labpilot.llm.registry._shared import OPENROUTER_REASONING

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


# MOVED OFF MISTRAL 2026-09-19, and the death there is now complete. This is
# the THIRD error shape from one model, each cleaner than the last:
#
#   2026-08-11   answered
#   2026-08-16   429 with x-ratelimit-limit-tokens-minute: 0  (not entitled)
#   2026-09-19   dropped from GET /v1/models ENTIRELY, and a direct call says
#                "This model is not available in your subscription tier"
#
# The wording matters: Mistral answers "Invalid model: glm-5.3" for something
# that does not exist, so GLM-5.2 still EXISTS there and is simply behind a
# paid tier. Not revivable for free on Mistral. Mistral's catalogue is also
# down from 55 models to 46.
#
# OpenRouter serves it free instead, measured 2026-09-19: 1 call in 4
# answered, the rest 429 `upstream_provider_shared_pool` - CONGESTION, which
# is a different failure from `limit: 0` and one the chain already retries.
# A tier that answers a quarter of the time strictly beats one that is dead.
#
# ⚠ 32,768 CONTEXT, so it can NEVER serve a report: PROMPT_BUDGET 30,000 plus
# REPORT_MAX_TOKENS 32,000 is 62,000. _check_fits refuses it locally for
# nothing, and it is here for Step 2's smaller jobs - where it is worth
# having, at Code Arena #19 (1592), ahead of Gemini 3.6 Flash.
GLM_5_2 = OpenAICompatibleProvider(
    name="GLM-5.2",
    tier=0,
    url=OPENROUTER_URL,
    model="z-ai/glm-5.2:free",
    api_key_env="OPENROUTER_API_KEY",
    context_window=32_768,
    max_output_tokens=29_491,
    extra_body=OPENROUTER_REASONING,
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


DEEPSEEK_V4_FLASH = OpenAICompatibleProvider(
    name="DeepSeek V4 Flash",
    tier=0,
    url=OPENROUTER_URL,
    model="deepseek/deepseek-v4-flash-0731:free",
    api_key_env="OPENROUTER_API_KEY",
    context_window=1_048_576,
    max_output_tokens=393_216,
    extra_body=OPENROUTER_REASONING,
)

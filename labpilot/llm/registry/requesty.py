"""The tiers of Requesty."""

from __future__ import annotations

from labpilot.llm.openai_compatible import OpenAICompatibleProvider
from labpilot.llm.registry._shared import OPENROUTER_REASONING

REQUESTY_URL = "https://router.requesty.ai/v1/chat/completions"


# REQUESTY — a third free route, INDEPENDENT of Google and OpenRouter.
#
# 200 requests a DAY, no card, no trial expiry. Its value is not new
# capability, it is INDEPENDENCE: a refused Google exit has already taken
# every Google tier from this project for a week, and Requesty serves Gemma
# and Nemotron without touching Google or OpenRouter.
#
# Measured 2026-09-19, 7 of its 12 free models answered. The five that did
# not are recorded so nobody re-adds them: ling-3.0-tiny 404, laguna-m.1 404,
# laguna-xs.2 404, nemotron-3-nano-30b-a3b 410 GONE, nemotron-3-super 503.
#
# It exposes NO usage or credits endpoint (both 404), so the remaining daily
# allowance cannot be read - the same blindness as Kilo and Cline.

# One request at a time for the whole organisation: three calls at the same moment
# gave one answer and two 429 "reached its limit of concurrent requests"
# (measured 2026-11-16, and the same message in both sittings).
REQUESTY_MAX_CONCURRENT = 1


def _requesty(
    *,
    name: str,
    model: str,
    context_window: int,
    max_output_tokens: int,
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name=name,
        tier=0,
        url=REQUESTY_URL,
        model=model,
        api_key_env="REQUESTY_API_KEY",
        # ONE pool: the 200/day is account-wide across every free model.
        quota_pool="REQUESTY_API_KEY",
        max_concurrent=REQUESTY_MAX_CONCURRENT,
        context_window=context_window,
        max_output_tokens=max_output_tokens,
        extra_body=OPENROUTER_REASONING,
    )


REQUESTY_GEMMA_4_31B = _requesty(
    name="Gemma 4 31B (Requesty)",
    model="google/gemma-4-31b-it",
    context_window=262_144,
    max_output_tokens=32_768,
)


REQUESTY_NEMOTRON_3_ULTRA = _requesty(
    name="Nemotron 3 Ultra (Requesty)",
    model="nvidia/nemotron-3-ultra-550b-a55b",
    context_window=1_000_000,
    max_output_tokens=65_536,
)


# NEW CAPABILITY, not a backup route. AA v4.3 = 18 at 91.3 tok/s, which sits
# between Gemini 3.5 Flash-Lite (23) and Gemma 4 31B (15). Live 2.3s.
REQUESTY_MUSE_GLIMMER = _requesty(
    name="Muse Glimmer 30B (Requesty)",
    model="nvidia/muse-glimmer-30b",
    context_window=262_144,
    max_output_tokens=32_768,
)


# The same Ling 3.1 Flash as on Kilo, second because Kilo allows 200 an HOUR and
# this is 200 a DAY. 2.3 s on 2026-11-02.
REQUESTY_LING_3_1_FLASH = _requesty(
    name="Ling 3.1 Flash (Requesty)",
    model="novita/ling-3.1-flash",
    context_window=262_144,
    max_output_tokens=32_768,
)

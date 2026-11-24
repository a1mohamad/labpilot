"""The tiers of Kilo."""

from __future__ import annotations

from labpilot.llm.openai_compatible import OpenAICompatibleProvider
from labpilot.llm.registry._shared import OPENROUTER_REASONING

KILO_URL = "https://api.kilo.ai/api/gateway/v1/chat/completions"


# KILO — A SECOND FREE ALLOWANCE FOR MODELS WE ALREADY REACH, added 2026-09-19.
#
# Kilo resells OpenRouter under its OWN org account, proven from the error
# body: ours reads `"user_id": "user_3HREb…"` and Kilo's `"user_id":
# "org_2uwFc…"`. Everything else in the two responses is byte-identical.
#
# THE CONSEQUENCE IS MEASURED, and it is the whole reason these tiers exist:
# three successful Kilo calls left our OpenRouter counter at 17 of 50. Kilo
# spends KILO's allowance. So when our OpenRouter day is gone, these still
# answer.
#
#     OpenRouter   50 requests per DAY      (our account)
#     Kilo        200 requests per HOUR     (per IP, their docs)
#
# One hour of Kilo is four times our whole OpenRouter day, which is why a
# Kilo route goes BEFORE its OpenRouter twin for the same model. That is this
# project's standing rule: rank different models by capability, and within
# ONE model prefer the provider with more usable quota.
#
# TWO CEILINGS, NEITHER OF THEM OURS, and both measured:
#   * 200/hour is per IP and we are on a SHARED VPN exit, so it is split with
#     everyone else on that address - the thing that made OVH unusable.
#   * a per-model daily cap on OpenRouter's shared capacity sits underneath.
#     inkling-small returned `limit_source: openrouter_shared_capacity`,
#     X-RateLimit-Limit 5000, Remaining 0, resetting at midnight UTC.
# Kilo returns NO rate-limit headers on a success and has no usage endpoint,
# so the remaining allowance cannot be read. Same blindness as Cline.
#
# A 429 here is CHEAP - measured 0.7-1.2s, not retryable, straight to the next
# tier. A spent OpenRouter day is not recoverable until tomorrow. That
# asymmetry is what makes "try Kilo first" safe even when Kilo is congested.
#
# The key is OPTIONAL: Kilo's docs say anonymous and authenticated free
# requests are rate-limited identically, by IP. It is sent for attribution.
def _kilo(
    *,
    name: str,
    model: str,
    context_window: int,
    max_output_tokens: int,
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name=name,
        tier=0,
        url=KILO_URL,
        model=model,
        api_key_env="KILO_API_KEY",
        # ONE pool for every Kilo tier: the 200/hour is per IP, shared across
        # all of them, so a 429 on one really does mean the rest are spent.
        quota_pool="KILO_API_KEY",
        context_window=context_window,
        max_output_tokens=max_output_tokens,
        extra_body=OPENROUTER_REASONING,
    )


# NOT HERE: z-ai/glm-5.3-flash. Kilo carries it and it is PAID there -
# $0.150/$0.500 per M - so it answered "Paid Model - Credits Required" and
# was a dead tier burning a request on every report. It was added by matching
# Cline's tier-1 MODEL ID against Kilo's CATALOGUE, which is the wrong list:
# the catalogue is what Kilo SERVES, the free list is what it serves for
# NOTHING. tests/smoke/test_gateway_tiers_are_free.py now pins that.
KILO_DEEPSEEK_V4_FLASH = _kilo(
    name="DeepSeek V4 Flash (Kilo)",
    model="deepseek/deepseek-v4-flash-0731:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)


KILO_QWEN_3_8_27B = _kilo(
    name="Qwen3.8 27B (Kilo)",
    model="qwen/qwen3.8-27b:free",
    context_window=262_144,
    max_output_tokens=235_929,
)


KILO_GLM_5_2 = _kilo(
    name="GLM-5.2 (Kilo)",
    model="z-ai/glm-5.2:free",
    context_window=32_768,
    max_output_tokens=29_491,
)


KILO_LAGUNA_S_2_1 = _kilo(
    name="Laguna S 2.1 (Kilo)",
    model="poolside/laguna-s-2.1:free",
    context_window=262_144,
    max_output_tokens=32_768,
)


KILO_NEMOTRON_3_ULTRA = _kilo(
    name="Nemotron 3 Ultra (Kilo)",
    model="nvidia/nemotron-3-ultra-550b-a55b:free",
    context_window=1_000_000,
    max_output_tokens=65_536,
)


KILO_NORTH_MINI_CODE = _kilo(
    name="North Mini Code (Kilo)",
    model="cohere/north-mini-code:free",
    context_window=256_000,
    max_output_tokens=64_000,
)


KILO_NEMOTRON_3_SUPER = _kilo(
    name="Nemotron 3 Super (Kilo)",
    model="nvidia/nemotron-3-super-120b-a12b:free",
    context_window=262_144,
    max_output_tokens=235_929,
)


# ADDED 2026-11-02. Ling 3.1 Flash is 41 on AA v4.3.2 (the comparison pages that
# use that index), a tie with Gemini 3.8 Flash and the fastest strong free model
# found: 2.0 s on Kilo, 2.3 s on Requesty. The catalogue id is the 1019 build;
# AA's current-index page for that build says 29 (v5.0), so the 41 rests on the
# older pages and the match between the two names is NOT proven.
KILO_LING_3_1_FLASH = _kilo(
    name="Ling 3.1 Flash (Kilo)",
    model="inclusionai/ling-3.1-flash-1019-free",
    context_window=1_000_000,
    max_output_tokens=262_144,
)


# UNSCORED (AA shows 6 to 24 depending on page), so it sits with the unscored
# tiers. 9.6 s on 2026-11-02.
KILO_NEMOTRON_3_5_LIGHTNING = _kilo(
    name="Nemotron 3.5 Lightning (Kilo)",
    model="nvidia/nemotron-3.5-lightning:free",
    context_window=1_000_000,
    max_output_tokens=65_536,
)


# AA v4.3 = 26 at 173.9 tok/s - ABOVE Gemini 3.5 Flash-Lite's 23, which is
# why it earns a slot at all. Code Arena is the caveat and it is a real one:
# 1407, rank #73, so it is a weak coder for a strong general score.
#
# ⚠ It was 429 when measured, and the reason is worth keeping: the refusal
# carried `limit_source: openrouter_shared_capacity`, X-RateLimit-Limit 5000,
# Remaining 0, resetting at midnight UTC. That is a per-model DAILY cap over
# every OpenRouter user, not our allowance - "Credits don't affect this cap".
#
# MEASURED AGAIN 2026-09-29/30, and it answered 429 on 6 of 6 calls in a
# 50-tier run (docs/step2/slice1/RESULTS.md). The raw refusal:
#   "Daily limit reached for thinkingmachines/inkling-small:free via Thinking
#    Machines"   X-RateLimit-Limit 1000, Remaining 0, reset 00:00 UTC
# THE CAP IS 1,000 REQUESTS A DAY FOR THE WHOLE WORLD, and it was gone by 18:29
# UTC. THERE IS NO SECOND FREE ROUTE, all four checked:
#   Cline        reaches the same OpenRouter counter (same
#                `limit_rpd/thinkingmachines/inkling-small-20260730` id, sent
#                back as an HTTP 500 wrapping the 429)
#   OpenRouter   403 "only available on agentic harnesses" - Kilo and Cline pass
#                that gate, we do not
#   Routeway, Requesty, and the paid Kilo/OpenRouter ids   PAID, $0.45-$1.87
#                per million input tokens - the no-card rule forbids them
# So it works only in the first hours of a UTC day, if at all. A 429 costs one
# 1.1s call and the chain moves on, so it is kept where its score puts it.
KILO_INKLING_SMALL = _kilo(
    name="Inkling Small (Kilo)",
    model="thinkingmachines/inkling-small:free",
    context_window=1_048_576,
    max_output_tokens=131_072,
)


# AA v4.3 = 19 at 152.1 tok/s, between Flash-Lite (23) and Gemma (15). The
# only free model Kilo serves that OpenRouter does not. Live 4.5s.
KILO_STEP_3_7_FLASH = _kilo(
    name="Step 3.7 Flash (Kilo)",
    model="stepfun/step-3.7-flash:free",
    context_window=262_144,
    max_output_tokens=65_536,
)

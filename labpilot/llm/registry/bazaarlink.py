"""The tiers of Bazaarlink."""

from __future__ import annotations

from labpilot.llm.openai_compatible import OpenAICompatibleProvider

BAZAARLINK_URL = "https://api.bazaarlink.ai/v1/chat/completions"


# BAZAARLINK - a free pool of its own, and a SMALL one. Probed 2026-10-18.
#
# Two free ids exist (GET /v1/models, price 0): qwen/qwen3.7-flash:free and
# deepseek/deepseek-v4-flash-0731free:free. The plain ids of both models are
# PAID, and the DeepSeek one is the 0731 snapshot, not plain V4 Flash.
#
# THE QUOTA IS THE WHOLE STORY. The docs say "60 requests a day" per free model,
# counted in UNITS that grow with the prompt. Measured: the account was refused
# after only 13 calls (about 70,000 prompt tokens, two of them 25K and 44K), with
# "daily limit of 60 free-model requests for your account, resets at 00:00 UTC".
# DeepSeek was refused at once after 3 small calls, so the pool looks
# ACCOUNT-WIDE and ONE quota_pool is used, as for Kilo and Requesty. The units
# per token are unknown.
#
# So both tiers are modelled for SMALL JOBS ONLY: max_output_tokens is 8,192, not
# a report's 32,000. _check_fits then turns a report away for free, instead of
# letting one report spend a third of the day. This is Groq's trick - model the
# limit that binds, not the one the vendor advertises - and the number is
# conservative, not measured: raise it once the units are calibrated.
#
# Measured: Qwen 3.7 Flash 3 of 3 whole answers in 2.7-3.0s, 2 of 2 valid tool
# calls, 3 of 3 valid JSON (json_object, strict json_schema, plain), and a needle
# found at 25,478 and at 43,828 real prompt tokens in 6.8s and 8.3s. DeepSeek
# 0731 free 3 of 3 whole answers in 5.6-12.2s with about 430 hidden reasoning
# tokens; its tools, JSON and big prompts are NOT tested yet (the quota ran out).
# Neither model has an Artificial Analysis score, so both sit in the unscored
# group: no evidence, no promotion.
#
# SAFETY NET: past the free quota, an account with a POSITIVE balance is billed
# at the paid price. `X-Free-Fallback: false` turns that into a 429. The balance
# is $0 today, so it is a net and not a fix, and a test pins it on every tier.
#
# No `extra_body`: whether a reasoning field is accepted is untested, and an
# unlisted field is a guess. Qwen spends no reasoning tokens by default.
BAZAARLINK_NO_PAID_FALLBACK: dict[str, str] = {"X-Free-Fallback": "false"}


BAZAARLINK_MAX_OUTPUT = 8_192


def _bazaarlink(
    *, name: str, model: str, context_window: int
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name=name,
        tier=0,
        url=BAZAARLINK_URL,
        model=model,
        api_key_env="BAZAARLINK_API_KEY",
        # ONE pool: the daily quota is account-wide (see above).
        quota_pool="BAZAARLINK_API_KEY",
        context_window=context_window,
        max_output_tokens=BAZAARLINK_MAX_OUTPUT,
        extra_headers=BAZAARLINK_NO_PAID_FALLBACK,
    )


# The windows are the catalogue's own numbers. Qwen took 43,828 real tokens.
BAZAARLINK_QWEN_3_7_FLASH = _bazaarlink(
    name="Qwen 3.7 Flash (Bazaarlink)",
    model="qwen/qwen3.7-flash:free",
    context_window=1_000_000,
)


BAZAARLINK_DEEPSEEK_V4_FLASH_0731 = _bazaarlink(
    name="DeepSeek V4 Flash 0731 (Bazaarlink)",
    model="deepseek/deepseek-v4-flash-0731free:free",
    context_window=1_048_576,
)

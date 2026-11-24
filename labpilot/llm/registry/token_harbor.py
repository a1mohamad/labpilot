"""The tiers of Token Harbor."""

from __future__ import annotations

from labpilot.llm.openai_compatible import OpenAICompatibleProvider

# TOKEN HARBOR - four free models, probed and read from its own pages 2026-11-16.
#
# THE KEY IS `TOKEN_HARBOR_API_KEY` (the old .env.example said TOKEN_HARBOR_API,
# a revoked key). Base https://tokenharbor.ai/v1, OpenAI-compatible.
#
# MEASURED: 20 calls (4 free models x 5, no retry, 120 s cap) answered 20 of 20,
# every one `finish_reason=stop`, 2.8 to 7.3 s. That is ONE day. The old note
# (2026-09-23) measured 8 of 20 rounds, with failures that are a HANG and
# time-correlated, so these tiers carry a 120 s read cap (a hang must not spend
# the 600 s default) and the rule of NOT_TRUSTED applies: a tier that answers
# sometimes and fails sometimes moves there. Re-test on another day.
#
# THE LIMITS (the provider's own FAQ):
#   * 60 requests a minute and 1,800 an hour per ACCOUNT, shared by every key and
#     every model; 100 and 3,000 per IP. No limit on concurrent requests.
#   * The free quota is a VALUE-based allowance on a rolling 7-day period that
#     starts at the first free request. Its size is NOT published; the dashboard
#     shows a percentage, and every reply carries `x-th-free-used-pct` and
#     `x-th-free-resets`. When it is spent, free routes stop (an HTTP error).
#     ONE pool, because the allowance is account-wide.
#   * 4 MB per request on a free account (413 above it).
#   * PRIVACY: on free routes the staff may read the conversations and the
#     providers that serve them may train on them. LabPilot sends users' code, so
#     these tiers are SMALL JOBS only.
#
# So max_output_tokens is a DELIBERATE 16,384, like Hy4: the allowance size is
# unknown, a report would spend much of it, and the privacy rule above argues
# against sending a whole pair. A local guard, not a measured limit.
#
# `extra_body` is not set: whether a reasoning field is accepted is untested.
TOKEN_HARBOR_URL = "https://tokenharbor.ai/v1/chat/completions"


TOKEN_HARBOR_MAX_OUTPUT = 16_384


TOKEN_HARBOR_TIMEOUT = (10.0, 120.0)


# 60 requests a minute for the whole account (its own FAQ), and NO limit on how
# many are open at once, so max_concurrent stays None.
TOKEN_HARBOR_REQUESTS_PER_MINUTE = 60


def _token_harbor(
    *, name: str, model: str, context_window: int
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name=name,
        tier=0,
        url=TOKEN_HARBOR_URL,
        model=model,
        api_key_env="TOKEN_HARBOR_API_KEY",
        # ONE pool: the 7-day allowance and the 60-a-minute limit are account-wide.
        quota_pool="TOKEN_HARBOR_API_KEY",
        allowance_header="x-th-free-used-pct",
        allowance_reset_header="x-th-free-resets",
        stream_usage=False,
        requests_per_minute=TOKEN_HARBOR_REQUESTS_PER_MINUTE,
        context_window=context_window,
        max_output_tokens=TOKEN_HARBOR_MAX_OUTPUT,
        timeout=TOKEN_HARBOR_TIMEOUT,
    )


# Windows are the catalogue's own numbers. DeepSeek V4.1 Flash is AA v4.3.2 = 39
# and DeepSeek V4 Flash 34 (the families LiteRouter already carries), MiMo V2.6
# Flash 27 on the v5.0.1 chart; MiMo V2.5 has no score.
TOKEN_HARBOR_DEEPSEEK_V4_1_FLASH = _token_harbor(
    name="DeepSeek V4.1 Flash (Token Harbor)",
    model="deepseek-v4.1-flash:free",
    context_window=1_048_576,
)


TOKEN_HARBOR_DEEPSEEK_V4_FLASH = _token_harbor(
    name="DeepSeek V4 Flash (Token Harbor)",
    model="deepseek-v4-flash:free",
    context_window=1_000_000,
)


TOKEN_HARBOR_MIMO_V2_6_FLASH = _token_harbor(
    name="MiMo V2.6 Flash (Token Harbor)",
    model="mimo-v2.6-flash:free",
    context_window=1_048_576,
)


TOKEN_HARBOR_MIMO_V2_5 = _token_harbor(
    name="MiMo V2.5 (Token Harbor)",
    model="mimo-v2.5:free",
    context_window=1_048_576,
)

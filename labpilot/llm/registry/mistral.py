"""The tiers of Mistral."""

from __future__ import annotations

from labpilot.llm.openai_compatible import OpenAICompatibleProvider

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"


MISTRAL_REASONING: dict[str, object] = {"reasoning_effort": "high", "top_p": 1}


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


DEVSTRAL_2 = OpenAICompatibleProvider(
    name="Devstral 2",
    tier=14,
    url=MISTRAL_URL,
    model="devstral-2512",
    api_key_env="MISTRAL_API_KEY",
    context_window=262_144,
    max_output_tokens=16_384,
)


# ADDED 2026-10-23: the free Mistral text models that ANSWER on this account and
# were not in the chain (one live call to every text model on 2026-10-22; the
# console page lists more than the account may call). UNSCORED - no independent
# score was looked up for any of them - so they sit below the measured Gemma
# 4 31B. The only evidence is the quick size test of 2026-10-22, a PROXY (list
# every named constant in 90K tokens of code, cut into parts of 12K):
#
#                   recall   seconds   invented names
#   Ministral 8B     .91       22          15
#   Mistral Nemo     .90       22          12
#   Ministral 14B    .84       42           7
#
# Good recall and fast, but they INVENT names, so a claims chain may use them
# only behind a quote check (CLAUDE.md section 23, D69, not built yet). The 14B
# is the weakest of the three: a timeout on the whole text, a lost part at 28K,
# and only 30 calls a minute. Ministral 3B (recall .50) and Codestral (.79)
# were left out on purpose.
#
# A DELIBERATE output cap of 8,192, like Bazaarlink's: a local guard, not a
# measured limit, so _check_fits turns a report away for free. These models
# must not write a report, and claims are short.
#
# NOT reasoning models (the catalogue says reasoning: false), so no reasoning
# field. ONE POOL PER MODEL: Mistral's console shows its per-minute limits per
# model. The account's monthly cap, if it binds, takes all of them at once.
MISTRAL_SMALL_MAX_OUTPUT = 8_192


# 2 requests and 40,000 tokens a minute for EACH model (headers
# x-ratelimit-limit-req-minute: 2, measured 2026-11-16). The old 30 to 750 a minute
# came from the console page and was wrong. Mistral Nemo is Ministral 8B: every
# answer says ministral-8b-2512 and it shares that bucket, so it shares the pool.
MISTRAL_SMALL_REQUESTS_PER_MINUTE = 2


def _mistral_small(
    *, name: str, model: str, context_window: int, pool_model: str | None = None
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name=name,
        tier=0,
        url=MISTRAL_URL,
        model=model,
        api_key_env="MISTRAL_API_KEY",
        quota_pool=f"MISTRAL_API_KEY:{pool_model or model}",
        requests_per_minute=MISTRAL_SMALL_REQUESTS_PER_MINUTE,
        context_window=context_window,
        max_output_tokens=MISTRAL_SMALL_MAX_OUTPUT,
    )


MINISTRAL_8B = _mistral_small(
    name="Ministral 8B", model="ministral-8b-2512", context_window=262_144
)


MISTRAL_NEMO = _mistral_small(
    name="Mistral Nemo",
    model="open-mistral-nemo",
    context_window=128_000,
    pool_model=MINISTRAL_8B.model,
)


MINISTRAL_14B = _mistral_small(
    name="Ministral 14B", model="ministral-14b-2512", context_window=262_144
)


# ADDED 2026-11-02 (answered in 2.3 s on the live catalogue check; the size test
# above gave recall .79 and 16 invented names, the reason it was left out on
# 2026-10-23). UNSCORED and small jobs only, like the three above.
CODESTRAL = _mistral_small(
    name="Codestral", model="codestral-2508", context_window=256_000
)

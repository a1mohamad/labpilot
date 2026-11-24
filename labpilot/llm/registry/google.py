"""The tiers of Google."""

from __future__ import annotations

import dataclasses

from labpilot.llm.gemini import GeminiProvider

GOOGLE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


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
#
# A THIRD account was added 2026-10-22. Proven live the same day: a 14,800-token
# prompt on Gemma 4 31B was accepted on keys 2 and 3 at the same moment, so each
# key is its own room (key x model). Three accounts driven from one VPN exit is
# the pattern that got an account flagged on 2026-08-11, so do not add a fourth
# without a decision.
GOOGLE_KEYS = ("GOOGLE_API_KEY", "GOOGLE_API_KEY_2", "GOOGLE_API_KEY_3")


# Both Gemma models take 30 requests a minute for each (key, model), read from the
# AI Studio rate-limit page. The 16,000 input tokens a minute are max_input_tokens.
GEMMA_REQUESTS_PER_MINUTE = 30


def _gemini(
    *,
    name: str,
    model: str,
    tier: int = 0,
    api_key_env: str = GOOGLE_KEYS[0],
    context_window: int = GOOGLE_CONTEXT,
    max_output_tokens: int = GOOGLE_OUTPUT,
    max_input_tokens: int | None = None,
    requests_per_minute: int | None = None,
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
        requests_per_minute=requests_per_minute,
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


def _third_account(provider: GeminiProvider) -> GeminiProvider:
    """The same model on the third key: its own tier, its own pool."""
    return dataclasses.replace(
        provider,
        name=f"{provider.name} (key 3)",
        api_key_env=GOOGLE_KEYS[2],
        quota_pool=f"{GOOGLE_KEYS[2]}:{provider.model}",
    )


def _other_accounts(provider: GeminiProvider) -> tuple[GeminiProvider, ...]:
    """The same model on every account after the first, in key order."""
    return (_second_account(provider), _third_account(provider))


# ADDED 2026-09-19. AA v4.3 = 41 at 297.8 tok/s, which puts it SECOND -
# between GLM-5.3 Flash (42) and Gemini 3.7 Flash (39) - and it is free on the
# key this project already holds, so it cost nothing to reach.
#
# Code Arena is the caveat, and it repeats a pattern: 1568 (#23) puts it BELOW
# Qwen3.8-27B's 1593 and DeepSeek's 1580 despite a higher general score. It is
# the strongest GENERAL tier after tier 1, not the strongest coder.
#
# ITS FREE QUOTA IS UNVERIFIED. Do NOT assume 3.7's 20/day - Google publishes
# limits per model and this one is new. Read AI Studio before budgeting on it.
GEMINI_3_8_FLASH = _gemini(name="Gemini 3.8 Flash", model="gemini-3.8-flash")


# Gemini 4 Hydrogen (2026-11-17, 31.21): AA v5.0.1 51 at "high" against 31 for
# Gemini 3.8 Flash. 20 requests a day for each key (the AI Studio panel), 29 to
# 117 s for a one-line answer, 503 "high demand" on about 4 requests of 9. No
# thinking level is sent: the model thinks by itself. Argon, Carbon and Neon
# answer 429 (limit 0) on this account. The window and output cap are Google's
# own figures for this model (GET /v1beta/models, 2026-11-20).
GEMINI_4_HYDROGEN = _gemini(
    name="Gemini 4 Hydrogen", model="gemini-4-hydrogen", thinking=None
)


GEMINI_3_7_FLASH = _gemini(name="Gemini 3.7 Flash", model="gemini-3.7-flash")


GEMINI_3_6_FLASH = _gemini(name="Gemini 3.6 Flash", model="gemini-3.6-flash")


GEMINI_3_5_FLASH = _gemini(name="Gemini 3.5 Flash", model="gemini-3.5-flash")


GEMINI_3_5_FLASH_LITE = _gemini(
    name="Gemini 3.5 Flash-Lite", model="gemini-3.5-flash-lite", requests_per_minute=15
)


GEMINI_3_1_FLASH_LITE = _gemini(
    name="Gemini 3.1 Flash-Lite", model="gemini-3.1-flash-lite", requests_per_minute=15
)


# thinking=None is NOT a preference. Gemma answers HTTP 400 - "Thinking level
# is not supported for this model" - to a request that carries MEDIUM (the level
# every Gemini tier here shipped with), so tier 8 was dead on every call,
# measured 2026-09-11. Removing the field makes it answer normally.
#
# ⚠ CORRECTED 2026-09-30: that note used to say "every request that carries the
# field", and it is not true. Gemma accepts TWO levels, MINIMAL and HIGH, and
# refuses LOW, MEDIUM and thinkingBudget 0. See the measurements below.
#
# This is the largest generator budget in the project - 14,400 requests a DAY,
# against 20/day for each Flash model - and CLAUDE.md's Step 2 routing leads
# both GATE_CHAIN and SUMMARY_CHAIN with it. So the cheapest, highest-volume
# tier had been broken since `thinking` was added in slice 4.
#
# The weekly smoke test DID cover it and DID fail. Nobody read the result. The
# guard worked; the reporting did not.
#
# WHY IT IS SLOW, measured 2026-09-30 - and it is NOT a bug of ours. Streaming a
# 30-token answer showed the wait comes BEFORE the first token:
#   Gemini 3.5 Flash-Lite   first token 1.7s   total 1.7s
#   Gemma 4 31B             first token 38.5s  first answer 44.6s  total 45.0s
# then it writes fast. Three more facts:
#   * it THINKS BY DEFAULT - 166-207 hidden tokens for a 38-token answer, ~1,000
#     for a 500-token one. `thinkingLevel: MINIMAL` IS ACCEPTED and writes NO
#     hidden tokens; HIGH is accepted too. LOW, MEDIUM and thinkingBudget 0 answer
#     400 "not supported for this model". On the 26B below, MINIMAL took the same
#     job from 7.1s to 2.5s, 3 of 3 times. On this 31B the wait is the QUEUE, so
#     MINIMAL saved little (28-31s against 40s)
#   * about half the calls answered 500 "Internal error encountered" or 503: 5 of
#     7 valid calls in one direct test, 5 of 12 in the 300-request latency run
#   * "small" is misleading: this is a DENSE 31B model. The 26B A4B below answered
#     the same job in 7.3s, twice, with no error
# Routeway's six 26B finetunes are slow for a different reason: 22 tokens a second
# for a model with ~4B active parameters is their host, not the model.
GEMMA_4_31B = _gemini(
    name="Gemma 4 31B",
    model="gemma-4-31b-it",
    context_window=262_144,
    max_output_tokens=32_768,
    max_input_tokens=16_000,
    requests_per_minute=GEMMA_REQUESTS_PER_MINUTE,
    thinking=None,
)


# NOT IN CHAIN, and that is exactly why it is here.
#
# This is a RERANKER. Slice 6 measured it second best of everything scored -
# MRR 0.732, and r@1 0.647 which is the BEST first-position score of the four
# LLM tiers - and rerank/LLM_RERANK_ORDER names it. But rerank/ is an adapter
# and may not import llm/, so the object must be built by a layer that may see
# both, and it must EXIST somewhere production can reach.
#
# It did not. It lived in tests/smoke/test_rerankers.py as a dataclasses.replace
# of the 31B, so the second-best reranker in the project was reachable only by
# the weekly smoke run. Moving it here is the whole fix; the smoke test now
# imports it instead of rebuilding it, so the two cannot drift apart.
#
# THE LIMITS ARE MEASURED, not inherited on faith. GET /v1beta/models reports
# inputTokenLimit 262,144 and outputTokenLimit 32,768 - identical to the 31B,
# which is what the smoke test had assumed. The 16,000 max_input_tokens is a
# different limit: the per-minute input quota, 16K TPM for BOTH Gemma models.
#
# Google bills per project per MODEL, so this carries its OWN 14,400 requests a
# day on top of the 31B's. It is also the faster of the two - 18.7s against
# 22.8s on a 30-document ranking - though far less than its ~3.8B active
# parameters suggest, because the bottleneck is Google's serving of these
# models and not their size.
#
# IN CHAIN SINCE 2026-09-30, as a GENERATOR, on the user's decision. The evidence
# was about SPEED and reliability, not capability: on Google it answered a
# 30-token job in 7.3s twice with no error, against 28-45s and 500s for the 31B
# (first token at 2.0s against 38.5s). Stock Gemma 4 26B A4B is 17 on AA v4.3.2
# against the 31B's 15, so it is not weaker on the one number we have, and it has
# its own 14,400 requests a day. It sits BETWEEN Muse Glimmer (18) and the 31B.
#
# `thinking="MINIMAL"` is what makes it worth having: it answered a 30-token job
# in 2.3-2.6s (3 of 3), no hidden tokens, against 1.7s for Gemini 3.5 Flash-Lite,
# which allows 500 calls a day, not 14,400. That suits the small nodes (gate,
# verify, planner) Step 2 wants on the biggest free pool.
#
# ⚠ NOT TESTED FOR QUALITY. Thinking off changes what a verdict or a ranking is
# worth, and the AA 17 and the 0.732 rerank MRR were both measured with thinking
# ON. It also cannot serve a report: 16,000 tokens a MINUTE of input, refused
# locally for free by _check_fits, exactly like the 31B.
#
# THE RERANKER IS UNCHANGED. api/reranking.py builds its tier with
# dataclasses.replace(provider, thinking=None, ...), so this default never reaches
# it - and it must not until the ranking has been re-measured with thinking off.
GEMMA_4_26B = _gemini(
    name="Gemma 4 26B A4B",
    model="gemma-4-26b-a4b-it",
    context_window=262_144,
    max_output_tokens=32_768,
    max_input_tokens=16_000,
    requests_per_minute=GEMMA_REQUESTS_PER_MINUTE,
    thinking="MINIMAL",
)

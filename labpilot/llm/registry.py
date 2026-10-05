from __future__ import annotations

import dataclasses

from labpilot.llm.cline import ClineProvider
from labpilot.llm.gemini import GeminiProvider
from labpilot.llm.openai_compatible import OpenAICompatibleProvider

CLINE_URL = "https://api.cline.bot/api/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GOOGLE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
KILO_URL = "https://api.kilo.ai/api/gateway/v1/chat/completions"
REQUESTY_URL = "https://router.requesty.ai/v1/chat/completions"
LITEROUTER_URL = "https://api.literouter.com/v1/chat/completions"
ORCAROUTER_URL = "https://api.orcarouter.ai/v1/chat/completions"
ROUTEWAY_URL = "https://api.routeway.ai/v1/chat/completions"
CLOUDFLARE_URL = (
    "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/chat/completions"
)

# NOT a preference. This field is what makes the tier work at all.
#
# Measured 2026-09-13, five runs each on one prompt. Without it glm-5.3-flash
# spends its whole budget on reasoning and returns empty content, which Cline
# reports as its own HTTP 500 "empty response content":
#
#     no reasoning field        2 of 5 succeeded   ~1,200 reasoning tokens
#     reasoning.effort = high   5 of 5 succeeded      17-60 reasoning tokens
#
# Note the direction: on this model an explicit effort CAPS the reasoning
# rather than raising it, which is what stops the budget being exhausted. The
# OpenRouter spelling is the right one because Cline routes through OpenRouter
# - its own usage ledger records aiInferenceProviderName "openrouter".
CLINE_REASONING: dict[str, object] = {"reasoning": {"effort": "high"}}

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


# Free, and free in a way no other tier here is: Cline records what the call
# WOULD have cost and charges zero credits. Proven live 2026-09-13 - two
# 1,700-token generations reported costUsd 84,625 and 78,375 with creditsUsed
# 0, while a paid control model deducted credit immediately on 13 tokens.
#
# It leads the chain because the budget it protects is the scarce one: every
# Google Flash model is 20 requests a DAY. A free tier in front of them spends
# nothing we are short of.
#
# TWO THINGS ARE UNKNOWN AND BOTH MATTER. The free quota is published nowhere -
# no docs page, no endpoint, and Cline sends NO rate-limit headers at all, so
# the five-way failure rule cannot tell "busy" from "spent" here and will treat
# the first 429 as a dead pool. And the promotion can end without notice; the
# signal is `cost` in the log line turning into a credit deduction.
def _cline(
    *, name: str, model: str, context_window: int, max_output_tokens: int
) -> ClineProvider:
    """A pool PER MODEL, deliberately, and the choice is a guess with a reason.

    Whether Cline's free quota is per account or per model is unknown and
    cannot be learned without spending the thing being measured. The costs are
    asymmetric, so the guess follows them: sharing a pool when the quota is
    per-model silently loses a whole free tier, while splitting it when the
    quota is per-account wastes exactly ONE request before both are marked
    dead. Same shape as Google, where per-model pools are measured fact.
    """
    return ClineProvider(
        name=name,
        tier=0,
        url=CLINE_URL,
        model=model,
        api_key_env="CLINE_API_KEY",
        quota_pool=f"CLINE_API_KEY:{model}",
        context_window=context_window,
        max_output_tokens=max_output_tokens,
        extra_body=CLINE_REASONING,
    )


CLINE_GLM_5_3_FLASH = _cline(
    name="GLM-5.3 Flash (Cline)",
    model="z-ai/glm-5.3-flash",
    context_window=1_310_720,
    max_output_tokens=131_072,
)

# Tier 9, and the placement is measured rather than argued. Four benchmarks,
# counting only where both models appear:
#
#   vs Nemotron 3 Ultra (below it)   2-0   TB 0.702/0.564 · SWE-ML 0.785/0.677
#   vs Gemini 3.5 Flash-Lite         2-0   TB 0.702/0.540 · SWE-Pro 0.594/0.542
#   vs GLM-5.2 (above it)            1-2   loses TB and SWE-Pro, wins Toolathlon
#
# So it sits exactly between tiers 8 and 10. It is NOT ranked by the AA index
# or LMArena like the rest of the table, because it appears on NEITHER - it is
# a coding specialist with no general-reasoning score anywhere, which is also
# why it is not placed any higher than the evidence puts it.
#
# Two cautions that are real and unresolved. Independent coverage reports it is
# "too closely tuned to Poolside's agent harness" and "can stray from the
# required format" - and our citation contract is parsed, so drift breaks the
# anti-hallucination mechanism rather than merely the prose. And the FREE
# variant caps output at 32,768 against REPORT_MAX_TOKENS of 32,000: 768 tokens
# of headroom. The PAID id `poolside/laguna-s-2.1` has 131,072 and would spend
# credits, which is why the `:free` suffix is load-bearing.
CLINE_LAGUNA_S_2_1 = _cline(
    name="Laguna S 2.1 (Cline)",
    model="poolside/laguna-s-2.1:free",
    context_window=262_144,
    max_output_tokens=32_768,
)

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
GEMINI_3_7_FLASH = _gemini(name="Gemini 3.7 Flash", model="gemini-3.7-flash")
GEMINI_3_6_FLASH = _gemini(name="Gemini 3.6 Flash", model="gemini-3.6-flash")
GEMINI_3_5_FLASH = _gemini(name="Gemini 3.5 Flash", model="gemini-3.5-flash")

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
# ⚠ 32,768 CONTEXT, so it can NEVER serve a report: PROMPT_BUDGET 26,000 plus
# REPORT_MAX_TOKENS 32,000 is 58,000. _check_fits refuses it locally for
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
    thinking="MINIMAL",
)


# ADDED 2026-09-19, and the placement rests on TWO independent sources
# because one of them contradicted the blogs badly. See CLAUDE.md.
#
#                        AA v4.3   Code Arena     out tok/s
#   GLM-5.3 Flash          42      1607  (#17)       94.6
#   Gemini 3.7 Flash       39         -             288.3
#   DeepSeek V4 Flash      35      1580  (#22)      211.9
#   Gemini 3.6 Flash       34      1537  (#32)      182.5
#   Qwen3.8-27B            34      1593  (#18)       43.1
#   Gemini 3.5 Flash       33      1500  (#44)      207.8
#
# ⚠ EVERY OTHER AA NUMBER IN THIS FILE IS FROM AN OLDER INDEX VERSION and is
# NOT comparable with these. v4.3 scores Flash-Lite at 23, where the table
# above the chain still says 37.4. Only re-scored models may be compared.
# THE SAME MODEL ON TWO HOSTS TAKES TWO DIFFERENT WORDS, measured:
#
#   Cloudflare  "Unexpected reasoning effort high. Supported types are
#                xhigh (default), medium, and low."
#   Groq        "invalid Qwen3.8 reasoning_effort" for xhigh; `high` is fine.
#
# So neither host accepts the other's value, and a single shared constant
# would break one of them. This file already records that the same model on
# two hosts has different LIMITS; it also has different PARAMETER VOCABULARY.
#
# xhigh is Cloudflare's default AND the setting Artificial Analysis scored at
# 34, so the placement in CHAIN describes the configuration we actually send.
QWEN_CF_REASONING = {"reasoning_effort": "xhigh"}

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

# THE CODING SPECIALIST, and that is a measured claim rather than a vendor
# one. On general intelligence it TIES Gemini 3.6 Flash (34 = 34); on Code
# Arena it beats it by 56 Elo (1593 against 1537) and beats DeepSeek V4 Flash
# too (#18 against #22). AA also ranks it #1 of 142 open-weights models in the
# 4B-40B class. Step 2 should ROUTE code-writing sub-tasks here rather than
# walking the chain - the same rule this file already applies to Devstral.
#
# Cloudflare FIRST because it is the only one of the two that can serve a
# report: 262,144 context against Groq's binding 8,000 tokens per MINUTE.
# Measured cost: 244 neurons for a 4,860-token call, so ~41 such calls a day
# out of 10,000. Slow, though - 43.1 tok/s is the lowest of any tier here.
QWEN_3_8_27B = OpenAICompatibleProvider(
    name="Qwen3.8 27B",
    tier=0,
    url=CLOUDFLARE_URL,
    model="@cf/qwen/qwen3.8-27b",
    api_key_env="CLOUDFLARE_API_KEY",
    account_env="CLOUDFLARE_ACCOUNT_ID",
    context_window=262_144,
    max_output_tokens=262_144,
    extra_body=QWEN_CF_REASONING,
)

# The SAME model on Groq, and modelled at 8,000 like GPT-OSS is - because the
# binding limit is a per-minute budget covering prompt AND reserved output,
# not the 131,042 context Groq advertises. Read from its own headers:
# x-ratelimit-limit-requests 1000, x-ratelimit-limit-tokens 8000.
#
# So it can NEVER serve a report and _check_fits refuses it locally for free.
# It is here for Step 2's small code jobs, where 1,000 requests a day and a
# 0.6s round trip are worth more than a context it cannot fill.
QWEN_3_8_27B_GROQ = OpenAICompatibleProvider(
    name="Qwen3.8 27B (Groq)",
    tier=0,
    url=GROQ_URL,
    model="qwen/qwen3.8-27b",
    api_key_env="GROQ_API_KEY",
    context_window=8_000,
    max_output_tokens=8_000,
    extra_body=OPENAI_REASONING,
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


# LITEROUTER and ORCAROUTER - two more free gateways, measured 2026-09-23 and
# re-measured LIVE 2026-09-28 before any line here was written: all seven
# routes below answered, 21 of 21 calls, under three reasoning settings each.
#
# Only models ALREADY RANKED in CHAIN are routed here. Both gateways list more
# free models than this, and an unranked model cannot be placed - the same
# rule that kept dots-3-note and nex-n2.5 out on 2026-09-19.
#
# Their value is a SECOND and THIRD route to models whose first route is thin
# or dead: GLM-5.3 Flash (tier 1) is otherwise only on Cline, whose quota is
# invisible; DeepSeek V4 Flash died on OpenRouter AND Kilo; Mistral Medium's
# own account is paused until its monthly usage resets.
#
# LiteRouter publishes NO quota and sends no rate-limit headers - blind, like
# Cline and Kilo - and it allows ONE concurrent request per account, measured
# as a 403 "Too many concurrent requests". A real report prompt fits: 48,011
# tokens to DeepSeek and 27,010 to GLM-5.3 Flash, both 200.
#
# OrcaRouter publishes 10 requests a minute and 50 a day on its own
# /api/free-package/public, and took a 15,691-token report prompt.
#
# ONE pool per gateway, as for Kilo and Requesty: neither limit is per model.
def _gateway(
    *,
    name: str,
    url: str,
    key: str,
    model: str,
    context_window: int,
    max_output_tokens: int,
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name=name,
        tier=0,
        url=url,
        model=model,
        api_key_env=key,
        quota_pool=key,
        context_window=context_window,
        max_output_tokens=max_output_tokens,
        # glm-5.3-flash returns EMPTY content without an explicit effort on
        # Cline and on OrcaRouter - a property of the model, not the host.
        extra_body=OPENROUTER_REASONING,
    )


def _literouter(**kwargs) -> OpenAICompatibleProvider:
    return _gateway(url=LITEROUTER_URL, key="LITEROUTER_API_KEY", **kwargs)


def _orcarouter(**kwargs) -> OpenAICompatibleProvider:
    return _gateway(url=ORCAROUTER_URL, key="ORCAROUTER_API_KEY", **kwargs)


LITEROUTER_GLM_5_3_FLASH = _literouter(
    name="GLM-5.3 Flash (LiteRouter)",
    model="glm-5.3-flash:free",
    context_window=1_310_720,
    max_output_tokens=131_072,
)
ORCAROUTER_GLM_5_3_FLASH = _orcarouter(
    name="GLM-5.3 Flash (OrcaRouter)",
    model="z-ai/glm-5.3-flash-free",
    context_window=1_310_720,
    max_output_tokens=131_072,
)
LITEROUTER_DEEPSEEK_V4_FLASH = _literouter(
    name="DeepSeek V4 Flash (LiteRouter)",
    model="deepseek-v4-flash-0731:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)
ORCAROUTER_DEEPSEEK_V4_FLASH = _orcarouter(
    name="DeepSeek V4 Flash (OrcaRouter)",
    model="deepseek/deepseek-v4-flash-free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)
LITEROUTER_QWEN_3_8_27B = _literouter(
    name="Qwen3.8 27B (LiteRouter)",
    model="qwen3.8-27b:free",
    context_window=262_144,
    max_output_tokens=235_929,
)
LITEROUTER_GLM_5_2 = _literouter(
    name="GLM-5.2 (LiteRouter)",
    model="glm-5.2:free",
    context_window=32_768,
    max_output_tokens=29_491,
)
LITEROUTER_MISTRAL_MEDIUM = _literouter(
    name="Mistral Medium (LiteRouter)",
    model="mistral-medium-2508:free",
    context_window=262_144,
    max_output_tokens=262_144,
)


# ROUTEWAY — a fourth free gateway, probed LIVE 2026-09-29 with
# scripts/probe_routeway.py before any line here was written.
#
# THE LIMITS ARE THE DECISION. Every number is from the API, not a docs page:
#
#     5 requests a MINUTE and 200 a DAY, read from the response headers, and the
#     day counter fell across DIFFERENT models - one budget, so one pool.
#
#     a hard context cap per free route, enforced on prompt PLUS requested
#     output and named in the 400:
#         deepseek-v4-flash:free   42,000   (the model itself holds 1,000,000)
#         the Gemma variants       62,000
#     A 41,901-token prompt passed and a 45,954-token one was refused. So the
#     window is both the context AND the output ceiling, and `max_tokens:
#     131072` on a ten-token prompt is a 400.
#
# WHAT WAS ADDED, and what was measured against it:
#   * DeepSeek V4 Flash - 3 of 3 whole answers to a real question, 2-11s, a
#     correct diagnosis of the planted bug, and a tool call in 2.4s. It cannot
#     serve a report (42,000 against the 58,000 one needs), which
#     CONTEXT_TOO_SMALL in the tests names. A third live route to a model whose
#     two original ones died.
#   * Six Gemma 4 26B A4B variants - 18 of 18 pings and 5 of 6 real answers (the
#     sixth was a proxy timeout at 10.2s, not the model). Routeway's own
#     description calls them COMMUNITY CREATIVE FINETUNES, so they are NOT the
#     stock model AA scores at 17, and none has a score of its own. They sit
#     below the measured Gemma 4 31B (15) on purpose: no evidence, no promotion.
#     The order among them rests on ONE sample each and means nothing.
#
# WHAT WAS LEFT OUT, and why:
#   * MiniMax M2.7 - AA 23, but 0 of 3 whole answers. Its reasoning arrives as
#     `<think>...` INSIDE the reply text, it spends 550-1,024 tokens on one
#     sentence, and one call took 58s. `_visible_text` would return the thinking
#     as the answer.
#   * Muse Glimmer 30B - 0 of 3 whole (one cut at 1,024 tokens after 57s, two
#     60s read timeouts, and an earlier 502). Requesty's route answered in 2.3s.
#
# THE TIMEOUT IS SET PER TIER, which is what the field exists for. Routeway
# HANGS instead of refusing (three DeepSeek calls ran past 60s, one Gemma
# prompt of 59K did too), and the default 600s read timeout would let one hang
# spend two thirds of the 900s chain budget. Real answers were 1-26s.
#
# A `cache-status: MISS/HIT` header shows Routeway caches identical requests.
# temperature is 0 here, so a repeated prompt can be served without a model.
ROUTEWAY_DEEPSEEK_TIMEOUT = (10.0, 120.0)
ROUTEWAY_GEMMA_TIMEOUT = (10.0, 180.0)


def _routeway(
    *,
    name: str,
    model: str,
    context_window: int,
    timeout: tuple[float, float],
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name=name,
        tier=0,
        url=ROUTEWAY_URL,
        model=model,
        api_key_env="ROUTEWAY_API_KEY",
        # ONE pool: 5 a minute and 200 a day are account-wide across models.
        quota_pool="ROUTEWAY_API_KEY",
        context_window=context_window,
        # No separate output cap exists. The server checks prompt PLUS output
        # against one window, and that window is what _check_fits enforces.
        max_output_tokens=context_window,
        timeout=timeout,
        # No `extra_body`: `reasoning_effort` is NOT in these models'
        # supported_parameters (only Muse Glimmer lists it), and an unlisted
        # field is a guess.
    )


ROUTEWAY_DEEPSEEK_V4_FLASH = _routeway(
    name="DeepSeek V4 Flash (Routeway)",
    model="deepseek-v4-flash:free",
    context_window=42_000,
    timeout=ROUTEWAY_DEEPSEEK_TIMEOUT,
)


def _routeway_gemma(variant: str) -> OpenAICompatibleProvider:
    return _routeway(
        name=f"Gemma 4 26B A4B {variant} (Routeway)",
        model=f"gemma-4-26b-a4b-it-{variant.lower()}:free",
        context_window=62_000,
        timeout=ROUTEWAY_GEMMA_TIMEOUT,
    )


# Named first-sample-correct first (they read `xs[i-k:i+1]` as k+1 elements,
# the planted bug). ONE call each, so treat the order as a coin flip.
ROUTEWAY_GEMMA_VARIANTS = tuple(
    _routeway_gemma(variant)
    for variant in (
        "Darksoul",
        "Moonlight",
        "Musica",
        "Luminous",
        "Chimerax",
        "MeroMero",
    )
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
    CLINE_GLM_5_3_FLASH,
    # Tier 1's model on two more gateways. Cline first because it is free and
    # was measured first; LiteRouter's quota is unpublished, OrcaRouter's is
    # 50 a day, so the smaller known allowance goes last.
    LITEROUTER_GLM_5_3_FLASH,
    ORCAROUTER_GLM_5_3_FLASH,
    GEMINI_3_8_FLASH,
    _second_account(GEMINI_3_8_FLASH),
    GEMINI_3_7_FLASH,
    _second_account(GEMINI_3_7_FLASH),
    # --- ADDED 2026-09-19, placed on TWO independent sources ---------------
    # DeepSeek first of the three: it and Qwen TIE on AA (35 vs 34, inside
    # the +-1 interval), Qwen wins Code Arena by 13 Elo, and DeepSeek is
    # FIVE TIMES faster (211.9 tok/s against 43.1) with a 1.05M context and
    # no per-day neuron budget. A 13-Elo coding edge does not buy a 5x
    # slowdown when generation is already 98.2% of an answer.
    #
    # Its two ORIGINAL routes died on 2026-09-23 and wait at the END of the
    # chain; these two took their place.
    LITEROUTER_DEEPSEEK_V4_FLASH,
    ORCAROUTER_DEEPSEEK_V4_FLASH,
    # A third route, and the last of the three because it is the only one that
    # cannot serve a report: 42,000 of context against 58,000. _check_fits
    # refuses it for a report at no cost, and it answers the small jobs.
    ROUTEWAY_DEEPSEEK_V4_FLASH,
    # Then the coding specialist. It ties Gemini 3.6 Flash on general
    # intelligence and beats it by 56 Elo on code, which is the task this
    # project actually does - so it goes above it.
    KILO_QWEN_3_8_27B,
    LITEROUTER_QWEN_3_8_27B,
    QWEN_3_8_27B,
    # ADJACENT, for the same reason the Google twins are: once Cloudflare's
    # neurons are gone the strongest thing still available is the same model
    # on Groq, not a weaker one. It can never serve a report (8,000 tokens a
    # MINUTE), and _check_fits refuses it locally for free.
    QWEN_3_8_27B_GROQ,
    GEMINI_3_6_FLASH,
    _second_account(GEMINI_3_6_FLASH),
    GEMINI_3_5_FLASH,
    _second_account(GEMINI_3_5_FLASH),
    LITEROUTER_GLM_5_2,
    CLINE_LAGUNA_S_2_1,
    KILO_LAGUNA_S_2_1,
    KILO_NEMOTRON_3_ULTRA,
    NEMOTRON_3_ULTRA,
    REQUESTY_NEMOTRON_3_ULTRA,
    KILO_INKLING_SMALL,
    GEMINI_3_5_FLASH_LITE,
    _second_account(GEMINI_3_5_FLASH_LITE),
    LITEROUTER_MISTRAL_MEDIUM,
    KILO_STEP_3_7_FLASH,
    REQUESTY_MUSE_GLIMMER,
    # ADDED 2026-09-30: AA 17 sits between Muse Glimmer (18) and the 31B (15), and
    # it is the reliable, fast Gemma. Adjacent to its key-2 twin for the same
    # reason every Google model is - a spent account costs nothing to skip.
    GEMMA_4_26B,
    _second_account(GEMMA_4_26B),
    GEMMA_4_31B,
    _second_account(GEMMA_4_31B),
    REQUESTY_GEMMA_4_31B,
    # UNSCORED community finetunes, below the measured Gemma 4 31B on purpose.
    *ROUTEWAY_GEMMA_VARIANTS,
    KILO_NORTH_MINI_CODE,
    NORTH_MINI_CODE,
    KILO_NEMOTRON_3_SUPER,
    NEMOTRON_3_SUPER,
    GPT_OSS_120B,
    GPT_OSS_120B_GROQ,
    GEMINI_3_1_FLASH_LITE,
    _second_account(GEMINI_3_1_FLASH_LITE),
    # KNOWN DEAD, KEPT ON PURPOSE - see KNOWN_DEAD below. Kilo before its
    # OpenRouter twin even here, so the day one revives the order is right.
    KILO_GLM_5_2,
    GLM_5_2,
    KILO_DEEPSEEK_V4_FLASH,
    DEEPSEEK_V4_FLASH,
    MISTRAL_MEDIUM,
    MAGISTRAL_SMALL,
    DEVSTRAL_2,
)

# Tiers that answer 404 on every call, KEPT so they can come back. Both free
# routes to each model died the same way, and the error says why:
#
#   DeepSeek V4 Flash   2026-09-23   OpenRouter "unavailable for free. The paid
#                                    version is available now"; Kilo "the
#                                    requested model does not exist"
#   GLM-5.2             2026-09-28   the same two answers, word for word
#
# A free model that disappears sometimes returns. A dead tier at the END costs
# one fast 404, and only once every live tier above it has failed; near the TOP
# it cost a request on EVERY report. Take a name out of this list only after
# that tier answers again - that is a claim, and a test holds you to it.
#
# THE THREE MISTRAL CHAT TIERS WERE ADDED 2026-10-05, and they are not dead
# the way the two above are. Mistral's own catalogue (GET /v1/models) says two
# of them are the SAME MODEL, which is why the calls were fine and the names
# were the problem:
#
#   mistral-medium-latest = Mistral Medium 3.5. Its aliases are mistral-medium,
#       -3, -3-5, -2604, magistral-medium-latest and the two vibe-cli ids.
#   mistral-small-latest  = Mistral Small 4 (mistral-small-2603). Its aliases
#       include magistral-small-latest.
#
# The old pinned ids are gone: every dated magistral-* and devstral-* id except
# devstral-2512 answers 400 "invalid model", and mistral-medium-2508 and
# mistral-small-2506 answer the same limit-0 429 as the new names. Mistral's
# changelog says it plainly:
# Medium 3.5 came out 2026-04-28 and Small 4 on 2026-03-16, Magistral and
# Devstral are listed as deprecated in favour of them, and "Devstral 2.0 moves
# to paid API access" (2026-01-27).
#
# On this account both models answer 429 with x-ratelimit-limit-req-minute: 0,
# on every one of the 40-odd calls made on 2026-10-05, while 11 other models
# answered 200 through the same key, the same network and the same request.
# reasoning_effort "none" does not change it, and the monthly allowance IS back
# ($0 of $10 used) - so this is not a spent quota. The admin Limits page even
# lists medium and small at 1 RPS; the API header is the truth, and the two
# disagree (request id 01a10b8a-8a6c-7754-b703-02ae7ed7b7ba is one for Mistral
# support).
#
# Moved to the END rather than deleted, like the two above, because Mistral may
# change what the free plan includes. Devstral 2 and Magistral Small have NO live
# route elsewhere, which test_registry names as an exception on purpose.
KNOWN_DEAD = (
    KILO_GLM_5_2.name,
    GLM_5_2.name,
    KILO_DEEPSEEK_V4_FLASH.name,
    DEEPSEEK_V4_FLASH.name,
    MISTRAL_MEDIUM.name,
    MAGISTRAL_SMALL.name,
    DEVSTRAL_2.name,
)

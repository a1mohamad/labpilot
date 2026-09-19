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
# Whether it belongs in CHAIN as a GENERATOR is a SEPARATE question and there
# is no evidence for it yet: it appears on neither AA nor LMArena, and this
# chain is ordered on measured capability. Adding it would also force two
# "pin the exceptions by name" lists to change, which must be deliberate.
GEMMA_4_26B = _gemini(
    name="Gemma 4 26B A4B",
    model="gemma-4-26b-a4b-it",
    context_window=262_144,
    max_output_tokens=32_768,
    max_input_tokens=16_000,
    thinking=None,
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
    KILO_DEEPSEEK_V4_FLASH,
    DEEPSEEK_V4_FLASH,
    # Then the coding specialist. It ties Gemini 3.6 Flash on general
    # intelligence and beats it by 56 Elo on code, which is the task this
    # project actually does - so it goes above it.
    KILO_QWEN_3_8_27B,
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
    KILO_GLM_5_2,
    GLM_5_2,
    CLINE_LAGUNA_S_2_1,
    KILO_LAGUNA_S_2_1,
    KILO_NEMOTRON_3_ULTRA,
    NEMOTRON_3_ULTRA,
    REQUESTY_NEMOTRON_3_ULTRA,
    KILO_INKLING_SMALL,
    GEMINI_3_5_FLASH_LITE,
    _second_account(GEMINI_3_5_FLASH_LITE),
    MISTRAL_MEDIUM,
    KILO_STEP_3_7_FLASH,
    REQUESTY_MUSE_GLIMMER,
    GEMMA_4_31B,
    _second_account(GEMMA_4_31B),
    REQUESTY_GEMMA_4_31B,
    KILO_NORTH_MINI_CODE,
    NORTH_MINI_CODE,
    KILO_NEMOTRON_3_SUPER,
    NEMOTRON_3_SUPER,
    GPT_OSS_120B,
    GPT_OSS_120B_GROQ,
    MAGISTRAL_SMALL,
    DEVSTRAL_2,
    GEMINI_3_1_FLASH_LITE,
    _second_account(GEMINI_3_1_FLASH_LITE),
)

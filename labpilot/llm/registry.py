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
BAZAARLINK_URL = "https://api.bazaarlink.ai/v1/chat/completions"
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
#
# "high" -> "medium" on 2026-10-25. The cap measured above was on a SHORT
# prompt. On the stuffed report (about 20,000 tokens in), "high" thought
# 29,182 tokens, took 547 s and was cut at 32,000; a second try ran 511 s and
# came back empty (HTTP 500). The same prompt at "medium": 2,490 reasoning
# tokens, 78 s, finished; at "low": 2,084, 74 s, finished. Both scored like the
# cut "high" report when read (section 26). Five short prompts at "medium":
# 5 of 5 answered, 2-5 s.
CLINE_REASONING: dict[str, object] = {"reasoning": {"effort": "medium"}}

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

# ADDED 2026-11-02, and placed on the evidence that exists. Both answered the
# real provider code on 2026-11-02 (1.4 s and 3.3 s) and cost zero credits.
#
#   Beam 1.0 (Reflection)   AA v4.3.2 = 30  - launch article and a comparison
#       page agree; the page for the CURRENT index (v5.0) says 18, because
#       GDPval-AA was dropped from the index, so only v4.3.2 numbers are used
#       beside the rest of this file.
#   Nemotron 3.5 Lightning  UNSCORED - AA shows 6, 13, 16 and 24 on different
#       pages and versions, so no number is trusted and it sits with the other
#       unscored tiers.
#
# The windows are NOT measured on Cline. Beam is modelled for SMALL JOBS only
# (a 16,384 output cap, like Bazaarlink's guard) until a long answer is tried.
# Cline publishes no quota and no rate-limit headers, as for tier 1.
CLINE_BEAM_1_0 = _cline(
    name="Beam 1.0 (Cline)",
    model="reflection/beam-free",
    context_window=131_072,
    max_output_tokens=16_384,
)
CLINE_NEMOTRON_3_5_LIGHTNING = _cline(
    name="Nemotron 3.5 Lightning (Cline)",
    model="nvidia/nemotron-3.5-lightning-free",
    context_window=1_000_000,
    max_output_tokens=65_536,
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

# ADDED 2026-11-02, UNSCORED (no v4.3.2 page was found), 1.5 s live. The smaller
# GPT-OSS on the same Groq account: the same 8,000-token per-minute budget, so
# it can never serve a report and _check_fits turns one away for free. Small
# jobs only, like its sibling.
GPT_OSS_20B_GROQ = OpenAICompatibleProvider(
    name="GPT-OSS 20B (Groq)",
    tier=0,
    url=GROQ_URL,
    model="openai/gpt-oss-20b",
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
# LiteRouter sends no rate-limit headers, and it allows ONE concurrent request
# per account, measured as a 403 "Too many concurrent requests". Its DASHBOARD
# does publish a daily limit, per model - see _literouter below, which is why
# this note used to say "publishes no quota" and no longer does. A real report
# prompt fits: 48,011 tokens to DeepSeek and 27,010 to GLM-5.3 Flash, both 200.
#
# OrcaRouter publishes 10 requests a minute and 50 a day on its own
# /api/free-package/public, and took a 15,691-token report prompt.
#
# ONE pool per gateway for OrcaRouter, Kilo and Requesty: none of their limits
# is per model. LiteRouter is the exception, and test_registry pins it.
def _gateway(
    *,
    name: str,
    url: str,
    key: str,
    model: str,
    context_window: int,
    max_output_tokens: int,
    quota_pool: str | None = None,
    seconds_between_calls: float = 0.0,
    seconds_after_call: float = 0.0,
    max_concurrent: int | None = None,
    requests_per_minute: int | None = None,
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name=name,
        tier=0,
        url=url,
        model=model,
        api_key_env=key,
        quota_pool=quota_pool or key,
        context_window=context_window,
        max_output_tokens=max_output_tokens,
        seconds_between_calls=seconds_between_calls,
        seconds_after_call=seconds_after_call,
        max_concurrent=max_concurrent,
        requests_per_minute=requests_per_minute,
        # glm-5.3-flash returns EMPTY content without an explicit effort on
        # Cline and on OrcaRouter - a property of the model, not the host.
        extra_body=OPENROUTER_REASONING,
    )


# LiteRouter, read from its own dashboard and measured 2026-10-11.
#
#   daily limit   shown PER MODEL on every card: "Free tier (100)" for some ids
#                 and "(∞)" for others, so each model is its own pool, the way
#                 Google's are. This replaces the note above that said
#                 LiteRouter publishes no quota.
#   cooldown      7 seconds between messages for the ACCOUNT, answered with
#                 HTTP 403 (not 429) on any model. Measured: four models called
#                 back to back, one 200 and three refused; the same three
#                 answered when spaced 8 seconds apart. 8 is the measured
#                 value that worked, 7 is the number the error states.
LITEROUTER_SECONDS_BETWEEN_CALLS = 8.0
# One request at a time for the whole account (403 "Too many concurrent requests",
# 2026-10-11 and again with the product's own parallel nodes, 2026-11-11). The gap
# above does not stop it, because a call can run for a minute.
LITEROUTER_MAX_CONCURRENT = 1
# A call that started 0 s after another one ENDED was refused 403 although its
# start was 9 s after the other's start (measured 2026-11-16, 12 of 13 LiteRouter
# refusals were this text). So the account is also closed for a moment after a call.
LITEROUTER_QUIET_AFTER_CALL = 1.0


def _literouter(*, model: str, **kwargs) -> OpenAICompatibleProvider:
    return _gateway(
        url=LITEROUTER_URL,
        key="LITEROUTER_API_KEY",
        model=model,
        quota_pool=f"LITEROUTER_API_KEY:{model}",
        seconds_between_calls=LITEROUTER_SECONDS_BETWEEN_CALLS,
        seconds_after_call=LITEROUTER_QUIET_AFTER_CALL,
        max_concurrent=LITEROUTER_MAX_CONCURRENT,
        **kwargs,
    )


# Its own free-package page: 10 requests a minute, 50 a day, for the account.
ORCAROUTER_REQUESTS_PER_MINUTE = 10


def _orcarouter(**kwargs) -> OpenAICompatibleProvider:
    return _gateway(
        url=ORCAROUTER_URL,
        key="ORCAROUTER_API_KEY",
        requests_per_minute=ORCAROUTER_REQUESTS_PER_MINUTE,
        **kwargs,
    )


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
# The free id was "deepseek-v4-flash-0731:free" until it left the catalogue
# (403 "not available or misspelled", 2026-10-11). The same model is listed
# without the date, and answered a 41,628-token prompt and a 32,000-token ask.
LITEROUTER_DEEPSEEK_V4_FLASH = _literouter(
    name="DeepSeek V4 Flash (LiteRouter)",
    model="deepseek-v4-flash:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)
# THE REST OF LITEROUTER'S FREE DEEPSEEK, added 2026-10-11. Nine ids are listed
# free; all nine answered a 15.8K-token prompt, a 41.6K-token prompt and a
# 32,000-token output ask, one call at a time. Placed on Artificial Analysis
# v4.3.2, read from each model's own page:
#
#     DeepSeek V4.1 Flash   39   214 tok/s    ABOVE the V4 Flash it follows
#     DeepSeek V4 Pro       36    85 tok/s    (the page may be a newer build
#                                              than the free id - not checked)
#     DeepSeek V4 Flash     34   216 tok/s
#     DeepSeek V3.2         16*  (an estimate, "independent evaluation
#                                 forthcoming")
#
# THE "-cheap" AND "-stable" IDS: LiteRouter does not say what they are, and
# neither do we. They answered like their base ids, so each is placed right
# after its base as a second route to the same family. Nothing here claims they
# are the same weights; if one turns out to be a lower-quality serving, this is
# the place to move it. The dashboard shows "(inf)" daily on the cheap ids that
# were visible and 100 on the base ids.
#
# V3.1 and V3.2 are OLDER models and they did worst: both named the wrong class
# on the 15.8K prompt ("QuoraPreproccesor" for SystemConfig), V3.1 on the 41K one
# too. They sit at the bottom, V3.2 by its score and V3.1 unscored, last.
LITEROUTER_DEEPSEEK_V4_1_FLASH = _literouter(
    name="DeepSeek V4.1 Flash (LiteRouter)",
    model="deepseek-v4.1-flash:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)
LITEROUTER_DEEPSEEK_V4_1_FLASH_STABLE = _literouter(
    name="DeepSeek V4.1 Flash stable (LiteRouter)",
    model="deepseek-v4.1-flash-stable:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)
LITEROUTER_DEEPSEEK_V4_1_FLASH_CHEAP = _literouter(
    name="DeepSeek V4.1 Flash cheap (LiteRouter)",
    model="deepseek-v4.1-flash-cheap:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)
LITEROUTER_DEEPSEEK_V4_PRO = _literouter(
    name="DeepSeek V4 Pro (LiteRouter)",
    model="deepseek-v4-pro:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)
LITEROUTER_DEEPSEEK_V4_PRO_CHEAP = _literouter(
    name="DeepSeek V4 Pro cheap (LiteRouter)",
    model="deepseek-v4-pro-cheap:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)
LITEROUTER_DEEPSEEK_V4_FLASH_CHEAP = _literouter(
    name="DeepSeek V4 Flash cheap (LiteRouter)",
    model="deepseek-v4-flash-cheap:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)
# The V3 pair holds 128k on Artificial Analysis. 32,768 of output is what a
# 32,000-token ask was accepted at, not a measured ceiling.
LITEROUTER_DEEPSEEK_V3_2 = _literouter(
    name="DeepSeek V3.2 (LiteRouter)",
    model="deepseek-v3.2:free",
    context_window=131_072,
    max_output_tokens=32_768,
)
LITEROUTER_DEEPSEEK_V3_1 = _literouter(
    name="DeepSeek V3.1 (LiteRouter)",
    model="deepseek-v3.1:free",
    context_window=131_072,
    max_output_tokens=32_768,
)
ORCAROUTER_DEEPSEEK_V4_FLASH = _orcarouter(
    name="DeepSeek V4 Flash (OrcaRouter)",
    model="deepseek/deepseek-v4-flash-free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)
# REPLACES "qwen3.8-27b:free", which left the free list (403 "not available or
# misspelled", 2026-10-11). This is NOT the same model: the 27B is gone and the
# list now holds Qwen3.8 Flash. Artificial Analysis scores the open checkpoint
# Qwen3.8-Flash-Next at 40 on v4.3.2 (reasoning), against 34 for the 27B, but
# it has no page under this exact name, so the match is unproven and the tier
# sits where the 27B sat. Measured 2026-10-11: a 40,892-token prompt answered
# correctly, but it took 157s once, against 6-15s for every other id tested.
LITEROUTER_QWEN_3_8_FLASH = _literouter(
    name="Qwen3.8 Flash (LiteRouter)",
    model="qwen3.8-flash:free",
    context_window=262_144,
    max_output_tokens=65_536,
)
# The 32,768 window and 29,491 output here came from OpenRouter's free route
# and were never measured on LiteRouter. Measured 2026-10-11: a 37,458-token
# prompt answered correctly and a 32,000-token output ask was accepted, so the
# window is larger than that and a report fits. Nothing above 37K was tried,
# which is why this is 131,072 and not the 200,000 the family is rated for.
LITEROUTER_GLM_5_2 = _literouter(
    name="GLM-5.2 (LiteRouter)",
    model="glm-5.2:free",
    context_window=131_072,
    max_output_tokens=65_536,
)
# MORE OF LITEROUTER'S FREE LIST, added 2026-10-11. Every id below answered a
# tiny prompt both with and without the `reasoning` field the registry sends,
# a 15.8K-token prompt correctly, a ~38K-token prompt, and a 32,000-token output
# ask, with no empty answer and no "<think>" leaking into the text (MiniMax M2.7
# did leak it on Routeway, which is why it was left out there). Scores are
# Artificial Analysis v4.3.2, each read from the model's own page:
#
#     GLM-5.3 Flash cheap   42   (the tier-1 model; a second LiteRouter id)
#     GLM-5.2 cheap         34   (a second id for the GLM-5.2 route above)
#     MiniMax M3            29       and its "-cheap" id
#     GLM-5                 28*  an estimate, and the page says deprecated
#     Kimi K2.6             27   the free list has only the "-cheap" id
#     GLM-5.1               26
#     Kimi K2.7 Code        26   again only "-cheap"; the 42 a search snippet
#                                gave was the OLD index (v4.1) - the page says 26
#     MiniMax M2.7          23
#
# LEFT OUT, because there is no independent score to place them by: MiniMax
# M3.1 Flash and Tencent Hy4 / Hy3 (Hy4 spent 1,000-1,600 tokens answering "you
# are online"). No evidence, no promotion. Windows below are what each family is
# rated for; none was tried above ~38K tokens.
LITEROUTER_GLM_5_3_FLASH_CHEAP = _literouter(
    name="GLM-5.3 Flash cheap (LiteRouter)",
    model="glm-5.3-flash-cheap:free",
    context_window=1_310_720,
    max_output_tokens=131_072,
)
LITEROUTER_GLM_5_2_CHEAP = _literouter(
    name="GLM-5.2 cheap (LiteRouter)",
    model="glm-5.2-cheap:free",
    context_window=131_072,
    max_output_tokens=65_536,
)
LITEROUTER_MINIMAX_M3 = _literouter(
    name="MiniMax M3 (LiteRouter)",
    model="minimax-m3:free",
    context_window=1_000_000,
    max_output_tokens=65_536,
)
LITEROUTER_MINIMAX_M3_CHEAP = _literouter(
    name="MiniMax M3 cheap (LiteRouter)",
    model="minimax-m3-cheap:free",
    context_window=1_000_000,
    max_output_tokens=65_536,
)
LITEROUTER_GLM_5 = _literouter(
    name="GLM-5 (LiteRouter)",
    model="glm-5:free",
    context_window=200_000,
    max_output_tokens=65_536,
)
LITEROUTER_KIMI_K2_6 = _literouter(
    name="Kimi K2.6 cheap (LiteRouter)",
    model="kimi-k2.6-cheap:free",
    context_window=262_144,
    max_output_tokens=65_536,
)
LITEROUTER_GLM_5_1 = _literouter(
    name="GLM-5.1 (LiteRouter)",
    model="glm-5.1:free",
    context_window=200_000,
    max_output_tokens=65_536,
)
LITEROUTER_KIMI_K2_7_CODE = _literouter(
    name="Kimi K2.7 Code cheap (LiteRouter)",
    model="kimi-k2.7-code-cheap:free",
    context_window=262_144,
    max_output_tokens=65_536,
)
LITEROUTER_MINIMAX_M2_7 = _literouter(
    name="MiniMax M2.7 (LiteRouter)",
    model="minimax-m2.7:free",
    context_window=204_800,
    max_output_tokens=65_536,
)
# REPLACES "mistral-medium-2508:free", which left the free list (403, 2026-10-11).
# Mistral Large 3 is the only large Mistral on it, and it is WEAK: AA v4.3.2 = 9
# (the page calls it deprecated), and on 2026-10-11 it named the wrong class on
# a 41K prompt ("QuoraPreproccesor" for SystemConfig). It goes at the very end
# of the live tiers, where it is only ever reached when everything better has
# failed.
LITEROUTER_MISTRAL_LARGE_3 = _literouter(
    name="Mistral Large 3 (LiteRouter)",
    model="mistral-large-3:free",
    context_window=262_144,
    max_output_tokens=32_768,
)

# ADDED 2026-11-02 after the free lists of every gateway were re-read through
# their own APIs and every new id probed (one call, up to 2 retries). 12 of the
# ids above had LEFT the free list (403 "not available or misspelled") and moved
# to KNOWN_DEAD; these are the free ids that answered and are worth a slot.
#
#   GLM-5.1 cheap   AA v4.3.2 = 26 (the GLM-5.1 score; the "-cheap" serving is
#                   not proven identical, as for every "-cheap" id here). 3.9 s.
#   Hy3             AA v4.3.2 = 23 (Hy3-preview, reasoning), a tie with
#                   Flash-Lite. 7.7 s here, 3.5 s on OrcaRouter. The window is
#                   what the family is rated for, not measured on this gateway.
#   Qwen3.8 Flash stable   the "-stable" twin of the tier above it. 6.1 s.
#   Qwen3 Coder Next / Qwen3 Coder   UNSCORED. AA shows 21 for Coder Next on
#                   index v4.1.1 and 9 on an older page, and 12 to 18 for the
#                   480B Coder, none of them on v4.3.2, so they go with the
#                   unscored tiers. 8.7 s and 7.0 s. Qwen was asked for.
LITEROUTER_GLM_5_1_CHEAP = _literouter(
    name="GLM-5.1 cheap (LiteRouter)",
    model="glm-5.1-cheap:free",
    context_window=204_800,
    max_output_tokens=131_072,
)
LITEROUTER_HY3 = _literouter(
    name="Hy3 (LiteRouter)",
    model="hy3:free",
    context_window=262_144,
    max_output_tokens=65_536,
)
LITEROUTER_QWEN_3_8_FLASH_STABLE = _literouter(
    name="Qwen3.8 Flash stable (LiteRouter)",
    model="qwen3.8-flash-stable:free",
    context_window=1_000_000,
    max_output_tokens=131_072,
)
LITEROUTER_QWEN3_CODER_NEXT = _literouter(
    name="Qwen3 Coder Next (LiteRouter)",
    model="qwen3-coder-next:free",
    context_window=262_144,
    max_output_tokens=235_929,
)
# GPT-OSS 120B on LiteRouter (added 2026-11-02 at the user's request): the same
# model as the Cloudflare and Groq tiers, 9.9 s live. A DELIBERATE 16,384 output
# cap, because no long answer was tried on this route, so it serves small jobs
# until one is. It goes after Cloudflare's route and before Groq's.
LITEROUTER_GPT_OSS_120B = _literouter(
    name="GPT-OSS 120B (LiteRouter)",
    model="gpt-oss-120b:free",
    context_window=131_072,
    max_output_tokens=16_384,
)
LITEROUTER_QWEN3_CODER = _literouter(
    name="Qwen3 Coder (LiteRouter)",
    model="qwen3-coder:free",
    context_window=262_144,
    max_output_tokens=65_536,
)
# ADDED 2026-11-08, after LiteRouter's free list was re-read and every new id was
# probed (one tiny call, `reasoning: high`, 8 s apart, up to 3 tries): all four
# answered on the FIRST try with a whole answer.
#
#   GLM-5.3 cheap         8.6 s   AA v4.3.2 = 42 is the GLM-5.3 Flash score; the
#                                 id has no "flash" in it, so the match is not
#                                 proven, like every "-cheap" id here
#   DeepSeek V4.1 Flash 1017      4.6 s   a dated build of the 39 model, placed
#                                 after the other V4.1 ids
#   DeepSeek V4 Flash 0731 stable 7.8 s   a build of the 34 model, after V4 Flash
#   MiMo V2.6 Flash       1.6 s   the fastest of the set. Scored the same day from
#                                 the AA v5.0.1 chart: 27 (see its CHAIN slot)
#
# Windows come from the catalogue (1,048,576 and 1,050,000); no output cap is
# published for MiMo, so 32,768 is a conservative guess, not a measurement.
LITEROUTER_GLM_5_3_CHEAP = _literouter(
    name="GLM-5.3 cheap (LiteRouter)",
    model="glm-5.3-cheap:free",
    context_window=1_048_576,
    max_output_tokens=131_072,
)
LITEROUTER_DEEPSEEK_V4_1_FLASH_1017 = _literouter(
    name="DeepSeek V4.1 Flash 1017 (LiteRouter)",
    model="deepseek-v4.1-flash-1017:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)
LITEROUTER_DEEPSEEK_V4_FLASH_0731_STABLE = _literouter(
    name="DeepSeek V4 Flash 0731 stable (LiteRouter)",
    model="deepseek-v4-flash-0731-stable:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)
# ADDED 2026-11-15 from LiteRouter's free list (GET /v1/models, ids ending ":free").
# Builds of families already scored, so each sits next to its base. The windows
# are what the catalogue lists (1,048,576); the output cap is the family's, not
# measured on these ids. Probed before they were kept (see the commit notes).
LITEROUTER_DEEPSEEK_V4_FLASH_0731 = _literouter(
    name="DeepSeek V4 Flash 0731 (LiteRouter)",
    model="deepseek-v4-flash-0731:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)
LITEROUTER_DEEPSEEK_V4_FLASH_0731_CHEAP = _literouter(
    name="DeepSeek V4 Flash 0731 cheap (LiteRouter)",
    model="deepseek-v4-flash-0731-cheap:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)
LITEROUTER_DEEPSEEK_V4_PRO_0813 = _literouter(
    name="DeepSeek V4 Pro 0813 (LiteRouter)",
    model="deepseek-v4-pro-0813:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)
LITEROUTER_DEEPSEEK_V4_PRO_STABLE = _literouter(
    name="DeepSeek V4 Pro stable (LiteRouter)",
    model="deepseek-v4-pro-stable:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)
# UNSCORED, so it goes with the other unscored Qwen3 tiers. 262,144 is the
# catalogue window; the 65,536 output cap is a guess, like the Kimi ones above.
LITEROUTER_QWEN3_NEXT_80B = _literouter(
    name="Qwen3 Next 80B (LiteRouter)",
    model="qwen3-next-80b-a3b-instruct:free",
    context_window=262_144,
    max_output_tokens=65_536,
)
# MiniMax M3.1 Flash on LiteRouter, added the same day at the user's request:
# 1.9 s, whole answer, first try. Routeway's route of this model has a 42,000
# window and can never hold a report; LiteRouter lists 1,048,576. The 65,536 output
# cap is the MiniMax M3 figure above, not a measurement of this id.
LITEROUTER_MINIMAX_M3_1_FLASH = _literouter(
    name="MiniMax M3.1 Flash (LiteRouter)",
    model="minimax-m3.1-flash:free",
    context_window=1_048_576,
    max_output_tokens=65_536,
)
LITEROUTER_MIMO_V2_6_FLASH = _literouter(
    name="MiMo V2.6 Flash (LiteRouter)",
    model="mimo-v2.6-flash:free",
    context_window=1_050_000,
    max_output_tokens=32_768,
)
# OrcaRouter, same day. DeepSeek V4.1 Flash is the AA v4.3.2 = 39 model that
# LiteRouter also serves; this route answered in 2.3 s against 17 s there, but
# OrcaRouter allows 50 a day, so it goes AFTER the LiteRouter ids.
ORCAROUTER_DEEPSEEK_V4_1_FLASH = _orcarouter(
    name="DeepSeek V4.1 Flash (OrcaRouter)",
    model="deepseek/deepseek-v4.1-flash-free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)
ORCAROUTER_HY3 = _orcarouter(
    name="Hy3 (OrcaRouter)",
    model="tencent/hy3-free",
    context_window=262_144,
    max_output_tokens=65_536,
)
# ADDED 2026-11-16 after 5 of 5 probes answered in 5.8 to 7.0 s (a reasoning model:
# 130 to 194 tokens for a one-sentence answer). OrcaRouter's catalogue and Kilo's
# list give no window and no output cap, so both are CONSERVATIVE GUESSES, not
# measurements: it serves small jobs until a long answer is tried.
ORCAROUTER_HY4_PREVIEW = _orcarouter(
    name="Hy4 preview (OrcaRouter)",
    model="tencent/hy4-preview-free",
    context_window=131_072,
    max_output_tokens=16_384,
)


# ROUTEWAY — a fourth free gateway, probed LIVE 2026-09-29 with
# scripts/models/probe_routeway.py before any line here was written.
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
# Its response headers: x-ratelimit-limit-minute 5 and limit-day 200 for the account
# (read 2026-09-29 and again 2026-11-16).
ROUTEWAY_REQUESTS_PER_MINUTE = 5


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
        requests_per_minute=ROUTEWAY_REQUESTS_PER_MINUTE,
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
# ADDED 2026-11-02 (the DeepSeek id above is GONE: 400 "No model found"; the
# replacement id deepseek-v4.1-flash:free is listed free but timed out on 5 of 5
# tries at 120 s, so it is NOT added - retest later with a short timeout).
#
#   MiniMax M3.1 Flash  AA v4.3.2 = 43 (the comparison pages on that index; the
#       current v5.0 page says 29). Probed 29.5 s for a one-line answer, so it
#       is slow for small jobs, and the catalogue window is 42,000, so it can
#       NEVER serve a report (CONTEXT_TOO_SMALL names it). It sits in the 42-41
#       group, a tie by this project's rule, and not first, because a 30-second
#       tier at position 1 would slow every small call that it answers.
#   Muse Glimmer 30B   AA v4.3 = 18, the model Requesty serves. 13.0 s here,
#       131,072 window. An earlier probe (2026-09-29) lost 3 of 3 answers to
#       timeouts, so it is the SECOND route, after Requesty's.
ROUTEWAY_MINIMAX_M3_1_FLASH = _routeway(
    name="MiniMax M3.1 Flash (Routeway)",
    model="minimax-m3.1-flash:free",
    context_window=42_000,
    timeout=ROUTEWAY_DEEPSEEK_TIMEOUT,
)
ROUTEWAY_MUSE_GLIMMER = _routeway(
    name="Muse Glimmer 30B (Routeway)",
    model="muse-glimmer-30b:free",
    context_window=131_072,
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


# Each Google model appears THREE times, on three accounts, adjacent. Adjacency
# is right here for the same reason the 2026-08-16 rewrite made it harmless: a
# spent pool is skipped for free, so a twin costs nothing when the first key
# still works and is the strongest available model when it does not. Ordering
# by capability then means "the same model on another account" beats
# "a weaker model on this one".
CHAIN = _ordered(
    # GLM-5.3 Flash on two gateways (its Cline route is KNOWN_DEAD since
    # 2026-11-03). OrcaRouter's route of it is in NOT_TRUSTED, at the tail.
    LITEROUTER_GLM_5_3_FLASH,
    LITEROUTER_GLM_5_3_FLASH_CHEAP,
    # MOVED UP 2026-11-08 on AA v5.0.1 (one page, one index, read from a
    # screenshot of the live chart): DeepSeek V4.1 Flash 1017 = 33, ahead of
    # Gemini 3.8 Flash (31) by two points, so a real gap and not a tie.
    LITEROUTER_DEEPSEEK_V4_1_FLASH_1017,
    # ADDED 2026-11-16: Hy4 preview on OrcaRouter answered 5 of 5 probes in 5.8 to
    # 7.0 s, and it has its OWN OrcaRouter allowance (50 a minute, 250 a day).
    # Its score is NOT settled: the v5.0.1 chart read on 2026-11-08 showed a "Hy4"
    # at 35, but whether that is this preview build is not proven, and 30.3 found
    # no score for the preview. So it goes just under the two models that are
    # scored on that page above it, and it is in no score table. Move it by the
    # live AA page.
    ORCAROUTER_HY4_PREVIEW,
    GEMINI_4_HYDROGEN,
    *_other_accounts(GEMINI_4_HYDROGEN),
    GEMINI_3_8_FLASH,
    *_other_accounts(GEMINI_3_8_FLASH),
    # ADDED 2026-11-02: Ling 3.1 Flash, AA v4.3.2 = 41 (a tie with Gemini 3.8
    # Flash), 2 s on both routes. On v5.0.1 it is 30 against Gemini 3.8's 31, still
    # a tie. (Kilo's route answers 404 since 2026-11-15 and waits in KNOWN_DEAD.)
    REQUESTY_LING_3_1_FLASH,
    # Gemini 3.7 Flash is NOT in the chain: Google redirects it to 3.8 (the reply's
    # modelVersion says "gemini-3.8-flash", checked 2026-11-16), so it was the
    # same model a second time under a different quota name.
    # MiniMax M3.1 Flash: AA v4.3.2 = 43 (a tie with Ling 41) but v5.0.1 = 29
    # (index v5 dropped GDPval), two points under Gemini 3.8 (31). It was first
    # at position 4 on the v4.3.2 number; both indexes agree it belongs after the
    # Gemini 3.8 and Ling tiers and before DeepSeek V4.1 Flash. LiteRouter's route
    # first: its 1M window can hold a report, Routeway's 42,000 never can and it
    # answers in about 30 s.
    LITEROUTER_MINIMAX_M3_1_FLASH,
    ROUTEWAY_MINIMAX_M3_1_FLASH,
    # --- ADDED 2026-10-11: DeepSeek on LiteRouter, by AA v4.3.2 -------------
    # V4.1 Flash (39) ties Gemini 3.7 Flash, and 3.7 is now served by 3.8 (41),
    # so it goes after the pair. Each "-stable" and "-cheap" id follows its base.
    # (The stable id, V4 Pro and the plain V4 Flash left the free list on
    # 2026-11-02 and wait in KNOWN_DEAD.) OrcaRouter's V4.1 Flash is in
    # NOT_TRUSTED.
    # ADDED 2026-11-16: Token Harbor's route first. The same model (AA 39), 2.8 to
    # 3.8 s on 5 of 5, 60 requests a minute and no concurrency limit, where
    # LiteRouter takes one request at a time and waits 8 s between calls.
    TOKEN_HARBOR_DEEPSEEK_V4_1_FLASH,
    LITEROUTER_DEEPSEEK_V4_1_FLASH,
    LITEROUTER_DEEPSEEK_V4_1_FLASH_CHEAP,
    # REVIVED 2026-11-08: V4 Pro cheap answers again (V4 Pro is 36, between the
    # V4.1 Flash ids above and the V4 Flash ids below). Only the cheap id is on
    # the free list; the plain V4 Pro and the V4.1 Flash stable id stay dead.
    LITEROUTER_DEEPSEEK_V4_PRO_CHEAP,
    # ADDED 2026-11-15: two more builds of V4 Pro, after its cheap id.
    LITEROUTER_DEEPSEEK_V4_PRO_0813,
    # --- ADDED 2026-09-19, placed on TWO independent sources ---------------
    # DeepSeek first of the three: it and Qwen TIE on AA (35 vs 34, inside
    # the +-1 interval), Qwen wins Code Arena by 13 Elo, and DeepSeek is
    # FIVE TIMES faster (211.9 tok/s against 43.1) with a 1.05M context and
    # no per-day neuron budget. A 13-Elo coding edge does not buy a 5x
    # slowdown when generation is already 98.2% of an answer.
    #
    # Its two ORIGINAL routes died on 2026-09-23 and wait at the END of the
    # chain; the LiteRouter and Routeway ones followed on 2026-11-02.
    # REVIVED 2026-11-08: the plain V4 Flash id is free again; each "-cheap" and
    # "-stable" id follows its base.
    # ADDED 2026-11-16: Token Harbor's route of the same model first (5 of 5).
    TOKEN_HARBOR_DEEPSEEK_V4_FLASH,
    LITEROUTER_DEEPSEEK_V4_FLASH,
    LITEROUTER_DEEPSEEK_V4_FLASH_CHEAP,
    # ADDED 2026-11-16: MiMo V2.6 Flash = 27 on the AA v5.0.1 chart, two points
    # under MiniMax M3.1 Flash (29) and seven over Qwen3.8 27B (20). Its LiteRouter
    # route left the free list on 2026-11-15, so this is its only route.
    TOKEN_HARBOR_MIMO_V2_6_FLASH,
    # Then the coding specialist. It ties Gemini 3.6 Flash on general
    # intelligence and beats it by 56 Elo on code, which is the task this
    # project actually does - so it goes above it.
    # (Qwen3.8 Flash and MiMo V2.6 Flash left LiteRouter's free list on
    # 2026-11-15 and wait in KNOWN_DEAD.)
    QWEN_3_8_27B,
    # ADJACENT, for the same reason the Google twins are: once Cloudflare's
    # neurons are gone the strongest thing still available is the same model
    # on Groq, not a weaker one. It can never serve a report (8,000 tokens a
    # MINUTE), and _check_fits refuses it locally for free.
    QWEN_3_8_27B_GROQ,
    # (GLM-5.2 cheap, revived 2026-11-08, left the free list again 2026-11-15.)
    GEMINI_3_6_FLASH,
    *_other_accounts(GEMINI_3_6_FLASH),
    # Gemini 3.5 Flash is NOT in the chain either: Google redirects it to 3.6
    # (modelVersion "gemini-3.6-flash", checked 2026-11-16).
    # (Beam 1.0 on Cline answers 402 since 2026-11-15 and waits in KNOWN_DEAD.)
    KILO_NEMOTRON_3_ULTRA,
    NEMOTRON_3_ULTRA,
    REQUESTY_NEMOTRON_3_ULTRA,
    GEMINI_3_5_FLASH_LITE,
    *_other_accounts(GEMINI_3_5_FLASH_LITE),
    # AA 23, a tie with Flash-Lite, which has a measured allowance. (Hy3 has no
    # trusted route: LiteRouter's is dead and OrcaRouter's is in NOT_TRUSTED.)
    LITEROUTER_MINIMAX_M2_7,
    LITEROUTER_HY3,
    # (Muse Glimmer has no trusted route: both Requesty's and Routeway's are in
    # NOT_TRUSTED, 2026-11-16.)
    # Gemma 4 26B A4B, AA 17. Moved to NOT_TRUSTED on 2026-11-17 and BACK to
    # trusted the same day (the user's rule: trusted in 2 of 3 sittings; it
    # failed 0 of 2, then passed 5 of 5, then passed 4 of 5).
    GEMMA_4_26B,
    *_other_accounts(GEMMA_4_26B),
    # AA 16 (an estimate) sits between the Gemma 26B (17) and the 31B (15).
    LITEROUTER_DEEPSEEK_V3_2,
    # MOVED UP 2026-11-15 from the unscored tiers. Both routes answered the smoke
    # test (Kilo 6.4 s, Cline 3.6 s) and Cline's is its ONLY usable free model
    # now. Its score is NOT settled: Artificial Analysis's launch article says 24,
    # comparison pages say 13 and 16, and the model page says 6. 16 (the middle
    # reading that is not the outlier) puts it level with DeepSeek V3.2 and just
    # above the Gemma 4 31B (15). Kilo first (200 an hour), Cline second (no
    # published quota). Move it by the live AA page, not by this guess.
    KILO_NEMOTRON_3_5_LIGHTNING,
    CLINE_NEMOTRON_3_5_LIGHTNING,
    # (Gemma 4 31B on Google moved to NOT_TRUSTED on 2026-11-17. Requesty's route
    # of it answered 5 of 5 in 8 to 11 s, so it stays trusted.)
    REQUESTY_GEMMA_4_31B,
    # ADDED 2026-10-18, UNSCORED, so below the measured Gemma 4 31B. Qwen first:
    # it is the fast one (3s against 6-12s) and its tools, JSON and big prompts
    # are all tested. Both serve small jobs only - see BAZAARLINK above.
    BAZAARLINK_QWEN_3_7_FLASH,
    BAZAARLINK_DEEPSEEK_V4_FLASH_0731,
    # ADDED 2026-10-23, UNSCORED: see MINISTRAL_8B. Best recall first. Codestral
    # joined them 2026-11-02.
    MINISTRAL_8B,
    MISTRAL_NEMO,
    MINISTRAL_14B,
    CODESTRAL,
    # ADDED 2026-11-02, UNSCORED: AA shows 6 to 24 for Nemotron 3.5 Lightning
    # depending on the page, and none of the Qwen3 Coder pages is on v4.3.2.
    LITEROUTER_QWEN3_CODER_NEXT,
    LITEROUTER_QWEN3_NEXT_80B,
    # ADDED 2026-11-16, UNSCORED (no AA page was found for MiMo V2.5).
    TOKEN_HARBOR_MIMO_V2_5,
    # UNSCORED community finetunes, below the measured Gemma 4 31B on purpose.
    *ROUTEWAY_GEMMA_VARIANTS,
    KILO_NORTH_MINI_CODE,
    NORTH_MINI_CODE,
    GPT_OSS_120B,
    LITEROUTER_GPT_OSS_120B,
    GPT_OSS_120B_GROQ,
    GPT_OSS_20B_GROQ,
    GEMINI_3_1_FLASH_LITE,
    *_other_accounts(GEMINI_3_1_FLASH_LITE),
    # Unscored and the worst on the one question asked of it, so it goes
    # last of the unscored. Then the weakest scored tier we have (AA 9).
    # (Mistral Large 3 left LiteRouter's free list on 2026-11-15.)
    # NOT TRUSTED - see NOT_TRUSTED below. They answer, but not every time: after
    # every trusted tier and before every dead one.
    # Gemma 4 31B on Google, all three keys, moved here 2026-11-17 (three
    # sittings: it passed 2 of 4, then 1 of 3, then 5 of 5, but each call took 36
    # to 66 s, with 500 and 503 "high demand" in the first two sittings). It is
    # trusted in 1 of 3 sittings only. The 26B was trusted again in 2 of 3.
    GEMMA_4_31B,
    *_other_accounts(GEMMA_4_31B),
    ORCAROUTER_GLM_5_3_FLASH,
    ORCAROUTER_DEEPSEEK_V4_1_FLASH,
    ORCAROUTER_DEEPSEEK_V4_FLASH,
    ORCAROUTER_HY3,
    REQUESTY_MUSE_GLIMMER,
    ROUTEWAY_MUSE_GLIMMER,
    # KNOWN DEAD, KEPT ON PURPOSE - see KNOWN_DEAD below. Kilo before its
    # OpenRouter twin even here, so the day one revives the order is right.
    CLINE_GLM_5_3_FLASH,
    LITEROUTER_DEEPSEEK_V4_1_FLASH_STABLE,
    LITEROUTER_DEEPSEEK_V4_PRO,
    ROUTEWAY_DEEPSEEK_V4_FLASH,
    LITEROUTER_GLM_5_2,
    LITEROUTER_MINIMAX_M3,
    LITEROUTER_MINIMAX_M3_CHEAP,
    LITEROUTER_GLM_5,
    LITEROUTER_KIMI_K2_6,
    LITEROUTER_GLM_5_1,
    LITEROUTER_KIMI_K2_7_CODE,
    CLINE_LAGUNA_S_2_1,
    KILO_LAGUNA_S_2_1,
    KILO_QWEN_3_8_27B,
    KILO_INKLING_SMALL,
    KILO_STEP_3_7_FLASH,
    KILO_NEMOTRON_3_SUPER,
    NEMOTRON_3_SUPER,
    KILO_GLM_5_2,
    GLM_5_2,
    KILO_DEEPSEEK_V4_FLASH,
    DEEPSEEK_V4_FLASH,
    MISTRAL_MEDIUM,
    MAGISTRAL_SMALL,
    DEVSTRAL_2,
    # 2026-11-15: nine LiteRouter ids that left its free list.
    LITEROUTER_GLM_5_3_CHEAP,
    LITEROUTER_QWEN_3_8_FLASH,
    LITEROUTER_QWEN_3_8_FLASH_STABLE,
    LITEROUTER_MIMO_V2_6_FLASH,
    LITEROUTER_GLM_5_2_CHEAP,
    LITEROUTER_GLM_5_1_CHEAP,
    LITEROUTER_QWEN3_CODER,
    LITEROUTER_MISTRAL_LARGE_3,
    CLINE_BEAM_1_0,
    KILO_LING_3_1_FLASH,
    LITEROUTER_DEEPSEEK_V4_PRO_STABLE,
    LITEROUTER_DEEPSEEK_V4_FLASH_0731_STABLE,
    LITEROUTER_DEEPSEEK_V4_FLASH_0731,
    LITEROUTER_DEEPSEEK_V4_FLASH_0731_CHEAP,
    LITEROUTER_DEEPSEEK_V3_1,
)

# NOT TRUSTED (defined by the user, 2026-11-16). A tier that is not dead, because
# it DOES answer sometimes, but whose answers FLUCTUATE: it answers once and
# refuses five times, so no route can count on it. Examples: Routeway's Muse
# Glimmer (71 s once, a closed connection the next time) and OrcaRouter's four
# capacity-limited models (429 "free model capacity is limited", Retry-After
# about 3 hours, while the same key got a 200 from Hy4 in the same minute).
#
# The rule is about RELIABILITY, not about the size of the quota: a provider with
# a small but steady allowance is trusted, and a big allowance that is often shut
# is not. Trusted examples: Gemini Flash-Lite, LiteRouter's models, the Mistral
# models, Groq, Cloudflare. A tier enters this list when it answered in some
# calls and failed in others on the smoke test; it leaves after it answers
# reliably on two different days (5 of 5, the way Hy4 did before it was added).
#
# A route uses these tiers LAST: after every trusted tier and before KNOWN_DEAD.
# Never first. As of 2026-11-16, from one smoke test and some direct calls.
NOT_TRUSTED = (
    *(p.name for p in (GEMMA_4_31B, *_other_accounts(GEMMA_4_31B))),
    ORCAROUTER_GLM_5_3_FLASH.name,
    ORCAROUTER_DEEPSEEK_V4_1_FLASH.name,
    ORCAROUTER_DEEPSEEK_V4_FLASH.name,
    ORCAROUTER_HY3.name,
    # Requesty's route answered 4 of 5 on 2026-11-16 but in 170, 101, 36 and 24 s,
    # plus a 504 after 303 s (2.3 s on 2026-11-02): too uneven for any route.
    REQUESTY_MUSE_GLIMMER.name,
    ROUTEWAY_MUSE_GLIMMER.name,
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
# 2026-11-02: TWENTY MORE, found by probing every tier (one call, up to 2
# retries) and re-reading each gateway's own free list. None of these ids is on
# its gateway's free list any more, and each answered an error on every call:
#
#   LiteRouter  403 "model is not available or misspelled" for DeepSeek V4.1
#               Flash stable, V4 Pro (+cheap), V4 Flash, GLM-5.2 (+cheap),
#               MiniMax M3 (+cheap), GLM-5, GLM-5.1, Kimi K2.6 cheap and Kimi
#               K2.7 Code cheap
#   Routeway    400 "No model found: deepseek-v4-flash:free"
#   Cline       Laguna S 2.1 answers HTTP 500 and is no longer on the free list
#   Kilo        404 for Laguna S 2.1, Qwen3.8 27B, Inkling Small, Step 3.7
#               Flash and Nemotron 3 Super
#   OpenRouter  404 "unavailable for free" for Nemotron 3 Super
#
# Gemini 3.8, 3.7 and Gemma 31B were 503 or timeouts the same day; that is
# Google's capacity, so they are NOT listed here.
# 2026-11-03: GLM-5.3 Flash on Cline answers HTTP 402 "insufficient_credits"
# (balance $0.01, total_spent 0). Cline moved it off its free list to Cline
# Pass (cline-pass/glm-5.3-flash), so it now costs credits. The LiteRouter and
# OrcaRouter routes above stay live.
#
# 2026-11-08: THREE REVIVED. LiteRouter's free list was re-read and DeepSeek V4
# Pro cheap, DeepSeek V4 Flash and GLM-5.2 cheap answered a live call again
# (6.4 s, 8.3 s, 6.1 s, first try), so they left this list and moved up the chain.
KNOWN_DEAD = (
    CLINE_GLM_5_3_FLASH.name,
    LITEROUTER_DEEPSEEK_V4_1_FLASH_STABLE.name,
    LITEROUTER_DEEPSEEK_V4_PRO.name,
    ROUTEWAY_DEEPSEEK_V4_FLASH.name,
    LITEROUTER_GLM_5_2.name,
    LITEROUTER_MINIMAX_M3.name,
    LITEROUTER_MINIMAX_M3_CHEAP.name,
    LITEROUTER_GLM_5.name,
    LITEROUTER_KIMI_K2_6.name,
    LITEROUTER_GLM_5_1.name,
    LITEROUTER_KIMI_K2_7_CODE.name,
    CLINE_LAGUNA_S_2_1.name,
    KILO_LAGUNA_S_2_1.name,
    KILO_QWEN_3_8_27B.name,
    KILO_INKLING_SMALL.name,
    KILO_STEP_3_7_FLASH.name,
    KILO_NEMOTRON_3_SUPER.name,
    NEMOTRON_3_SUPER.name,
    KILO_GLM_5_2.name,
    GLM_5_2.name,
    KILO_DEEPSEEK_V4_FLASH.name,
    DEEPSEEK_V4_FLASH.name,
    MISTRAL_MEDIUM.name,
    MAGISTRAL_SMALL.name,
    DEVSTRAL_2.name,
    # 2026-11-15: LiteRouter's GET /v1/models lists 37 ":free" ids and none of
    # these nine is among them (the dashboard agrees). Most were revived on
    # 2026-11-02 or 2026-11-08 and have left again. Qwen3.8 Flash may have been
    # renamed to "qwen-3.8-27b:free"; that id is not probed or added yet.
    LITEROUTER_GLM_5_3_CHEAP.name,
    LITEROUTER_QWEN_3_8_FLASH.name,
    LITEROUTER_QWEN_3_8_FLASH_STABLE.name,
    LITEROUTER_MIMO_V2_6_FLASH.name,
    LITEROUTER_GLM_5_2_CHEAP.name,
    LITEROUTER_GLM_5_1_CHEAP.name,
    LITEROUTER_QWEN3_CODER.name,
    LITEROUTER_MISTRAL_LARGE_3.name,
    # 2026-11-15 (smoke test of every tier): Cline moved Beam 1.0 off its free
    # list (402 insufficient_credits) and Kilo answers 404 for Ling 3.1 Flash.
    # Ling still has a live route on Requesty; Beam has none we use (Kilo lists
    # reflection/beam-free, which is NOT probed or added).
    CLINE_BEAM_1_0.name,
    KILO_LING_3_1_FLASH.name,
    # 2026-11-20: LiteRouter's free list (33 ids) no longer lists these five,
    # and each answered 403 "not available or misspelled". Hy3 is back on the
    # list and answered, so it left this list the same day.
    LITEROUTER_DEEPSEEK_V4_PRO_STABLE.name,
    LITEROUTER_DEEPSEEK_V4_FLASH_0731_STABLE.name,
    LITEROUTER_DEEPSEEK_V4_FLASH_0731.name,
    LITEROUTER_DEEPSEEK_V4_FLASH_0731_CHEAP.name,
    LITEROUTER_DEEPSEEK_V3_1.name,
)

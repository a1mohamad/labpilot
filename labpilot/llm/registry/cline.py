"""The tiers of Cline."""

from __future__ import annotations

from labpilot.llm.cline import ClineProvider

CLINE_URL = "https://api.cline.bot/api/v1/chat/completions"


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
# variant caps output at 32,768 against the 32,000 of the two-file answer: 768 tokens
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

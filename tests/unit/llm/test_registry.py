from pathlib import Path

import pytest

from labpilot.llm import (
    CHAIN,
    ClineProvider,
    GeminiProvider,
    LLMError,
    OpenAICompatibleProvider,
)
from labpilot.prompts import PROMPT_BUDGET, REPORT_MAX_TOKENS

ROOT = Path(__file__).resolve().parents[3]
ENV_EXAMPLE = ROOT / ".env.example"
SMOKE_WORKFLOW = ROOT / ".github" / "workflows" / "smoke.yaml"
KNOWN_THINKING = ("LOW", "MEDIUM", "HIGH")
REJECTS_REASONING = ("Devstral 2",)

# The Gemini-shape twin of REJECTS_REASONING, and it cost a dead tier to find.
# Gemma answers HTTP 400 - "Thinking level is not supported for this model" -
# to every request carrying the field, measured 2026-09-11. It is 14,400
# requests a DAY, the largest generator budget here, and it was broken on every
# call since slice 4 added `thinking`.
REJECTS_THINKING = ("gemma-4-31b-it",)

# Deliberate, measured exceptions. A new name appearing here is a real problem.
# Groq's 8,000 is a TOTAL per-minute budget (prompt + reserved output), so it is
# modelled as a small context_window. Gemma's 16,000 counts input only.
# Qwen3.8 27B (Groq) joined 2026-09-19. Same cause as its Groq sibling: the
# 8,000 is a per-MINUTE budget over prompt AND reserved output, so it can
# never serve a report however large Groq says its context is (131,042).
# It earns its place anyway - _check_fits refuses it locally for nothing,
# and Step 2's small code jobs fit easily at 1,000 requests a day.
OUTPUT_TOO_SMALL = (
    "Qwen3.8 27B (Groq)",
    # GLM-5.2 moved from Mistral to OpenRouter's free tier 2026-09-19 and
    # brought a 32,768 context with it, against the 58,000 a report needs.
    # BOTH routes carry it - the limit belongs to the model's free serving,
    # not to the gateway in front of it.
    "GLM-5.2 (Kilo)",
    "GLM-5.2",
    "GPT-OSS 120B (Groq)",
    "Devstral 2",
)
INPUT_LIMITED = ("gemma-4-31b-it",)

# Cline lists SIX free models and its API serves only these TWO. Measured
# 2026-09-13: the other four answer
#     403 "<model> is only available via Cline product surfaces"
# on every request - cline-free/muse-spark-1.3-contributor, cline-free/solar-pro4,
# cline-free/longcat-2.0 and deepseek/deepseek-v4-flash. The gate is per MODEL,
# not per namespace, so the id alone cannot tell you which side it is on.
#
# The `:free` suffix on Laguna is load-bearing in the other direction: the
# paid id `poolside/laguna-s-2.1` also answers, and spends credits.
CLINE_MODELS_THE_API_SERVES = ("z-ai/glm-5.3-flash", "poolside/laguna-s-2.1:free")


def test_chain_tiers_are_sequential_from_one():
    assert [provider.tier for provider in CHAIN] == list(range(1, len(CHAIN) + 1))


def test_no_single_pool_can_kill_the_whole_chain():
    pools = {provider.api_key_env for provider in CHAIN}

    for dead in pools:
        survivors = [p.name for p in CHAIN if p.api_key_env != dead]
        assert survivors, dead


def test_no_single_pool_can_stop_a_full_report():
    pools = {provider.api_key_env for provider in CHAIN}

    for dead in pools:
        survivors = [
            p.name
            for p in CHAIN
            if p.api_key_env != dead and p.max_output_tokens >= REPORT_MAX_TOKENS
        ]
        assert survivors, dead


def test_the_chain_spans_at_least_three_pools():
    pools = {provider.api_key_env for provider in CHAIN}

    assert len(pools) >= 3, pools


def test_every_chain_env_var_is_documented_in_env_example():
    """Matches a DECLARATION line, not the name anywhere in the file.

    The substring version this replaces could not fail: commenting the
    declaration out left the name in the file, so `CLINE_API_KEY` counted as
    documented while nobody could learn they had to set it. Its sibling in
    test_packaging.py was tightened for exactly this on 2026-08-17 and this
    copy kept the loose shape - and that sibling does not cover these names,
    because a provider reads os.environ[self.api_key_env] through a field, so
    an AST scan never sees the literal.
    """
    declared = {
        line.split("=", 1)[0].strip()
        for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    required = {provider.api_key_env for provider in CHAIN}
    required |= {
        provider.account_env
        for provider in CHAIN
        if getattr(provider, "account_env", None)
    }

    missing = sorted(required - declared)

    assert not missing, missing


def test_every_chain_env_var_is_mapped_in_the_smoke_workflow():
    workflow = SMOKE_WORKFLOW.read_text(encoding="utf-8")
    required = {provider.api_key_env for provider in CHAIN}
    required |= {
        provider.account_env
        for provider in CHAIN
        if getattr(provider, "account_env", None)
    }

    missing = sorted(
        name
        for name in required
        if f"{name}: ${{{{ secrets.{name} }}}}" not in workflow
    )

    assert not missing, missing


def test_every_google_tier_owns_a_pool_of_its_own():
    """Google bills per PROJECT per MODEL, so each (key, model) is its own
    bucket - and the pool has to say so, or one spent model retires the rest.

    Deliberately NOT a rule about the whole chain: OpenRouter really does have
    one account-wide 50/day, so its three tiers SHARE a pool and that sharing
    is correct. A test demanding globally unique pools would be demanding the
    wrong thing - measured, it fails on 5 tiers that are behaving properly.
    """
    google = [p for p in CHAIN if p.api_key_env.startswith("GOOGLE")]
    pools = [p.pool for p in google]

    assert google, "no Google tiers left to check"
    assert len(set(pools)) == len(pools), pools
    assert all(p.pool == f"{p.api_key_env}:{p.model}" for p in google)


def test_a_model_repeats_only_when_it_is_a_second_account():
    """A repeat that is NOT a second account is a copy-paste mistake."""
    seen: dict[str, set[str]] = {}
    for provider in CHAIN:
        seen.setdefault(provider.model, set()).add(provider.api_key_env)

    wrong = {
        model: keys
        for model, keys in seen.items()
        if len(keys) == 1 and [p.model for p in CHAIN].count(model) > 1
    }

    assert not wrong, f"{wrong} repeat on ONE key, so the second is dead weight"


def test_every_chain_provider_declares_its_token_limits():
    missing = [
        provider.name
        for provider in CHAIN
        if not provider.context_window or not provider.max_output_tokens
    ]

    assert not missing, missing


def test_no_provider_promises_more_output_than_its_context_window():
    over = [
        provider.name
        for provider in CHAIN
        if provider.max_output_tokens > provider.context_window
    ]

    assert not over, over


def test_only_known_tiers_cannot_serve_a_full_report():
    unable = [
        provider.name
        for provider in CHAIN
        if provider.max_output_tokens < REPORT_MAX_TOKENS
    ]

    assert unable == list(OUTPUT_TOO_SMALL), unable


def test_only_known_tiers_are_blocked_by_an_input_limit():
    blocked = sorted(
        {provider.model for provider in CHAIN if provider.max_input_tokens is not None}
    )

    assert blocked == sorted(INPUT_LIMITED), blocked


def test_an_input_limited_tier_costs_no_request():
    blocked = [p for p in CHAIN if p.max_input_tokens is not None]
    oversized = "x" * (max(p.max_input_tokens for p in blocked) * 4)

    for provider in blocked:
        with pytest.raises(LLMError, match="input"):
            provider._check_fits(oversized, 1024)


def test_every_tier_we_believe_can_serve_a_report_really_can():
    """OUTPUT_TOO_SMALL names them by FIELD. This checks the RULE.

    test_only_known_tiers_cannot_serve_a_full_report compares
    max_output_tokens against REPORT_MAX_TOKENS, which is one field and not
    what the chain applies. `_check_fits` enforces the SUM - prompt plus
    reserved output against the context window - so a tier with a generous
    max_output and a small CONTEXT passes that test and still cannot serve a
    report: 26,000 of prompt plus 32,000 of output is 58,000.

    GLM-5.2's move to OpenRouter on 2026-09-19 brought exactly that shape, a
    32,768 context, and it was caught by its output cap rather than by the
    limit that actually binds. The next tier like it might not be so lucky -
    it would sit in the report chain, be tried on every report, and fail at
    the provider instead of here.
    """
    prompt = "x" * (PROMPT_BUDGET * 3)
    excused = set(OUTPUT_TOO_SMALL) | {
        provider.name for provider in CHAIN if provider.model in INPUT_LIMITED
    }

    for provider in CHAIN:
        if provider.name in excused:
            continue
        provider._check_fits(prompt, REPORT_MAX_TOKENS)


def test_the_two_qwen_hosts_do_not_share_a_reasoning_value():
    """THE SAME MODEL ON TWO HOSTS TAKES TWO DIFFERENT WORDS, measured.

        Cloudflare  reasoning_effort=high   -> 400 "Supported types are
                                                    xhigh (default), medium,
                                                    and low"
        Groq        reasoning_effort=xhigh  -> 400 "invalid Qwen3.8
                                                    reasoning_effort"
        Groq        reasoning_effort=high   -> 200

    So a tidy-up that gave both the shared OPENAI_REASONING constant would
    make every Cloudflare Qwen call a 400. The chain would swallow it and
    fall through, so nothing would look broken - the tier would simply stop
    existing, at the cost of one request per report.

    This file already records that the same model on two hosts has different
    LIMITS. It also has different PARAMETER VOCABULARY.
    """
    cloudflare = next(p for p in CHAIN if p.name == "Qwen3.8 27B")
    groq = next(p for p in CHAIN if p.name == "Qwen3.8 27B (Groq)")

    # The premise, and the two hosts spell it differently: Cloudflare
    # namespaces its own catalogue with "@cf/".
    assert cloudflare.model.removeprefix("@cf/") == groq.model, (
        "these must be the SAME underlying model, or the finding is about two "
        "different things"
    )
    assert cloudflare.extra_body == {"reasoning_effort": "xhigh"}
    assert groq.extra_body == {"reasoning_effort": "high"}
    assert cloudflare.extra_body != groq.extra_body, (
        "one shared constant would 400 on Cloudflare for every call"
    )


def _thinking_tiers():
    return [
        provider
        for provider in CHAIN
        if isinstance(provider, GeminiProvider)
        and provider.model not in REJECTS_THINKING
    ]


def test_every_gemini_tier_uses_a_thinking_level_google_accepts():
    levels = [provider.thinking for provider in _thinking_tiers()]

    assert levels
    assert all(level in KNOWN_THINKING for level in levels), levels


def test_the_google_tiers_do_not_drift_apart():
    levels = {provider.thinking for provider in _thinking_tiers()}

    assert len(levels) == 1, levels


def test_a_tier_that_rejects_thinking_does_not_ask_for_it():
    """The other half, and the half that was missing.

    Without this, "all Gemini tiers agree" is satisfied again the moment
    somebody puts MEDIUM back on Gemma to tidy up - and tier 8 dies silently
    on every call, which is exactly what happened for weeks.
    """
    asking = [
        provider.name
        for provider in CHAIN
        if isinstance(provider, GeminiProvider)
        and provider.model in REJECTS_THINKING
        and provider.thinking is not None
    ]

    assert not asking, (
        f"{asking} reject a thinking level with HTTP 400 but are configured to "
        f"send one, so every call to them fails. Set thinking=None."
    )


def test_every_cline_tier_is_a_model_the_api_actually_serves():
    """Four of Cline's six free models are API-blocked, and blocked SILENTLY.

    They answer 403 "only available via Cline product surfaces", which the
    chain treats as "next tier" - so the report still arrives and nobody
    notices that a tier is dead weight costing a request on every single call.
    That is exactly how Gemma stayed broken for weeks.

    The gate is per MODEL, not per namespace: deepseek/deepseek-v4-flash is an
    ordinary catalogue id and is still refused, while z-ai/glm-5.3-flash is on
    the same free list and answers. So the id cannot be reasoned about - it has
    to be measured, and the measurement lives in the list above.
    """
    serves = set(CLINE_MODELS_THE_API_SERVES)
    unreachable = [
        provider.name
        for provider in CHAIN
        if isinstance(provider, ClineProvider) and provider.model not in serves
    ]

    assert not unreachable, (
        f"{unreachable} are refused by Cline's API with 403 on every call, so "
        f"they burn a request per report and can never answer. Only "
        f"{sorted(serves)} are served."
    )


def test_the_cline_tiers_do_not_share_a_quota_pool():
    """A decision that otherwise lives only in a comment.

    Whether Cline's free quota is per account or per model is UNKNOWN, and the
    costs of being wrong are asymmetric: sharing a pool when the quota is
    per-model silently loses a whole free tier, while splitting it when the
    quota is per-account wastes one request. So they are split, and that has to
    be defended by something - collapsing them back onto the bare API key would
    otherwise look like tidying up.
    """
    cline = [p for p in CHAIN if isinstance(p, ClineProvider)]
    pools = [p.pool for p in cline]

    assert len(cline) >= 2, "expected more than one Cline tier"
    assert len(set(pools)) == len(pools), pools
    assert all(p.pool == f"{p.api_key_env}:{p.model}" for p in cline), pools


def test_every_tier_that_accepts_reasoning_asks_for_it():
    missing = [
        provider.name
        for provider in CHAIN
        if isinstance(provider, OpenAICompatibleProvider)
        and not provider.extra_body
        and provider.name not in REJECTS_REASONING
    ]

    assert not missing, missing

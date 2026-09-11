from pathlib import Path

import pytest

from labpilot.llm import CHAIN, GeminiProvider, LLMError, OpenAICompatibleProvider
from labpilot.prompts import REPORT_MAX_TOKENS

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
REJECTS_THINKING = ("Gemma 4 31B",)

# Deliberate, measured exceptions. A new name appearing here is a real problem.
# Groq's 8,000 is a TOTAL per-minute budget (prompt + reserved output), so it is
# modelled as a small context_window. Gemma's 16,000 counts input only.
OUTPUT_TOO_SMALL = ("GPT-OSS 120B (Groq)", "Devstral 2")
INPUT_LIMITED = ("Gemma 4 31B",)


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
    documented = ENV_EXAMPLE.read_text(encoding="utf-8")
    required = {provider.api_key_env for provider in CHAIN}
    required |= {
        provider.account_env
        for provider in CHAIN
        if getattr(provider, "account_env", None)
    }

    missing = sorted(name for name in required if name not in documented)

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


def test_chain_models_are_unique():
    models = [provider.model for provider in CHAIN]

    assert len(set(models)) == len(models), models


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
    blocked = [
        provider.name for provider in CHAIN if provider.max_input_tokens is not None
    ]

    assert blocked == list(INPUT_LIMITED), blocked


def test_an_input_limited_tier_costs_no_request():
    blocked = [p for p in CHAIN if p.max_input_tokens is not None]
    oversized = "x" * (max(p.max_input_tokens for p in blocked) * 4)

    for provider in blocked:
        with pytest.raises(LLMError, match="input"):
            provider._check_fits(oversized, 1024)


def _thinking_tiers():
    return [
        provider
        for provider in CHAIN
        if isinstance(provider, GeminiProvider)
        and provider.name not in REJECTS_THINKING
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
        and provider.name in REJECTS_THINKING
        and provider.thinking is not None
    ]

    assert not asking, (
        f"{asking} reject a thinking level with HTTP 400 but are configured to "
        f"send one, so every call to them fails. Set thinking=None."
    )


def test_every_tier_that_accepts_reasoning_asks_for_it():
    missing = [
        provider.name
        for provider in CHAIN
        if isinstance(provider, OpenAICompatibleProvider)
        and not provider.extra_body
        and provider.name not in REJECTS_REASONING
    ]

    assert not missing, missing

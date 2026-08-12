from pathlib import Path

from labpilot.llm import CHAIN

ENV_EXAMPLE = Path(__file__).resolve().parents[3] / ".env.example"


def test_chain_tiers_are_sequential_from_one():
    assert [provider.tier for provider in CHAIN] == list(range(1, len(CHAIN) + 1))


def test_no_two_adjacent_tiers_share_an_api_key():
    pools = [provider.api_key_env for provider in CHAIN]
    adjacent = list(zip(pools, pools[1:], strict=False))

    assert all(first != second for first, second in adjacent), pools


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

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from labpilot.api import ApiConfig, app, create_app
from labpilot.api.startup import configured_providers, validate_provider_keys
from labpilot.llm import CHAIN

KEY = "GOOGLE_API_KEY"


@pytest.mark.skipif(not Path(".env").exists(), reason="needs a local .env file")
def test_importing_the_app_loads_the_env_file():
    """A fresh interpreter, with the key deliberately absent from its
    environment, must still find it after importing the app.

    Shipped broken on 2026-08-17: nothing called load_dotenv, so uvicorn
    started with no credentials and answered 503 on every request. No other
    API test can catch it, because they all replace the LLMClient.
    """
    stripped = {name: value for name, value in os.environ.items() if name != KEY}
    probe = f"import os, labpilot.api; print(bool(os.environ.get({KEY!r})))"

    finished = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        env=stripped,
        check=True,
    )

    assert finished.stdout.strip() == "True"


@pytest.mark.skipif(not Path(".env").exists(), reason="needs a local .env file")
def test_the_environment_wins_over_the_env_file():
    """Render and GitHub Actions supply variables directly. load_dotenv must
    not override them, or a deployed server would read a stale committed
    value instead of the platform's."""
    probe = f"import os, labpilot.api; print(os.environ[{KEY!r}])"

    finished = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        env={**os.environ, KEY: "set-by-the-platform"},
        check=True,
    )

    assert finished.stdout.strip() == "set-by-the-platform"


def test_startup_refuses_to_serve_when_no_tier_has_a_key(monkeypatch):
    for env in {provider.api_key_env for provider in CHAIN}:
        monkeypatch.delenv(env, raising=False)

    with pytest.raises(RuntimeError, match="no provider in the chain"):
        validate_provider_keys()


def test_startup_survives_when_only_some_tiers_have_a_key(monkeypatch):
    for env in {provider.api_key_env for provider in CHAIN}:
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setenv(KEY, "test-key-not-real")

    usable = validate_provider_keys()

    assert usable
    assert len(usable) < len(CHAIN)


def test_configured_providers_reads_the_environment_not_a_cached_value(monkeypatch):
    monkeypatch.delenv(KEY, raising=False)
    before = configured_providers()
    monkeypatch.setenv(KEY, "test-key-not-real")

    assert len(configured_providers()) > len(before)


def test_the_lifespan_puts_the_client_on_app_state(provider_key):
    fresh = create_app()

    with TestClient(fresh):
        assert fresh.state.client is not None
        assert fresh.state.providers

    assert not hasattr(fresh.state, "client"), "shutdown must release it"


def test_the_compare_endpoint_lives_under_the_version_prefix():
    paths = set(app.openapi()["paths"])

    assert f"{ApiConfig.PREFIX}/compare" in paths
    assert "/compare" not in paths


def test_the_probe_endpoints_stay_off_the_version_prefix():
    """An orchestrator's health probe must not need to know the API version."""
    paths = set(app.openapi()["paths"])

    assert "/health" in paths
    assert "/" in paths


def test_the_documented_failures_are_the_ones_the_endpoint_can_raise():
    responses = app.openapi()["paths"][f"{ApiConfig.PREFIX}/compare"]["post"][
        "responses"
    ]

    assert {"200", "413", "422", "503"} <= set(responses)

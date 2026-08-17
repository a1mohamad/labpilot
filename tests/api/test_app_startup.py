"""The app must be runnable straight from `uvicorn labpilot.api:app`.

Every other API test overrides the LLMClient dependency, so none of them ever
reads a provider key. That is exactly how the app shipped on 2026-08-17 with no
load_dotenv() call at all: the tests were green, the import worked, and the
server answered 503 on every request because the chain had no credentials.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from labpilot.api import app

KEY = "GOOGLE_API_KEY"


@pytest.mark.skipif(not Path(".env").exists(), reason="needs a local .env file")
def test_importing_the_app_loads_the_env_file():
    """A fresh interpreter, with the key deliberately absent from its
    environment, must still find it after importing the app."""
    stripped = {name: value for name, value in os.environ.items() if name != KEY}
    probe = f"import os, labpilot.api; print(bool(os.environ.get({KEY!r})))"

    finished = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        env=stripped,
        check=True,
    )

    assert finished.stdout.strip() == "True", (
        "importing labpilot.api did not load .env, so a uvicorn server "
        "would start with no provider keys and answer 503 on every request"
    )


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


def test_the_endpoint_is_registered_under_its_expected_path():
    routes = {route.path: route for route in app.routes}

    assert "/compare" in routes
    assert "POST" in routes["/compare"].methods

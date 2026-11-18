import pytest


@pytest.fixture
def no_sleep(monkeypatch):
    """Nobody really waits: every sleep of the chain is written down instead."""
    slept: list[float] = []
    monkeypatch.setattr("labpilot.llm.chain.time.sleep", slept.append)
    return slept

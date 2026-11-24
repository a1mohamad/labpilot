"""Which way to the database /compare uses, and that it maps its failure."""

import pytest
from fastapi.testclient import TestClient

from labpilot.api import main
from labpilot.api.routers import compare
from labpilot.store import ConnectionFailed, PooledConnection

COMPARE = "/api/v1/compare"


class FakePool:
    def close(self):
        pass


@pytest.fixture
def with_pool(monkeypatch, provider_key):
    monkeypatch.setattr(main, "make_pool", FakePool)

    def never(**_):
        raise AssertionError("a connection was held for the whole question")

    monkeypatch.setattr(compare, "connect", never)
    with TestClient(main.create_app()) as running:
        yield running


def test_with_a_pool_no_connection_is_held_for_the_question(with_pool, monkeypatch):
    seen = []

    def fake_ask(conn, *_, **__):
        seen.append(conn)
        raise ConnectionFailed("gone")

    monkeypatch.setattr("labpilot.api.asking.ask", fake_ask)

    reply = with_pool.post(COMPARE, json={"question": "hi"})

    assert isinstance(seen[0], PooledConnection)
    assert reply.status_code == 503


def test_fast_reaches_ask_and_is_off_by_default(with_pool, monkeypatch):
    seen = []

    def fake_ask(*_, fast, **__):
        seen.append(fast)
        raise ConnectionFailed("stop here")

    monkeypatch.setattr("labpilot.api.asking.ask", fake_ask)
    with_pool.post(COMPARE, json={"question": "hi"})
    with_pool.post(COMPARE, json={"question": "hi", "fast": True})

    assert seen == [False, True]

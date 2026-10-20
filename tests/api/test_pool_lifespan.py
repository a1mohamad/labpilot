from fastapi.testclient import TestClient

from labpilot.api import main
from labpilot.store import NotConfigured


class FakePool:
    def __init__(self):
        self.closed_calls = 0

    def close(self):
        self.closed_calls += 1


def test_the_app_builds_a_pool_at_boot_and_closes_it_at_stop(monkeypatch, provider_key):
    pool = FakePool()
    monkeypatch.setattr(main, "make_pool", lambda: pool)

    with TestClient(main.create_app()) as running:
        assert running.app.state.pool is pool
        assert pool.closed_calls == 0

    assert pool.closed_calls == 1


def test_no_database_url_means_no_pool_and_the_app_still_boots(
    monkeypatch, provider_key
):
    def not_configured():
        raise NotConfigured("DATABASE_URL is not set")

    monkeypatch.setattr(main, "make_pool", not_configured)

    with TestClient(main.create_app()) as running:
        assert running.app.state.pool is None

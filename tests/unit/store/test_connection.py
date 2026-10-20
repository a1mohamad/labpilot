from __future__ import annotations

import psycopg
import pytest

from labpilot.store import (
    POOL_SIZE,
    ConnectionFailed,
    NotConfigured,
    connect,
    database_url,
    make_pool,
)
from labpilot.store import connection as connection_module
from labpilot.store.defaults import CONNECT_TIMEOUT


def test_a_missing_database_url_is_not_configured(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(NotConfigured, match="DATABASE_URL"):
        database_url()


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
def test_a_blank_database_url_is_not_configured(monkeypatch, blank):
    monkeypatch.setenv("DATABASE_URL", blank)
    with pytest.raises(NotConfigured, match="DATABASE_URL"):
        database_url()


def test_a_url_with_surrounding_space_is_returned_stripped(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "  postgresql://u@h:5432/d  ")
    assert database_url() == "postgresql://u@h:5432/d"


def test_a_driver_failure_becomes_our_error_and_keeps_the_cause(monkeypatch):
    def boom(*args, **kwargs):
        raise psycopg.OperationalError("server closed the connection")

    monkeypatch.setattr(psycopg, "connect", boom)

    with pytest.raises(ConnectionFailed) as caught:  # noqa: PT012
        with connect("postgresql://u:p@h:5432/d"):
            pass

    assert isinstance(caught.value.__cause__, psycopg.OperationalError)


def test_our_error_never_repeats_the_url_we_were_given(monkeypatch):
    monkeypatch.setattr(
        psycopg,
        "connect",
        lambda *a, **k: (_ for _ in ()).throw(
            psycopg.OperationalError("connection to server at 1.2.3.4 failed")
        ),
    )
    url = "postgresql://postgres.abc:hunter2SECRET@host.example:5432/postgres"

    with pytest.raises(ConnectionFailed) as caught:  # noqa: PT012
        with connect(url):
            pass

    assert "hunter2SECRET" not in str(caught.value)
    assert url not in str(caught.value)


def test_an_explicit_url_wins_over_the_environment(monkeypatch):
    seen = {}

    def spy(dsn, **kwargs):
        seen["dsn"] = dsn
        raise psycopg.OperationalError("stop here")

    monkeypatch.setattr(psycopg, "connect", spy)
    monkeypatch.setenv("DATABASE_URL", "postgresql://from-env/x")

    with pytest.raises(ConnectionFailed):  # noqa: PT012
        with connect("postgresql://explicit/y"):
            pass

    assert seen["dsn"] == "postgresql://explicit/y"


@pytest.mark.parametrize("asked", [True, False])
def test_the_autocommit_choice_reaches_the_driver(monkeypatch, asked):
    seen = {}

    def spy(dsn, **kwargs):
        seen.update(kwargs)
        raise psycopg.OperationalError("stop here")

    monkeypatch.setattr(psycopg, "connect", spy)

    with pytest.raises(ConnectionFailed):  # noqa: PT012
        with connect("postgresql://u:p@h:5432/d", autocommit=asked):
            pass

    assert seen["autocommit"] is asked


def test_a_connection_is_not_autocommit_unless_someone_asks(monkeypatch):
    seen = {}

    def spy(dsn, **kwargs):
        seen.update(kwargs)
        raise psycopg.OperationalError("stop here")

    monkeypatch.setattr(psycopg, "connect", spy)

    with pytest.raises(ConnectionFailed):  # noqa: PT012
        with connect("postgresql://u:p@h:5432/d"):
            pass

    assert seen["autocommit"] is False


def test_a_pool_is_built_closed_with_the_planned_size_and_a_health_check(monkeypatch):
    seen = {}

    class FakePool:
        check_connection = staticmethod(lambda conn: None)

        def __init__(self, url, **kwargs):
            seen["url"] = url
            seen.update(kwargs)

    monkeypatch.setattr(connection_module, "ConnectionPool", FakePool)

    make_pool("postgresql://u@h:5432/d")

    assert seen["url"] == "postgresql://u@h:5432/d"
    assert seen["min_size"] == POOL_SIZE
    assert seen["max_size"] == POOL_SIZE
    assert seen["open"] is False
    assert seen["kwargs"] == {"autocommit": True, "connect_timeout": CONNECT_TIMEOUT}
    assert seen["check"] is FakePool.check_connection


def test_a_pool_without_a_database_url_is_not_configured(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(NotConfigured, match="DATABASE_URL"):
        make_pool()

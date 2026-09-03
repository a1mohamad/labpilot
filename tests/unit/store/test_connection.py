from __future__ import annotations

import psycopg
import pytest

from labpilot.store import ConnectionFailed, NotConfigured, connect, database_url


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

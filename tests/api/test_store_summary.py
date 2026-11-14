import logging

import pytest

from labpilot.api import saved as saved_module
from labpilot.api import summaries
from labpilot.api.chains import SUMMARY_MODELS
from labpilot.api.errors import GenerationUnavailable, StorageUnavailable
from labpilot.api.saved import summary_key
from labpilot.api.summaries import (
    SUMMARY_READ_SECONDS,
    SUMMARY_TOTAL_SECONDS,
    store_summary,
    summary_chain,
)
from labpilot.llm import CHAIN, LLMClient


def a_database(monkeypatch):
    rows = {}
    monkeypatch.setattr(
        saved_module,
        "read_saved",
        lambda conn, key: rows[key][:2] if key in rows else None,
    )
    monkeypatch.setattr(
        saved_module,
        "write_saved",
        lambda conn, key, kind, payload, *, artifacts: rows.update(
            {key: (kind, payload, artifacts)}
        ),
    )
    return rows


def a_summarizer(monkeypatch, function):
    monkeypatch.setattr(summaries, "make_summarizer", lambda conn, client: function)


def test_the_summary_is_made_and_saved_for_its_file(monkeypatch):
    rows = a_database(monkeypatch)
    calls = []
    a_summarizer(monkeypatch, lambda artifact_id: calls.append(artifact_id) or "s")

    assert store_summary("conn", "client", "A-1") is True

    assert calls == ["A-1"]
    assert rows[summary_key("A-1")][2] == ("A-1",)


def test_a_summary_that_is_already_saved_is_not_made_again(monkeypatch):
    a_database(monkeypatch)
    calls = []
    a_summarizer(monkeypatch, lambda artifact_id: calls.append(artifact_id) or "s")

    store_summary("conn", "client", "A-1")
    store_summary("conn", "client", "A-1")

    assert calls == ["A-1"]


def test_when_every_tier_fails_nothing_is_saved_and_it_says_so(monkeypatch, caplog):
    rows = a_database(monkeypatch)

    def exhausted(artifact_id):
        raise GenerationUnavailable("every free tier failed", attempts=())

    a_summarizer(monkeypatch, exhausted)

    with caplog.at_level(logging.WARNING):
        assert store_summary("conn", "client", "A-1") is False

    assert rows == {}
    assert "A-1" in caplog.text


def test_a_database_that_cannot_be_read_does_not_stop_the_upload(monkeypatch):
    rows = a_database(monkeypatch)

    def unreadable(artifact_id):
        raise StorageUnavailable("could not read the parts")

    a_summarizer(monkeypatch, unreadable)

    assert store_summary("conn", "client", "A-1") is False
    assert rows == {}


def test_a_bug_in_our_own_code_is_not_hidden(monkeypatch):
    a_database(monkeypatch)

    def broken(artifact_id):
        raise RuntimeError("a bug")

    a_summarizer(monkeypatch, broken)

    with pytest.raises(RuntimeError):
        store_summary("conn", "client", "A-1")


def test_the_summary_chain_is_the_short_one_with_time_limits():
    short = summary_chain(LLMClient(chain=CHAIN))

    assert {p.model for p in short.chain} == set(SUMMARY_MODELS)
    assert short.total_budget == SUMMARY_TOTAL_SECONDS
    assert short.max_retries_per_tier == 0
    timed = [p for p in short.chain if hasattr(p, "timeout")]
    assert timed
    assert all(p.timeout[1] == SUMMARY_READ_SECONDS for p in timed)


def test_the_summary_after_the_upload_uses_the_short_chain(monkeypatch):
    a_database(monkeypatch)
    clients = []
    monkeypatch.setattr(
        summaries,
        "make_summarizer",
        lambda conn, client: clients.append(client) or (lambda artifact_id: "s"),
    )

    store_summary("conn", LLMClient(chain=CHAIN), "A-1")

    assert {p.model for p in clients[0].chain} == set(SUMMARY_MODELS)
    assert clients[0].total_budget == SUMMARY_TOTAL_SECONDS

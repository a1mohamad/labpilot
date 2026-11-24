import logging

import pytest

from labpilot.agent import Correspondence
from labpilot.api import asking
from labpilot.api import saved as saved_module
from labpilot.api.errors import GenerationUnavailable, UnknownArtifactId
from labpilot.api.prompting import build_answer_prompt
from labpilot.llm import CHAIN, LLMClient, routes


def capture(monkeypatch):
    seen = {}

    def fake_build_graph(**kwargs):
        seen.update(kwargs)
        return "the graph"

    monkeypatch.setattr(asking, "build_graph", fake_build_graph)
    monkeypatch.setattr(asking, "make_planner", lambda conn, client: "planner")
    return seen


def summarizer(monkeypatch, function):
    # The stored summaries (D110) are real here; only the database is a dict.
    rows = {}
    monkeypatch.setattr(saved_module, "read_saved", lambda conn, key: rows.get(key))
    monkeypatch.setattr(
        saved_module,
        "write_saved",
        lambda conn, key, kind, payload, *, artifacts: rows.update(
            {key: (kind, payload)}
        ),
    )
    monkeypatch.setattr(asking, "make_summarizer", lambda conn, client: function)
    return rows


def test_the_graph_gets_a_summarize_function(monkeypatch):
    seen = capture(monkeypatch)

    asking._ask_graph("conn", "client")

    assert callable(seen["summarize"])


def test_a_summary_comes_from_the_summarizer(monkeypatch):
    seen = capture(monkeypatch)
    summarizer(monkeypatch, lambda artifact_id: f"summary of {artifact_id}")
    asking._ask_graph("conn", "client")

    assert seen["summarize"]("A-1") == "summary of A-1"


def test_when_every_tier_fails_the_report_goes_on_without_that_summary(
    monkeypatch, caplog
):
    def exhausted(artifact_id):
        raise GenerationUnavailable("every free tier failed", attempts=())

    seen = capture(monkeypatch)
    summarizer(monkeypatch, exhausted)
    asking._ask_graph("conn", "client")

    with caplog.at_level(logging.WARNING):
        summary = seen["summarize"]("A-1")

    assert summary == ""
    assert "A-1" in caplog.text


def test_a_missing_artifact_is_still_an_error_and_not_a_missing_summary(monkeypatch):
    def unknown(artifact_id):
        raise UnknownArtifactId(artifact_id)

    seen = capture(monkeypatch)
    summarizer(monkeypatch, unknown)
    asking._ask_graph("conn", "client")

    with pytest.raises(UnknownArtifactId):
        seen["summarize"]("A-1")


def test_the_graph_gets_the_one_prompt_builder_for_every_number_of_files(
    monkeypatch,
):
    seen = capture(monkeypatch)

    asking._ask_graph("conn", "client")

    assert seen["make_prompt"] is build_answer_prompt
    assert "make_answer_prompt" not in seen


def test_a_stored_summary_is_read_and_the_model_is_not_asked_again(monkeypatch):
    seen = capture(monkeypatch)
    calls = []
    summarizer(monkeypatch, lambda artifact_id: calls.append(artifact_id) or "stored")
    asking._ask_graph("conn", "client")

    assert seen["summarize"]("A-1") == "stored"
    assert seen["summarize"]("A-1") == "stored"
    assert calls == ["A-1"]


def test_a_summary_that_failed_is_asked_for_again_on_the_next_message(monkeypatch):
    seen = capture(monkeypatch)
    calls = []

    def exhausted(artifact_id):
        calls.append(artifact_id)
        raise GenerationUnavailable("every free tier failed", attempts=())

    rows = summarizer(monkeypatch, exhausted)
    asking._ask_graph("conn", "client")

    assert seen["summarize"]("A-1") == ""
    assert seen["summarize"]("A-1") == ""
    assert calls == ["A-1", "A-1"]
    assert rows == {}


def test_the_summarizer_is_given_the_short_summary_chain(monkeypatch):
    seen = capture(monkeypatch)
    clients = []
    monkeypatch.setattr(
        asking,
        "make_summarizer",
        lambda conn, client: clients.append(client) or (lambda artifact_id: "s"),
    )
    asking._ask_graph("conn", LLMClient(chain=CHAIN))

    assert [p.name for p in clients[0].chain] == [
        p.name for p in routes.resolve("summary", CHAIN)
    ]
    assert callable(seen["summarize"])


def test_a_stored_verdict_is_read_and_the_gate_is_not_asked_again(monkeypatch):
    seen = capture(monkeypatch)
    summarizer(monkeypatch, lambda artifact_id: "s")
    calls = []
    monkeypatch.setattr(
        asking,
        "make_gate",
        lambda client: (
            lambda summary_a, summary_b: (
                calls.append((summary_a, summary_b))
                or Correspondence("FULL", "same work")
            )
        ),
    )
    asking._ask_graph("conn", "client")

    first = seen["gate"]("A-1", "B-1", "about memory", "about memory too")
    second = seen["gate"]("A-1", "B-1", "about memory", "about memory too")

    assert first == second == Correspondence("FULL", "same work")
    assert calls == [("about memory", "about memory too")]

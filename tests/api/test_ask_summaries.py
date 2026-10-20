import logging

import pytest

from labpilot.api import asking
from labpilot.api.errors import GenerationUnavailable, UnknownArtifactId


def capture(monkeypatch):
    seen = {}

    def fake_build_graph(**kwargs):
        seen.update(kwargs)
        return "the graph"

    monkeypatch.setattr(asking, "build_graph", fake_build_graph)
    monkeypatch.setattr(asking, "make_planner", lambda conn, client: "planner")
    return seen


def summarizer(monkeypatch, function):
    monkeypatch.setattr(asking, "make_summarizer", lambda conn, client: function)


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


def test_the_prompt_builder_gets_the_summaries(monkeypatch):
    calls = []
    monkeypatch.setattr(
        asking,
        "build_report_prompt",
        lambda chunks, **kwargs: calls.append(kwargs) or ("the prompt", ()),
    )
    seen = capture(monkeypatch)
    asking._ask_graph("conn", "client")

    seen["make_prompt"]("chunks", "why?", {"A": 1}, {"A": "sa"})

    assert calls == [{"question": "why?", "totals": {"A": 1}, "summaries": {"A": "sa"}}]

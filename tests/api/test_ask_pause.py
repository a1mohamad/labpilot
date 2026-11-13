"""ask() when the graph pauses to ask the person a question (D109).

A fake graph stands in for the real one, as in test_ask_graph.py: what is
checked is what ask() does with a pause and with a reply.
"""

from __future__ import annotations

import pytest
from langgraph.types import Command, Interrupt

from labpilot.api import asking
from labpilot.api.contracts import Comparison, Question
from labpilot.api.errors import NothingToAnswer


class PausedGraph:
    """Pauses on the first call; finishes on the second."""

    def __init__(self, waiting=True):
        self.calls = []
        self.waiting = waiting

    def get_state(self, config):
        return type("Snapshot", (), {"next": ("respond",) if self.waiting else ()})()

    def invoke(self, given, config=None, **kwargs):
        self.calls.append((given, config, kwargs))
        if isinstance(given, Command):
            return {
                "result": "the report",
                "chunks": (),
                "selected": (),
                "prompt": "p",
                "totals": None,
            }
        return {"__interrupt__": [Interrupt(value={"question": "What F1?"}, id="x")]}


def use(monkeypatch, graph):
    built = []

    def fake_ask_graph(conn, client, thread_id=None, pool=None, **_):
        built.append(thread_id)
        return graph

    monkeypatch.setattr(asking, "_ask_graph", fake_ask_graph)
    monkeypatch.setattr(asking, "prune", lambda conn, thread_id: None)
    return built


def test_a_paused_graph_gives_back_the_question_not_a_comparison(monkeypatch):
    use(monkeypatch, PausedGraph())

    out = asking.ask(None, "A-1", "B-1", question="why?", client=None, thread_id="c")

    assert out == Question(text="What F1?")


def test_a_reply_resumes_the_saved_run_instead_of_starting_a_new_one(monkeypatch):
    graph = PausedGraph()
    use(monkeypatch, graph)

    out = asking.ask(
        None, "A-1", "B-1", question="why?", client=None, thread_id="c", reply="0.82"
    )

    given, config, kwargs = graph.calls[0]
    assert given == Command(resume="0.82")
    assert config == {"configurable": {"thread_id": "c"}}
    assert kwargs == {"durability": "exit"}
    assert isinstance(out, Comparison)


def test_a_skip_is_sent_as_the_empty_text_and_never_as_none(monkeypatch):
    graph = PausedGraph()
    use(monkeypatch, graph)

    asking.ask(
        None, "A-1", "B-1", question="why?", client=None, thread_id="c", reply=""
    )

    assert graph.calls[0][0] == Command(resume="")


def test_the_old_copies_are_cleaned_after_a_pause_too(monkeypatch):
    use(monkeypatch, PausedGraph())
    cleaned = []
    monkeypatch.setattr(
        asking, "prune", lambda conn, thread_id: cleaned.append(thread_id)
    )

    asking.ask(None, "A-1", "B-1", question="why?", client=None, thread_id="c")

    assert cleaned == ["c"]


def test_a_reply_to_a_chat_that_is_not_waiting_is_refused_not_answered_again(
    monkeypatch,
):
    graph = PausedGraph(waiting=False)
    use(monkeypatch, graph)

    with pytest.raises(NothingToAnswer):
        asking.ask(
            None, "A-1", "B-1", question="why?", client=None, thread_id="c", reply="0.8"
        )

    assert graph.calls == []

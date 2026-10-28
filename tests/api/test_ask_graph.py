import logging

import psycopg
import pytest

from labpilot.api import asking
from labpilot.api.errors import InvalidQuestion


class FakeGraph:
    def __init__(self, events=None):
        self.events = events if events is not None else []
        self.calls = []

    def invoke(self, state, config=None, **kwargs):
        self.events.append("invoke")
        self.calls.append((state, config, kwargs))
        return {
            "result": "the result",
            "chunks": ("c1", "c2"),
            "selected": ("c1",),
            "prompt": "the prompt",
            "totals": {"A": 5},
        }


def use(monkeypatch, graph):
    built = []

    def fake_ask_graph(conn, client, thread_id=None, pool=None):
        built.append(thread_id)
        return graph

    monkeypatch.setattr(asking, "_ask_graph", fake_ask_graph)
    return built


def test_ask_runs_the_graph_and_builds_the_comparison_from_its_state(monkeypatch):
    graph = FakeGraph()
    use(monkeypatch, graph)

    comparison = asking.ask(None, "A-1", "B-1", question="why?", client=None)

    assert graph.calls[0][0] == {"question": "why?", "a": "A-1", "b": "B-1"}
    assert comparison.result == "the result"
    assert comparison.chunks == ("c1", "c2")
    assert comparison.selected == ("c1",)
    assert comparison.prompt == "the prompt"
    assert comparison.totals == {"A": 5}


def test_a_chat_id_becomes_the_thread_and_the_graph_saves_once_at_the_end(monkeypatch):
    graph = FakeGraph()
    built = use(monkeypatch, graph)
    monkeypatch.setattr(asking, "prune", lambda conn, thread_id: None)

    asking.ask(None, "A-1", "B-1", question="why?", client=None, thread_id="chat-7")

    _, config, kwargs = graph.calls[0]
    assert config == {"configurable": {"thread_id": "chat-7"}}
    assert kwargs == {"durability": "exit"}
    assert built == ["chat-7"]


def test_the_old_copies_are_deleted_after_the_answer_and_not_before(monkeypatch):
    events = []
    use(monkeypatch, FakeGraph(events))
    monkeypatch.setattr(
        asking, "prune", lambda conn, thread_id: events.append(("prune", thread_id))
    )

    asking.ask(None, "A-1", "B-1", question="why?", client=None, thread_id="chat-7")

    assert events == ["invoke", ("prune", "chat-7")]


def test_a_question_with_no_chat_saves_nothing_and_deletes_nothing(monkeypatch):
    graph = FakeGraph()
    built = use(monkeypatch, graph)
    monkeypatch.setattr(
        asking, "prune", lambda *a: pytest.fail("there is no chat to clean")
    )

    asking.ask(None, "A-1", "B-1", question="why?", client=None)

    assert graph.calls[0][1:] == (None, {})
    assert built == [None]


def test_a_failed_clean_up_is_logged_and_the_answer_still_arrives(monkeypatch, caplog):
    use(monkeypatch, FakeGraph())

    def broken(conn, thread_id):
        raise psycopg.OperationalError("server closed the connection")

    monkeypatch.setattr(asking, "prune", broken)

    with caplog.at_level(logging.WARNING):
        comparison = asking.ask(
            None, "A-1", "B-1", question="why?", client=None, thread_id="chat-7"
        )

    assert comparison.result == "the result"
    assert "chat-7" in caplog.text


@pytest.mark.parametrize("question", ["", "   "])
def test_a_blank_question_is_refused_before_the_graph_is_built(monkeypatch, question):
    def built(conn, client, thread_id=None):
        raise AssertionError("the graph must not be built for a blank question")

    monkeypatch.setattr(asking, "_ask_graph", built)

    with pytest.raises(InvalidQuestion):
        asking.ask(None, "A-1", "B-1", question=question, client=None)


class FakePool:
    def __init__(self, closed=False):
        self.closed = closed
        self.opened = False

    def open(self, wait=True):
        self.opened = True
        self.closed = False


def test_with_a_pool_the_old_copies_are_deleted_through_the_pool(monkeypatch):
    use(monkeypatch, FakeGraph())
    places = []
    monkeypatch.setattr(asking, "prune", lambda place, thread_id: places.append(place))
    pool = FakePool(closed=True)

    asking.ask(
        "the request connection",
        "A-1",
        "B-1",
        question="why?",
        client=None,
        thread_id="chat-7",
        pool=pool,
    )

    assert places == [pool]
    assert pool.opened


def test_without_a_pool_the_request_connection_is_used(monkeypatch):
    use(monkeypatch, FakeGraph())
    places = []
    monkeypatch.setattr(asking, "prune", lambda place, thread_id: places.append(place))

    asking.ask(
        "the request connection",
        "A-1",
        "B-1",
        question="why?",
        client=None,
        thread_id="chat-7",
    )

    assert places == ["the request connection"]


def test_the_chat_is_saved_through_the_pool_and_not_the_idle_connection(monkeypatch):
    # The save runs after a report of many minutes; the request's connection was
    # seen closed by then (2026-10-25). A pool checks its connection first.
    saved_on = []
    monkeypatch.setattr(asking, "open_saver", lambda place: saved_on.append(place))
    pool = FakePool()

    asking._ask_graph("the request connection", "client", "chat-7", pool)

    assert saved_on == [pool]

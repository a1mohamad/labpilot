from contextlib import contextmanager
from types import SimpleNamespace

from labpilot.agent import Query
from labpilot.api import asking
from labpilot.api.searching import rank_pile


class FakePool:
    def __init__(self, *, closed=True):
        self.closed = closed
        self.opened = []

    def open(self, wait):
        self.opened.append(wait)
        self.closed = False

    @contextmanager
    def connection(self):
        yield "pooled"


def capture(monkeypatch):
    seen = {}

    def fake_build_graph(**kwargs):
        seen.update(kwargs)
        return "the graph"

    monkeypatch.setattr(asking, "build_graph", fake_build_graph)
    monkeypatch.setattr(
        asking, "make_planner", lambda conn, client: ("planner", conn, client)
    )
    monkeypatch.setattr(asking, "embed_query", lambda sides, *, side, text: (1.0,))
    return seen


def test_the_graph_gets_the_fan_out_functions_and_not_the_old_search(monkeypatch):
    seen = capture(monkeypatch)

    asking._ask_graph("conn", "client")

    assert {"search_one", "totals_of", "rank_side", "plan"} <= set(seen)
    assert "search" not in seen
    assert seen["rank_side"] is rank_pile
    assert seen["plan"] == ("planner", "conn", "client")


def test_without_a_pool_a_search_uses_the_shared_connection(monkeypatch):
    seen = capture(monkeypatch)
    calls = []

    def fake_retrieve(conn, sides, *, side, text):
        calls.append((conn, sides, side, text))
        return ("found",)

    monkeypatch.setattr(asking, "retrieve_query", fake_retrieve)
    asking._ask_graph("conn", "client")

    found = seen["search_one"]("the sides", Query("B", "clip"))

    assert found == ("found",)
    assert calls == [("conn", "the sides", "B", "clip")]


def test_with_a_pool_a_search_takes_a_pooled_connection_and_not_the_shared_one(
    monkeypatch,
):
    seen = capture(monkeypatch)
    used = []
    monkeypatch.setattr(
        asking,
        "retrieve_query",
        lambda conn, sides, *, side, text, vector: used.append(conn) or ("found",),
    )
    asking._ask_graph("conn", "client", pool=FakePool())

    seen["search_one"]("the sides", Query("A", "lr"))

    assert used == ["pooled"]


class EventPool(FakePool):
    def __init__(self, events, dead=0):
        super().__init__(closed=False)
        self.events = events
        self.dead = dead

    @contextmanager
    def connection(self):
        self.events.append("take")
        yield "pooled"
        self.events.append("give back")


def test_the_query_is_embedded_before_a_pooled_connection_is_taken(monkeypatch):
    # R16: the pool is not held while the embedder answers.
    seen = capture(monkeypatch)
    events = []

    def embed(sides, *, side, text):
        events.append("embed")
        return (0.5,)

    def retrieve(conn, sides, *, side, text, vector):
        events.append(("search", vector))
        return ()

    monkeypatch.setattr(asking, "embed_query", embed)
    monkeypatch.setattr(asking, "retrieve_query", retrieve)
    asking._ask_graph("conn", "client", pool=EventPool(events))

    seen["search_one"]("the sides", Query("A", "lr"))

    assert events == ["embed", "take", ("search", (0.5,)), "give back"]


def test_a_pooled_connection_that_dies_mid_search_is_replaced_once(monkeypatch):
    import psycopg

    seen = capture(monkeypatch)
    tries = []

    def retrieve(conn, sides, *, side, text, vector):
        tries.append(conn)
        if len(tries) == 1:
            raise psycopg.OperationalError("SSL SYSCALL error: EOF detected")
        return ("found",)

    monkeypatch.setattr(asking, "retrieve_query", retrieve)
    asking._ask_graph("conn", "client", pool=EventPool([]))

    assert seen["search_one"]("the sides", Query("A", "lr")) == ("found",)
    assert len(tries) == 2


def test_a_second_dead_connection_is_raised(monkeypatch):
    import psycopg
    import pytest

    seen = capture(monkeypatch)

    def retrieve(conn, sides, *, side, text, vector):
        raise psycopg.OperationalError("server closed the connection")

    monkeypatch.setattr(asking, "retrieve_query", retrieve)
    asking._ask_graph("conn", "client", pool=EventPool([]))

    with pytest.raises(psycopg.OperationalError):
        seen["search_one"]("the sides", Query("A", "lr"))


def test_a_closed_pool_is_opened_on_the_first_search_without_waiting(monkeypatch):
    seen = capture(monkeypatch)
    monkeypatch.setattr(asking, "retrieve_query", lambda *a, **k: ())
    pool = FakePool(closed=True)
    asking._ask_graph("conn", "client", pool=pool)

    seen["search_one"]("the sides", Query("A", "lr"))
    seen["search_one"]("the sides", Query("B", "seed"))

    assert pool.opened == [False]


def test_an_open_pool_is_not_opened_again(monkeypatch):
    seen = capture(monkeypatch)
    monkeypatch.setattr(asking, "retrieve_query", lambda *a, **k: ())
    pool = FakePool(closed=False)
    asking._ask_graph("conn", "client", pool=pool)

    seen["search_one"]("the sides", Query("A", "lr"))

    assert pool.opened == []


def test_the_totals_are_what_each_artifact_holds(monkeypatch):
    seen = capture(monkeypatch)
    asking._ask_graph("conn", "client")
    sides = {"A": SimpleNamespace(chunks=5), "B": SimpleNamespace(chunks=900)}

    assert seen["totals_of"](sides) == {"A": 5, "B": 900}


def test_ask_gives_the_graph_builder_the_pool(monkeypatch):
    built = []

    class Graph:
        def invoke(self, state, config=None, **kwargs):
            return {
                "result": "r",
                "chunks": (),
                "selected": (),
                "prompt": "p",
                "totals": None,
            }

    def fake_ask_graph(conn, client, thread_id=None, pool=None):
        built.append(pool)
        return Graph()

    monkeypatch.setattr(asking, "_ask_graph", fake_ask_graph)

    asking.ask(None, "A-1", "B-1", question="why?", client=None, pool="the pool")

    assert built == ["the pool"]

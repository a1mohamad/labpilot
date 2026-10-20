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
        lambda conn, sides, *, side, text: used.append(conn) or ("found",),
    )
    asking._ask_graph("conn", "client", pool=FakePool())

    seen["search_one"]("the sides", Query("A", "lr"))

    assert used == ["pooled"]


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

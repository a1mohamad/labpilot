import pytest

from labpilot.api import services
from labpilot.api.errors import InvalidQuestion


class FakeGraph:
    def __init__(self):
        self.received = None

    def invoke(self, state):
        self.received = state
        return {
            "result": "the result",
            "chunks": ("c1", "c2"),
            "selected": ("c1",),
            "prompt": "the prompt",
            "totals": {"A": 5},
        }


def test_ask_runs_the_graph_and_builds_the_comparison_from_its_state(monkeypatch):
    graph = FakeGraph()
    monkeypatch.setattr(services, "_ask_graph", lambda conn, client: graph)

    comparison = services.ask(None, "A-1", "B-1", question="why?", client=None)

    assert graph.received == {"question": "why?", "a": "A-1", "b": "B-1"}
    assert comparison.result == "the result"
    assert comparison.chunks == ("c1", "c2")
    assert comparison.selected == ("c1",)
    assert comparison.prompt == "the prompt"
    assert comparison.totals == {"A": 5}


@pytest.mark.parametrize("question", ["", "   "])
def test_a_blank_question_is_refused_before_the_graph_is_built(monkeypatch, question):
    def built(conn, client):
        raise AssertionError("the graph must not be built for a blank question")

    monkeypatch.setattr(services, "_ask_graph", built)

    with pytest.raises(InvalidQuestion):
        services.ask(None, "A-1", "B-1", question=question, client=None)

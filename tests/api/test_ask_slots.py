import pytest

from labpilot.api import asking


class RecordingGraph:
    def __init__(self):
        self.started = []

    def invoke(self, start, *args, **kwargs):
        self.started.append(start)
        return {
            "result": "an answer",
            "chunks": (),
            "selected": (),
            "prompt": "a prompt",
            "totals": None,
        }


@pytest.fixture
def graph(monkeypatch):
    recording = RecordingGraph()
    monkeypatch.setattr(asking, "_ask_graph", lambda *args, **kwargs: recording)
    return recording


@pytest.mark.parametrize(
    ("a", "b", "slots"),
    [
        ("", "", ("", "")),
        ("A-1", "", ("A-1", "")),
        ("", "A-1", ("A-1", "")),
        ("B-1", "", ("", "B-1")),
        ("", "B-1", ("", "B-1")),
        ("A-1", "B-1", ("A-1", "B-1")),
        ("B-1", "A-1", ("B-1", "A-1")),
        ("typo", "", ("typo", "")),
    ],
    ids=[
        "none",
        "reference alone, right slot",
        "reference alone, wrong slot",
        "subject alone, wrong slot",
        "subject alone, right slot",
        "two ids stay as sent",
        "two swapped ids stay as sent",
        "unknown id stays, so the lookup says 404",
    ],
)
def test_a_lone_artifact_reaches_the_graph_in_the_slot_of_its_own_side(
    graph, a, b, slots
):
    asking.ask(object(), a, b, question="why?", client=object())

    assert (graph.started[0]["a"], graph.started[0]["b"]) == slots

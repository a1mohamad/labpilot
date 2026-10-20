import threading

import pytest

from labpilot.agent import build_graph
from labpilot.agent.summarize import make_summarize_node

STUFFED = ("whole one", "whole two")


class Boom(Exception):
    pass


def run(summarize=None):
    graph = build_graph(
        measure=lambda a, b: object(),
        fits=lambda sides, question: True,
        stuff=lambda sides, question: (STUFFED, None),
        search=lambda sides, question: (STUFFED, {"A": 1}),
        make_prompt=lambda chunks, question, totals, summaries: (
            "the prompt",
            chunks[:1],
        ),
        generate=lambda prompt: "the result",
        summarize=summarize,
    )
    return graph.invoke({"question": "why?", "a": "A-1", "b": "B-1"})


def test_a_node_summarizes_the_artifact_of_its_own_side():
    seen = []

    def summarize(artifact_id):
        seen.append(artifact_id)
        return f"summary of {artifact_id}"

    state = {"a": "A-1", "b": "B-1"}

    assert make_summarize_node("a", summarize)(state) == {"summary_a": "summary of A-1"}
    assert make_summarize_node("b", summarize)(state) == {"summary_b": "summary of B-1"}
    assert seen == ["A-1", "B-1"]


def test_both_summaries_reach_the_final_state_and_the_answer_still_runs():
    final = run(lambda artifact_id: f"summary of {artifact_id}")

    assert final["summary_a"] == "summary of A-1"
    assert final["summary_b"] == "summary of B-1"
    assert final["result"] == "the result"


def test_the_two_summaries_run_at_the_same_time():
    barrier = threading.Barrier(2, timeout=2)

    def summarize(artifact_id):
        barrier.wait()
        return artifact_id

    final = run(summarize)

    assert final["summary_a"] == "A-1"
    assert final["summary_b"] == "B-1"


def test_a_graph_built_without_summarize_has_no_summaries():
    final = run()

    assert "summary_a" not in final
    assert "summary_b" not in final
    assert final["result"] == "the result"


def test_an_error_in_a_summary_reaches_the_caller_unchanged():
    def summarize(artifact_id):
        raise Boom(artifact_id)

    with pytest.raises(Boom):
        run(summarize)

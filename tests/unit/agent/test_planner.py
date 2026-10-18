import time

import pytest

from labpilot.agent import Plan, Query, build_graph
from labpilot.agent.planner import make_planner_node

PLAN = Plan(
    steps=("extract_claims", "find_bugs"),
    queries=(Query("A", "gradient clipping value"), Query("B", "CLIP_NORM")),
)


class Boom(Exception):
    pass


def run(plan=None, order=None):
    order = [] if order is None else order

    def measure(a, b):
        order.append("measure")
        return object()

    graph = build_graph(
        measure=measure,
        fits=lambda sides, question: True,
        stuff=lambda sides, question: (("whole",), None),
        search=lambda sides, question: (("found",), {"A": 1}),
        make_prompt=lambda chunks, question, totals: ("the prompt", chunks[:1]),
        generate=lambda prompt: "the result",
        plan=plan,
    )
    return graph.invoke({"question": "why?", "a": "A-1", "b": "B-1"})


def test_a_node_asks_for_a_plan_with_the_question_and_both_artifacts():
    seen = []

    def plan(question, a, b):
        seen.append((question, a, b))
        return PLAN

    state = {"question": "why?", "a": "A-1", "b": "B-1"}

    assert make_planner_node(plan)(state) == {"plan": PLAN}
    assert seen == [("why?", "A-1", "B-1")]


def test_the_plan_reaches_the_final_state_and_the_answer_still_runs():
    final = run(lambda question, a, b: PLAN)

    assert final["plan"] == PLAN
    assert final["result"] == "the result"


def test_the_planner_runs_before_anything_reads_the_artifacts():
    order = []

    def plan(question, a, b):
        time.sleep(0.05)
        order.append("plan")
        return PLAN

    run(plan, order)

    assert order == ["plan", "measure"]


def test_a_graph_built_without_a_planner_has_no_plan():
    final = run()

    assert "plan" not in final
    assert final["result"] == "the result"


def test_an_error_in_the_planner_reaches_the_caller_unchanged():
    def plan(question, a, b):
        raise Boom(question)

    with pytest.raises(Boom):
        run(plan)

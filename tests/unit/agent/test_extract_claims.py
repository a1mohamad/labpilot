import logging

import pytest
from labpilot.agent.extract_claims import STEP, make_claims_node, wants_claims

from labpilot.agent import Claim, ClaimsError, Plan, Query, allowed_steps, build_graph
from labpilot.ingest import Chunk

CLAIMS = (Claim("the time step is 0.01 s", "[paper.md · 4 Setup · lines 10-19]"),)
WANTS = Plan(steps=("extract_claims",), queries=(Query("B", "time step"),))
NOT_WANTED = Plan(steps=("summarize",), queries=(Query("B", "time step"),))
FOUND = Chunk(
    text="dt = 0.01",
    source="solver.py",
    start_line=1,
    end_line=1,
    side="B",
    artifact_id="B-1",
    chunk_index=0,
)


SIDES = {"A": "stored A", "B": "stored B"}


class Boom(Exception):
    pass


def run(plan, *, fits_value, extract="default", order=None):
    order = [] if order is None else order
    if extract == "default":

        def extract(question, a):
            order.append(("claims", question, a))
            return CLAIMS

    def stuff(sides, question):
        order.append("stuff")
        return (FOUND,), None

    def rank_side(question, pile):
        order.append("rank")
        return pile

    def generate(prompt):
        order.append("generate")
        return "the result"

    graph = build_graph(
        measure=lambda a, b: SIDES,
        fits=lambda sides, question: fits_value,
        stuff=stuff,
        search_one=lambda sides, query: (FOUND,),
        totals_of=lambda sides: {"A": 1, "B": 1},
        rank_side=rank_side,
        plan=lambda question, a, b: plan,
        make_prompt=lambda chunks, **_: ("the prompt", chunks),
        generate=generate,
        extract_claims=extract,
    )
    final = graph.invoke({"question": "why?", "a": "A-1", "b": "B-1"})
    return final, order


def test_the_step_is_one_the_planner_may_choose_for_two_files_and_not_for_one():
    assert STEP in allowed_steps(("A", "B"))
    assert STEP not in allowed_steps(("B",))


def test_the_claims_are_wanted_only_when_the_plan_lists_the_step():
    assert wants_claims({"plan": WANTS}) is True
    assert wants_claims({"plan": NOT_WANTED}) is False


def test_the_node_reads_the_question_and_the_reference_and_returns_the_claims():
    seen = []

    def extract(question, a):
        seen.append((question, a))
        return CLAIMS

    result = make_claims_node(extract)({"question": "why?", "a": "A-1"})

    assert result == {"claims": CLAIMS}
    assert seen == [("why?", "A-1")]


def test_when_no_claims_can_be_made_the_node_gives_none_and_logs_why(caplog):
    def extract(question, a):
        raise ClaimsError("the reference is too big")

    with caplog.at_level(logging.WARNING):
        result = make_claims_node(extract)({"question": "why?", "a": "A-1"})

    assert result == {"claims": ()}
    assert "the reference is too big" in caplog.text


def test_any_other_error_reaches_the_caller_unchanged():
    def extract(question, a):
        raise Boom("a bug")

    with pytest.raises(Boom):
        make_claims_node(extract)({"question": "why?", "a": "A-1"})


def test_after_a_search_the_claims_step_runs_before_the_answer():
    final, order = run(WANTS, fits_value=False)

    assert order == ["rank", ("claims", "why?", "A-1"), "generate"]
    assert final["claims"] == CLAIMS


def test_after_stuffing_the_claims_step_runs_before_the_answer():
    final, order = run(WANTS, fits_value=True)

    assert order == ["stuff", ("claims", "why?", "A-1"), "generate"]
    assert final["claims"] == CLAIMS


@pytest.mark.parametrize("fits_value", [True, False])
def test_a_plan_without_the_step_never_runs_it(fits_value):
    _, order = run(NOT_WANTED, fits_value=fits_value)

    assert not any(isinstance(item, tuple) for item in order)
    assert order[-1] == "generate"


def test_without_a_function_the_graph_has_no_claims_step_even_if_the_plan_lists_it():
    graph = build_graph(
        measure=lambda a, b: SIDES,
        fits=lambda sides, question: True,
        stuff=lambda sides, question: ((FOUND,), None),
        search_one=lambda sides, query: (FOUND,),
        totals_of=lambda sides: {"A": 1},
        rank_side=lambda question, pile: pile,
        plan=lambda question, a, b: WANTS,
        make_prompt=lambda chunks, **_: ("the prompt", chunks),
        generate=lambda prompt: "the result",
    )

    final = graph.invoke({"question": "why?", "a": "A-1", "b": "B-1"})

    assert "extract_claims" not in graph.get_graph().nodes
    assert final["result"] == "the result"
    assert "claims" not in final


def test_a_failed_extraction_does_not_stop_the_answer():
    def extract(question, a):
        raise ClaimsError("no tier answered")

    final, order = run(WANTS, fits_value=False, extract=extract)

    assert final["claims"] == ()
    assert order[-1] == "generate"

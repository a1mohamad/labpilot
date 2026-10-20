import logging

import pytest

from labpilot.agent import Plan, Query, allowed_steps, present_sides
from labpilot.agent.plan_check import check_plan, default_plan, question_queries

QUESTION = "why is the clip value 1.5?"
BOTH = ("A", "B")

GOOD = Plan(
    steps=("extract_claims", "find_bugs"),
    queries=(Query("A", "gradient clipping value"), Query("B", "CLIP_NORM")),
)


def queries(count):
    return tuple(Query("A", f"query {i}") for i in range(count))


def test_the_question_is_one_query_for_each_side_that_has_a_file():
    assert question_queries(QUESTION, BOTH) == (
        Query("A", QUESTION),
        Query("B", QUESTION),
    )
    assert question_queries(QUESTION, ("B",)) == (Query("B", QUESTION),)
    assert question_queries(QUESTION, ()) == ()


def test_no_file_means_no_step():
    assert allowed_steps(()) == ()


def test_more_files_never_remove_a_step():
    assert set(allowed_steps(("B",))) <= set(allowed_steps(BOTH))


def test_searching_with_claims_needs_two_files():
    assert "extract_claims" not in allowed_steps(("A",))
    assert "extract_claims" in allowed_steps(BOTH)


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("A-1", "B-1", ("A", "B")),
        ("", "B-1", ("B",)),
        ("A-1", "", ("A",)),
        ("", "", ()),
    ],
)
def test_a_side_is_present_when_its_id_is_not_empty(a, b, expected):
    assert present_sides(a, b) == expected


def test_the_default_plan_runs_every_allowed_step_and_searches_with_the_question():
    plan = default_plan(QUESTION, BOTH)

    assert plan.steps == allowed_steps(BOTH)
    assert plan.queries == (Query("A", QUESTION), Query("B", QUESTION))
    assert plan.source == "default"


def test_the_default_plan_searches_only_the_sides_that_have_a_file():
    assert default_plan(QUESTION, ("B",)).queries == (Query("B", QUESTION),)


def test_with_no_file_the_default_plan_is_empty():
    assert default_plan(QUESTION, ()) == Plan((), (), source="default")


def test_a_good_plan_is_returned_as_it_is():
    assert check_plan(GOOD, QUESTION, BOTH) is GOOD


def test_a_good_plan_still_says_the_planner_made_it():
    assert check_plan(GOOD, QUESTION, BOTH).source == "planner"


def test_an_empty_plan_is_allowed_because_it_means_chat_only():
    plan = Plan((), ())

    assert check_plan(plan, QUESTION, BOTH) is plan


def test_six_queries_are_allowed():
    plan = Plan((), queries(6))

    assert check_plan(plan, QUESTION, BOTH) is plan


@pytest.mark.parametrize(
    ("plan", "sides"),
    [
        pytest.param(Plan(("dance",), ()), BOTH, id="a step nobody knows"),
        pytest.param(Plan(("verify",), ()), BOTH, id="a name from lesson 1"),
        pytest.param(Plan(("extract_claims",), ()), ("B",), id="claims, one file"),
        pytest.param(Plan(("summarize",) * 2, ()), BOTH, id="the same step twice"),
        pytest.param(Plan((), (Query("A", "x"),)), ("B",), id="a side with no file"),
        pytest.param(Plan((), (Query("C", "x"),)), BOTH, id="an unknown side"),
        pytest.param(Plan((), (Query("A", "   "),)), BOTH, id="a blank query"),
        pytest.param(Plan((), queries(7)), BOTH, id="seven queries"),
    ],
)
def test_a_bad_plan_is_replaced_by_the_default_plan(plan, sides):
    assert check_plan(plan, QUESTION, sides) == default_plan(QUESTION, sides)


def test_a_rejected_plan_leaves_the_reason_in_the_log(caplog):
    with caplog.at_level(logging.WARNING):
        check_plan(Plan(("dance",), ()), QUESTION, BOTH)

    assert "'dance'" in caplog.text

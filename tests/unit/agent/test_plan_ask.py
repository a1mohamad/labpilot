"""The planner's optional question for the person (D109): the field, its reader
and its checks. An empty `ask` is the normal case."""

from __future__ import annotations

import pytest

from labpilot.agent import Plan
from labpilot.agent.errors import PlanError
from labpilot.agent.plan_check import MAX_ASK_CHARS, check_plan, problem_with
from labpilot.agent.plan_schema import plan_schema, read_plan

SIDES = ("A", "B")


def test_the_schema_offers_an_optional_ask_field():
    schema = plan_schema(SIDES)

    assert schema["properties"]["ask"] == {"type": "string"}
    assert "ask" not in schema["required"]


def test_a_plan_without_ask_reads_with_an_empty_one():
    plan = read_plan({"steps": [], "queries": []})

    assert plan.ask == ""


def test_the_question_is_trimmed():
    plan = read_plan({"steps": [], "queries": [], "ask": "  What F1?  "})

    assert plan.ask == "What F1?"


def test_line_breaks_in_the_question_become_spaces_and_the_question_is_kept():
    plan = read_plan(
        {
            "steps": [],
            "queries": [],
            "ask": "Which F1 did you get?\nOn validation\n or test?",
        }
    )

    assert plan.ask == "Which F1 did you get? On validation or test?"


@pytest.mark.parametrize("empty", [None, ""])
def test_null_and_empty_both_mean_no_question(empty):
    assert read_plan({"steps": [], "queries": [], "ask": empty}).ask == ""


def test_a_question_that_is_not_text_is_refused():
    with pytest.raises(PlanError):
        read_plan({"steps": [], "queries": [], "ask": ["What F1?"]})


def test_a_long_question_is_not_a_reason_to_write_the_plan_again():
    plan = Plan(steps=(), queries=(), ask="x" * (MAX_ASK_CHARS + 1))

    assert problem_with(plan, SIDES, "why lower?") is None


def test_the_last_guard_drops_a_long_question_but_keeps_the_plan():
    plan = Plan(steps=("summarize",), queries=(), ask="x" * (MAX_ASK_CHARS + 1))

    kept = check_plan(plan, "why?", SIDES)

    assert kept.steps == ("summarize",)
    assert kept.ask == ""
    assert kept.source == "planner"


def test_a_question_at_the_limit_is_kept():
    plan = Plan(steps=(), queries=(), ask="x" * MAX_ASK_CHARS)

    assert problem_with(plan, SIDES, "why?") is None
    assert check_plan(plan, "why?", SIDES) == plan


def test_a_question_that_repeats_the_users_own_makes_the_plan_a_problem():
    plan = Plan(steps=(), queries=(), ask="Why is my F1 lower?")

    problem = problem_with(plan, SIDES, "why is my f1 lower?")

    assert "repeats" in problem


def test_without_the_users_question_nothing_counts_as_a_repeat():
    plan = Plan(steps=(), queries=(), ask="Why is my F1 lower?")

    assert problem_with(plan, SIDES) is None


def test_the_last_guard_drops_a_repeated_question_but_keeps_the_plan():
    plan = Plan(steps=("summarize",), queries=(), ask="Why is my F1 lower?")

    kept = check_plan(plan, "why is my f1 lower?", SIDES)

    assert kept.ask == ""
    assert kept.steps == ("summarize",)


def test_a_good_question_goes_through_unchanged():
    plan = Plan(steps=(), queries=(), ask="What F1 did you get?")

    assert check_plan(plan, "why lower?", SIDES) == plan

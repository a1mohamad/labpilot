"""The planner's three choices about the question (D107): which file it is
about, whether it needs the files, and whether it asks for a new check. The safe
side is the default for each, so a plan that says nothing changes nothing."""

from __future__ import annotations

import pytest

from labpilot.agent.errors import PlanError
from labpilot.agent.plan_check import check_plan, problem_with
from labpilot.agent.plan_schema import plan_schema, read_plan
from labpilot.prompts import PLANNER_VERSION, build_planner_prompt

BOTH = ("A", "B")


def test_a_plan_that_says_nothing_takes_the_safe_side_of_each_choice():
    plan = read_plan({"steps": [], "queries": []})

    assert (plan.about, plan.files, plan.fresh) == ("both", True, False)


def test_the_choices_are_read_as_written():
    plan = read_plan(
        {"steps": [], "queries": [], "about": "A", "files": False, "fresh": True}
    )

    assert (plan.about, plan.files, plan.fresh) == ("A", False, True)


def test_null_means_the_safe_side():
    plan = read_plan(
        {"steps": [], "queries": [], "about": None, "files": None, "fresh": None}
    )

    assert (plan.about, plan.files, plan.fresh) == ("both", True, False)


@pytest.mark.parametrize(
    ("field", "value"),
    [("about", 3), ("files", "yes"), ("fresh", 1)],
)
def test_a_choice_of_the_wrong_type_is_a_plan_error(field, value):
    with pytest.raises(PlanError):
        read_plan({"steps": [], "queries": [], field: value})


def test_the_schema_offers_all_three_choices_and_requires_none():
    schema = plan_schema(BOTH)

    assert schema["properties"]["about"]["enum"] == ["A", "B", "both"]
    assert schema["properties"]["files"] == {"type": "boolean"}
    assert schema["properties"]["fresh"] == {"type": "boolean"}
    assert not {"about", "files", "fresh"} & set(schema["required"])


def test_an_about_that_is_not_a_side_is_a_problem_so_the_next_tier_writes_again():
    plan = read_plan({"steps": [], "queries": [], "about": "C"})

    assert "about" in problem_with(plan, BOTH)


def test_a_question_about_a_side_with_no_file_is_a_problem():
    plan = read_plan({"steps": [], "queries": [], "about": "A"})

    assert "no file" in problem_with(plan, ("B",))


def test_with_one_file_about_becomes_both_and_the_plan_stays():
    plan = read_plan({"steps": ["summarize"], "queries": [], "about": "A"})

    checked = check_plan(plan, "what is it?", ("B",))

    assert checked.source == "planner"
    assert checked.about == "both"


def test_with_two_files_a_one_sided_question_is_kept():
    plan = read_plan({"steps": [], "queries": [], "about": "B"})

    assert check_plan(plan, "what does fit do?", BOTH).about == "B"


def test_the_prompt_tells_the_planner_what_each_choice_means():
    prompt = build_planner_prompt("q", "map", ("summarize",), max_queries=6)

    for word in ("about:", "files:", "fresh:", "ask:"):
        assert word in prompt


def test_the_prompt_says_to_take_the_safe_side_when_unsure():
    prompt = build_planner_prompt("q", "map", ("summarize",), max_queries=6)

    assert prompt.count("not sure") >= 3


def test_the_planner_wording_has_a_new_version():
    assert PLANNER_VERSION == 6


def test_no_step_is_described_that_no_node_runs():
    prompt = build_planner_prompt("q", "map", ("summarize",), max_queries=6)

    assert "extract_outcomes" not in prompt


def test_the_ask_rule_forbids_repeating_or_rewording_the_question():
    prompt = build_planner_prompt("q", "map", ("summarize",), max_queries=6)

    assert "repeat or reword the person's own question" in prompt

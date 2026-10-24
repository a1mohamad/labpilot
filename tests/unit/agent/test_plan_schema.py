import pytest

from labpilot.agent import (
    PLAN_TOOL_NAME,
    Plan,
    PlanError,
    Query,
    allowed_steps,
    plan_schema,
    read_plan,
)
from labpilot.agent.plan_check import problem_with

GOOD = {
    "steps": ["extract_claims", "find_missing"],
    "queries": [
        {"side": "A", "text": "gradient clipping value 1.0"},
        {"side": "B", "text": "clip_grad_norm_ CLIP_NORM"},
    ],
}


def test_the_tool_has_a_name_the_instruction_can_use():
    assert PLAN_TOOL_NAME == "make_plan"


@pytest.mark.parametrize(
    "sides", [("A", "B"), ("A",), ("B",)], ids=["both", "only A", "only B"]
)
def test_the_schema_offers_only_the_steps_and_sides_the_files_allow(sides):
    schema = plan_schema(sides)
    properties = schema["properties"]

    assert properties["steps"]["items"]["enum"] == list(allowed_steps(sides))
    assert properties["queries"]["items"]["properties"]["side"]["enum"] == list(sides)


def test_the_schema_requires_every_field():
    schema = plan_schema(("A", "B"))

    assert schema["type"] == "object"
    assert schema["required"] == ["steps", "queries"]
    assert schema["properties"]["queries"]["items"]["required"] == ["side", "text"]


def test_arguments_become_a_plan_with_real_queries():
    plan = read_plan(GOOD)

    assert plan == Plan(
        steps=("extract_claims", "find_missing"),
        queries=(
            Query("A", "gradient clipping value 1.0"),
            Query("B", "clip_grad_norm_ CLIP_NORM"),
        ),
    )
    assert plan.source == "planner"


def test_an_empty_plan_is_a_plan():
    assert read_plan({"steps": [], "queries": []}) == Plan(steps=(), queries=())


def test_a_field_we_did_not_ask_for_is_ignored():
    assert read_plan({**GOOD, "effort": "high"}) == read_plan(GOOD)


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"steps": ["find_missing"]},
        {"queries": []},
        {"steps": "find_missing", "queries": []},
        {"steps": ["find_missing", 3], "queries": []},
        {"steps": [], "queries": "B: CLIP_NORM"},
        {"steps": [], "queries": ["CLIP_NORM"]},
        {"steps": [], "queries": [{"text": "CLIP_NORM"}]},
        {"steps": [], "queries": [{"side": "B"}]},
        {"steps": [], "queries": [{"side": "B", "text": 5}]},
        {"steps": [], "queries": [{"side": ["B"], "text": "x"}]},
    ],
    ids=lambda arguments: str(arguments)[:50],
)
def test_arguments_with_the_wrong_shape_are_a_plan_error(arguments):
    with pytest.raises(PlanError):
        read_plan(arguments)


def test_what_the_plan_means_is_judged_by_check_plan_and_not_here():
    plan = read_plan(
        {"steps": ["fly_to_the_moon"], "queries": [{"side": "a", "text": "x"}]}
    )

    assert problem_with(plan, ("A", "B")) is not None

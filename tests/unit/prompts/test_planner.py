import pytest

from labpilot.agent.plan_check import STEPS_BY_FILES
from labpilot.llm import CHAIN
from labpilot.llm.defaults import SAFETY_MARGIN_RATIO
from labpilot.prompts import (
    PLANNER,
    PLANNER_BUDGET,
    PLANNER_INPUT_LIMIT,
    STEP_MEANINGS,
    build_planner_prompt,
    map_budget,
)

ALL_STEPS = sorted({step for steps in STEPS_BY_FILES.values() for step in steps})


def prompt(**changes):
    arguments = {
        "question": "why do the results differ?",
        "corpus_map": "SIDE B - 1 file\ntrain.py   3 parts, lines 1-90",
        "steps": ("summarize", "find_bugs"),
        "max_queries": 12,
    }
    return build_planner_prompt(**{**arguments, **changes})


@pytest.mark.parametrize("step", ALL_STEPS)
def test_every_step_the_rules_allow_has_a_meaning_for_the_model(step):
    assert STEP_MEANINGS[step].strip()
    assert step in prompt(steps=(step,))


def test_only_the_steps_that_are_allowed_are_listed():
    text = prompt(steps=("summarize", "find_bugs"))

    assert "- summarize:" in text
    assert "- find_bugs:" in text
    assert "extract_claims" not in text


def test_a_step_without_a_meaning_is_refused_before_any_model_is_asked():
    with pytest.raises(ValueError, match="fly_to_the_moon"):
        prompt(steps=("fly_to_the_moon",))


def test_the_prompt_holds_the_map_the_limit_and_the_question_last():
    text = prompt(max_queries=7)

    assert text.startswith(PLANNER)
    assert "train.py   3 parts, lines 1-90" in text
    assert "2 to 5 queries, and never more than 7" in text
    assert "The question itself is searched too" in text
    assert text.endswith("why do the results differ?")


def test_the_instruction_shows_what_a_good_query_looks_like():
    assert "Good query" in PLANNER
    assert "Bad query" in PLANNER


def test_the_map_gets_its_ceiling_when_there_is_plenty_of_room():
    assert map_budget(100) == PLANNER_BUDGET


def test_the_map_shrinks_when_the_rest_of_the_prompt_is_big():
    assert map_budget(PLANNER_INPUT_LIMIT - 5_000) == 5_000


def test_the_map_budget_never_reaches_zero():
    assert map_budget(PLANNER_INPUT_LIMIT * 3) == 1


def test_the_limit_fits_the_tightest_input_cap_in_the_chain():
    tightest = min(
        tier.max_input_tokens for tier in CHAIN if tier.max_input_tokens is not None
    )

    assert PLANNER_INPUT_LIMIT * (1 + SAFETY_MARGIN_RATIO) <= tightest


def test_the_instruction_says_what_a_quoted_signature_or_sentence_in_the_map_is():
    assert "signature" in PLANNER
    assert "in quotes" in PLANNER
    assert "copied from the file" in PLANNER

import pytest

from labpilot.prompts import (
    MAX_QUERY_CHARS,
    REQUERY,
    build_requery_prompt,
    requery_problem,
)

COLLAPSE_BYTES = 2200
BANNED = (
    "python",
    "pytorch",
    "gradient",
    "dataset",
    "function",
    "class",
    "variable",
    "repository",
    "epoch",
)


def test_the_instruction_comes_first_and_the_closing_comes_last():
    prompt = build_requery_prompt("the step is 0.01 s", ["the step is 0.01 s"])

    assert prompt.startswith(REQUERY.header)
    assert prompt.endswith(REQUERY.closing)


def test_the_claim_comes_before_the_earlier_queries_which_are_numbered_in_order():
    prompt = build_requery_prompt("the step is 0.01 s", ["first words", "second words"])

    assert "THE CLAIM\nthe step is 0.01 s" in prompt
    assert "EARLIER QUERIES\n1. first words\n2. second words" in prompt
    assert prompt.index("THE CLAIM") < prompt.index("EARLIER QUERIES")


def test_what_the_check_said_is_in_the_prompt_only_when_there_is_something():
    said = build_requery_prompt("a fact", ["a fact"], "the parts are about output")
    silent = build_requery_prompt("a fact", ["a fact"], "   ")

    assert "WHAT THE CHECK SAID\nthe parts are about output" in said
    assert "WHAT THE CHECK SAID" not in silent


def test_a_long_earlier_query_and_a_long_note_are_cut_but_the_claim_never_is():
    claim = "c" * 500

    prompt = build_requery_prompt(claim, ["q" * 500], "n" * 1_000)

    assert claim in prompt
    assert "q" * 500 not in prompt
    assert "q" * 200 in prompt
    assert "n" * 1_000 not in prompt
    assert "n" * 300 in prompt


@pytest.mark.parametrize("claim, tried", [("", ["a"]), ("   ", ["a"]), ("a fact", [])])
def test_a_new_query_needs_a_claim_and_at_least_one_query_already_tried(claim, tried):
    with pytest.raises(ValueError):
        build_requery_prompt(claim, tried)


def test_the_instruction_asks_for_one_line_and_for_a_query_that_is_new():
    text = " ".join(REQUERY.header.split())

    assert "Write the query on one line and nothing else" in text
    assert "Do not repeat an earlier query" in text


def test_the_instruction_names_no_field_of_study():
    text = REQUERY.header.lower()

    assert [word for word in BANNED if word in text] == []


def test_the_instruction_is_short_enough_to_be_followed():
    assert len(REQUERY.header.encode()) < COLLAPSE_BYTES


def test_a_good_query_has_no_problem():
    assert requery_problem(["the step is 0.01 s"], "dt timestep TIME_STEP") is None


@pytest.mark.parametrize("answer", ["", "   ", "line one\nline two"])
def test_a_blank_answer_or_one_with_many_lines_is_a_problem(answer):
    assert requery_problem(["a"], answer) is not None


def test_an_answer_over_200_characters_is_a_problem_and_200_is_not():
    assert MAX_QUERY_CHARS == 200
    assert requery_problem(["a"], "w" * 201) is not None
    assert requery_problem(["a"], "w" * 200) is None


@pytest.mark.parametrize(
    "answer", ["the step is 0.01 s", "  THE  step is 0.01 s ", "the step\tis 0.01 s"]
)
def test_an_answer_that_repeats_an_earlier_query_is_a_problem(answer):
    assert requery_problem(["x y", "the step is 0.01 s"], answer) is not None


@pytest.mark.parametrize(
    "answer", ["clip norm 1.0", "split 0.9 test", "lr 3e-4", "dim 100"]
)
def test_a_query_that_holds_a_value_is_refused(answer):
    assert "value" in requery_problem(["first"], answer)


@pytest.mark.parametrize(
    "answer", ["f1 threshold", "conv2d stride", "CLIP_NORM clip_grad_norm_"]
)
def test_a_name_that_holds_a_digit_is_not_a_value(answer):
    assert requery_problem(["first"], answer) is None


def test_the_outline_of_the_other_file_is_shown_when_given():
    prompt = build_requery_prompt("a claim", ["first"], "", "B_train.py\n  def fit")

    assert "THE OUTLINE OF THE OTHER FILE\nB_train.py" in prompt
    assert prompt.endswith(REQUERY.closing)


def test_without_an_outline_there_is_no_outline_block():
    block = "THE OUTLINE OF THE OTHER FILE" + chr(10)

    assert block not in build_requery_prompt("a claim", ["first"])

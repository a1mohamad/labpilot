import pytest

from labpilot.prompts import (
    FOLLOW_UP,
    build_follow_up_prompt,
    follow_up_problem,
    last_answer_excerpt,
)


def test_the_prompt_holds_the_earlier_questions_in_order_and_then_the_new_one():
    prompt = build_follow_up_prompt(
        "and the batch size?", ["why do results differ?", "what is the lr?"]
    )

    assert "1. why do results differ?" in prompt
    assert "2. what is the lr?" in prompt
    assert prompt.index("1. why") < prompt.index("2. what")
    assert prompt.index("2. what") < prompt.index("New question:\nand the batch size?")


def test_only_the_last_four_earlier_questions_are_sent():
    history = [f"question {number}?" for number in range(10)]

    prompt = build_follow_up_prompt("and now?", history)

    assert "question 5?" not in prompt
    assert "question 6?" in prompt
    assert "question 9?" in prompt


def test_a_long_earlier_question_is_cut_but_the_new_question_never_is():
    new = "y" * 1_000

    prompt = build_follow_up_prompt(new, ["x" * 1_000])

    assert "x" * 1_000 not in prompt
    assert "x" * 300 in prompt
    assert new in prompt


def test_the_last_answer_comes_after_the_questions_and_before_the_new_question():
    prompt = build_follow_up_prompt(
        "do the second one", ["what can I improve?"], "1. clip. 2. lower the lr."
    )

    assert "The last answer the tool gave:\n1. clip. 2. lower the lr." in prompt
    assert prompt.index("1. what can I improve?") < prompt.index("The last answer")
    assert prompt.index("The last answer") < prompt.index("New question:")


def test_the_prompt_holds_only_the_end_of_a_very_long_last_answer():
    answer = "STARTMARK" + "q" * 5_000 + "ENDMARK"

    prompt = build_follow_up_prompt("and now?", ["first?"], answer)

    assert "STARTMARK" not in prompt
    assert "ENDMARK" in prompt
    assert "q" * 2_000 not in prompt


def test_without_a_last_answer_the_prompt_has_no_answer_block():
    prompt = build_follow_up_prompt("and now?", ["first?"])

    assert "The last answer the tool gave" not in prompt


def test_the_instruction_comes_first_and_the_closing_comes_last():
    prompt = build_follow_up_prompt("and now?", ["first?"], "an answer")

    assert prompt.startswith(FOLLOW_UP.header)
    assert prompt.endswith(FOLLOW_UP.closing)


def test_the_instruction_says_to_copy_a_question_it_cannot_make_clearer():
    # D6: a specific question must not be rewritten, because a rewrite of a good
    # question can only lose. Two sentences carry it: one for a question that
    # already stands alone, one for a word that cannot be resolved. A live check
    # on a cheap tier showed that without the second one the model guessed.
    assert "copy it exactly" in FOLLOW_UP.header
    assert "Never guess" in FOLLOW_UP.header


def test_the_instruction_lets_the_last_answer_be_used_only_when_it_is_pointed_at():
    # A live check showed the answer lets the model solve "the second one", and
    # the words "only when" are what keep it out of every other question.
    assert "last answer only when the new question points at" in " ".join(
        FOLLOW_UP.header.split()
    )


@pytest.mark.parametrize(
    ("question", "history"), [("   ", ["first?"]), ("and now?", [])]
)
def test_a_follow_up_with_no_question_or_no_past_is_refused(question, history):
    with pytest.raises(ValueError):
        build_follow_up_prompt(question, history)


def test_a_short_answer_is_kept_whole_and_one_of_exactly_2000_characters_too():
    assert last_answer_excerpt("  a short answer  ") == "a short answer"
    assert last_answer_excerpt("x" * 2_000) == "x" * 2_000


def test_a_long_answer_is_cut_to_its_end_and_never_past_2000_characters():
    text = "start " + "m" * 5_000 + " end of the answer"

    excerpt = last_answer_excerpt(text)

    assert len(excerpt) == 2_000
    assert excerpt.startswith("…")
    assert excerpt.endswith("end of the answer")
    assert "start" not in excerpt


def test_cutting_an_excerpt_again_changes_nothing():
    once = last_answer_excerpt("y" * 5_000)

    assert last_answer_excerpt(once) == once


def test_a_good_rewrite_has_no_problem():
    assert follow_up_problem("and the lr?", "what is the learning rate?") is None


@pytest.mark.parametrize("answer", ["", "   ", "line one\nline two"])
def test_a_blank_answer_or_one_with_many_lines_is_a_problem(answer):
    assert follow_up_problem("and the lr?", answer) is not None


def test_an_answer_over_600_characters_is_a_problem_and_600_is_not():
    assert follow_up_problem("q?", "w" * 601) is not None
    assert follow_up_problem("q?", "w" * 600) is None


def test_a_copy_of_a_long_question_is_never_too_long():
    long = "z" * 900

    assert follow_up_problem(long, long) is None

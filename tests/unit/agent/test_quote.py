import pytest

from labpilot.agent._quote import has_quote

PART = "[paper.md · 4 Setup]\nThe time step is 0.01 s, and the mesh has 200 cells."


def test_words_that_are_in_the_part_are_a_quote():
    assert has_quote(PART, "the mesh has 200 cells") is True


def test_words_that_are_not_in_the_part_are_not_a_quote():
    assert has_quote(PART, "the mesh has 400 cells") is False


@pytest.mark.parametrize("quote", ["", "   ", "\n"])
def test_a_blank_quote_is_never_a_quote(quote):
    assert has_quote(PART, quote) is False


def test_capital_letters_and_spaces_do_not_make_a_quote_wrong():
    assert has_quote(PART, "THE TIME STEP  is\n0.01 s") is True


def test_an_escaped_pipe_does_not_make_a_quote_wrong():
    part = "| dropout | 0.5 |"

    assert has_quote(part, r"\| dropout \| 0.5 \|") is True


@pytest.mark.parametrize(
    "part, quote",
    [
        ("We use $K = 4$ heads.", "We use K = 4 heads."),
        ("We use K = 4 heads.", "We use $K = 4$ heads."),
        ("chosen on the **development** set.", "chosen on the development set."),
    ],
)
def test_formula_and_bold_marks_do_not_make_a_quote_wrong(part, quote):
    assert has_quote(part, quote) is True


def test_a_quote_has_to_match_words_in_a_row_and_not_words_far_apart():
    assert has_quote(PART, "time step 200 cells") is False

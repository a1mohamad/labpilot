"""What a part's own first characters say about it: a signature or a sentence."""

from __future__ import annotations

from labpilot.prompts import OPENING_CHARS
from labpilot.prompts._hints import describe

# ---- a function or a class: the def line, found by name --------------------


def test_a_function_gives_its_signature():
    opening = "    def fit(self, loader, epochs=3):\n        for e in range(epochs):\n"

    assert describe("def fit", opening) == ("def fit(self, loader, epochs=3)", "")


def test_the_decorators_of_a_function_stay_in_front_of_its_signature():
    opening = "    @torch.no_grad()\n    def evaluate(self):\n        pass\n"

    assert describe("def evaluate", opening) == (
        "@torch.no_grad() def evaluate(self)",
        "",
    )


def test_an_async_function_keeps_its_async():
    assert describe("def fetch", "async def fetch(url):\n    pass\n") == (
        "async def fetch(url)",
        "",
    )


def test_a_signature_over_several_lines_is_joined_into_one():
    opening = "    def __init__(\n        self,\n        model,\n    ):\n        pass\n"

    assert describe("def __init__", opening) == ("def __init__(self, model)", "")


def test_a_class_gives_its_bases():
    assert describe("class Net", "class Net(nn.Module):\n    width = 3\n") == (
        "class Net(nn.Module)",
        "",
    )


def test_a_name_the_text_does_not_hold_gets_no_signature():
    # the chunker can merge a tiny function into its neighbour: the label names
    # one function and the text starts with another, and a wrong signature is
    # worse than none
    assert describe("def fit", "def other(x):\n    return x\n") == ("", "")


def test_a_part_with_no_opening_gets_nothing():
    assert describe("def fit", "") == ("", "")
    assert describe("def fit", "   \n  ") == ("", "")


def test_a_cut_signature_is_not_shown_half_written():
    opening = ("def long_one(" + ", ".join(f"argument_{i}" for i in range(60)))[
        :OPENING_CHARS
    ]
    assert len(opening) == OPENING_CHARS, "premise: the opening is cut"

    signature, _ = describe("def long_one", opening)

    assert signature.endswith(" …")
    assert len(signature) <= 115
    assert signature.removesuffix(" …").rsplit(" ", 1)[-1] in {
        f"argument_{i}" for i in range(60)
    }


# ---- the docstring line under a def ----------------------------------------


def test_the_first_line_of_a_docstring_is_the_note():
    opening = 'def seed(x):\n    """Makes runs repeatable.\n\n    More."""\n    pass\n'

    assert describe("def seed", opening) == ("def seed(x)", "Makes runs repeatable.")


def test_a_docstring_that_starts_on_the_next_line_is_read_from_there():
    opening = 'def seed(x):\n    """\n    Makes runs repeatable.\n    """\n'

    assert describe("def seed", opening)[1] == "Makes runs repeatable."


def test_a_double_quote_inside_a_docstring_cannot_close_the_note_early():
    opening = 'def seed(x):\n    """Say "hi" now."""\n'

    assert describe("def seed", opening)[1] == "Say 'hi' now."


def test_a_docstring_line_cut_by_the_end_of_the_opening_is_not_shown_half_written():
    # a long signature uses up the opening, so the docstring is cut in a word
    opening = ("def f(" + "a" * 265 + '):\n    """Makes the thing repeat')[
        :OPENING_CHARS
    ]
    assert len(opening) == OPENING_CHARS, "premise: the opening is cut"

    assert describe("def f", opening)[1] == "Makes the thing …"


# ---- a section: the first sentence under a heading with its name -----------


def test_the_first_sentence_under_a_section_heading_is_the_note():
    opening = (
        "## 4.1 Input\n\nQuestions are lowercased. Punctuation is split off.\n"
        "\nMore text.\n"
    )

    assert describe("4.1 Input", opening) == ("", "Questions are lowercased.")


def test_a_sentence_that_wraps_onto_a_line_with_a_formula_stays_whole():
    opening = "## Setup\n\nWe train with $x$ and\n$y$ together. Then more.\n"

    assert describe("Setup", opening)[1] == "We train with $x$ and $y$ together."


def test_a_formula_block_under_a_heading_is_skipped_not_quoted():
    opening = "## Loss\n\n$$\nL = -(y + p)\n$$\n\nWe minimise the loss.\n"

    assert describe("Loss", opening)[1] == "We minimise the loss."


def test_a_sentence_cut_by_the_end_of_the_opening_is_not_shown_half_written():
    opening = (
        "## Title\n\n$$\n" + "x" * 250 + "\n$$\n\nThe model trains for many epochs"
    )[:OPENING_CHARS]
    assert len(opening) == OPENING_CHARS, "premise: the opening is cut"

    assert describe("Title", opening)[1] == "The model trains for many …"


def test_a_heading_that_is_not_the_name_of_the_unit_is_not_trusted():
    # a notebook cell or a code comment can start with "#" too
    assert describe("4.1 Input", "# something else\n\nimport torch\n") == ("", "")


def test_a_code_comment_is_not_a_section_hint():
    opening = "# Load the data\nimport pandas\n"

    assert describe("cell 3 [code] run 1", opening) == ("", "")

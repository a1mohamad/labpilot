import pytest

from labpilot.agent import KINDS, VERDICTS
from labpilot.prompts import (
    CHECK,
    CHECKS_NOTE,
    build_check_prompt,
    render_checks,
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
PARTS = ["alpha body", "beta body", "gamma body"]


def test_the_instruction_comes_first_and_the_closing_comes_last():
    prompt = build_check_prompt("the step is 0.01 s", "[paper.md · 4]", PARTS)

    assert prompt.startswith(CHECK.header)
    assert prompt.endswith(CHECK.closing)


def test_the_claim_and_its_place_are_in_the_prompt():
    prompt = build_check_prompt("the step is 0.01 s", "[paper.md · 4]", PARTS)

    assert "THE CLAIM (from [paper.md · 4])\nthe step is 0.01 s" in prompt


def test_every_part_is_numbered_from_zero_in_its_order():
    prompt = build_check_prompt("a fact", "[paper.md]", PARTS)

    assert "[part 0]\nalpha body" in prompt
    assert "[part 1]\nbeta body" in prompt
    assert "[part 2]\ngamma body" in prompt
    positions = [prompt.index(f"[part {n}]") for n in range(3)]
    assert positions == sorted(positions)


@pytest.mark.parametrize("claim, parts", [("", PARTS), ("   ", PARTS), ("a fact", [])])
def test_a_check_needs_a_claim_and_at_least_one_part(claim, parts):
    with pytest.raises(ValueError):
        build_check_prompt(claim, "[paper.md]", parts)


def test_the_instruction_names_every_word_the_schema_allows():
    for word in (*VERDICTS, *KINDS):
        assert word in CHECK.header


def test_the_instruction_says_absent_means_not_found_in_these_parts():
    assert "never" in CHECK.header and "not found in these parts" in CHECK.header


def test_the_instruction_names_no_field_of_study():
    text = CHECK.header.lower()

    assert [word for word in BANNED if word in text] == []


def test_the_instruction_is_short_enough_to_be_followed():
    assert len(CHECK.header.encode()) < COLLAPSE_BYTES


def test_the_checks_come_with_a_note_that_says_what_absent_means():
    block = render_checks(["[match] one", "[absent] two"])

    assert block.splitlines() == [CHECKS_NOTE, "[match] one", "[absent] two"]
    assert "not found" in CHECKS_NOTE


def test_no_checks_make_no_block_at_all():
    assert render_checks([]) == ""


def test_facts_from_the_whole_file_come_after_the_parts_and_before_the_closing():
    prompt = build_check_prompt(
        "the positive class is weighted",
        "[paper.md]",
        ["part zero"],
        "`pos_weight` (defined in [x]) is never called or named anywhere else.",
    )

    assert "FACTS FROM THE WHOLE OTHER FILE\n`pos_weight`" in prompt
    assert (
        prompt.index("[part 0]")
        < prompt.index("FACTS FROM")
        < prompt.index(CHECK.closing)
    )


def test_without_facts_there_is_no_facts_block():
    assert "FACTS FROM" not in build_check_prompt("a claim", "[p]", ["part"])


def test_the_instruction_says_a_definition_alone_is_not_a_use():
    header = " ".join(CHECK.header.split())

    assert "only defined and never used or called" in header


def test_a_never_called_fact_is_called_a_mismatch_not_absent():
    # 2026-10-24, the wired check arm: the checker saw "pos_class_weight is
    # never called" and still answered "absent", twice. The paper weights the
    # class and B does not, so the right verdict is a mismatch.
    from labpilot.prompts.checks import CHECK

    header = " ".join(CHECK.header.split())
    assert (
        "never called or named anywhere else in the file, that is a mismatch" in header
    )


def test_the_instruction_says_how_to_judge_a_claim_that_something_is_not_done():
    text = " ".join(CHECK.header.split())

    assert "NOT done" in text and "never match" in text

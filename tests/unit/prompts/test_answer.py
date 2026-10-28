import pytest

from labpilot.prompts import (
    CHAT,
    ONE_FILE,
    TWO_FILES,
    build_chat_prompt,
    instructions_for,
)


def squeezed(text):
    return " ".join(text.split())


def test_each_number_of_files_gets_its_own_instruction():
    assert instructions_for(0) is CHAT
    assert instructions_for(1) is ONE_FILE
    assert instructions_for(2) is TWO_FILES


@pytest.mark.parametrize("files", [-1, 3])
def test_a_number_of_files_other_than_0_1_or_2_is_refused(files):
    with pytest.raises(ValueError):
        instructions_for(files)


def test_the_chat_instruction_asks_for_a_file_it_was_not_given():
    # Measured on two tiers: 8 of 8 runs asked for the missing file and none
    # guessed what was in it.
    header = squeezed(CHAT.header)

    assert "do not guess what is in it" in header
    assert "ask the person to add it" in header


def test_the_chat_instruction_does_not_talk_about_parts_or_citations():
    assert "[B-17" not in CHAT.header
    assert "parts" not in CHAT.header


def test_the_one_file_instruction_answers_first_and_then_lists_problems():
    header = ONE_FILE.header

    assert header.index("ANSWER -") < header.index("PROBLEMS -")
    assert "answer the question first" in squeezed(header)


def test_the_one_file_instruction_keeps_the_citation_format():
    # The code parses [B-17 "line"], so this sentence is a contract.
    expected = 'Cite every claim as [B-17 "one line copied exactly from that part"]'

    assert expected in ONE_FILE.header


def test_the_one_file_instruction_leaves_out_what_the_code_does_on_purpose():
    # The filter sentence that stopped a check that raises on purpose from being
    # reported as a problem (4 of 12 answers without it, 0 of 11 with it).
    assert "a design choice the code states on purpose" in squeezed(ONE_FILE.header)


def test_every_instruction_lets_the_last_answer_be_used_only_when_pointed_at():
    for instructions in (CHAT, ONE_FILE, TWO_FILES):
        assert "Use it only when the question points at it" in squeezed(
            instructions.header
        )


def test_the_chat_prompt_is_the_instruction_then_the_question():
    prompt = build_chat_prompt("explain gradient clipping")

    assert prompt.startswith(CHAT.header)
    assert prompt.endswith("QUESTION: explain gradient clipping")
    assert "The last answer the tool gave:" not in prompt


def test_the_chat_prompt_puts_the_last_answer_between_them():
    prompt = build_chat_prompt("do the second one", "1. clip  2. lower the lr")

    block = "The last answer the tool gave:\n1. clip  2. lower the lr"
    assert prompt.index(CHAT.header) < prompt.index(block) < prompt.index("QUESTION:")


def test_a_blank_chat_question_is_refused():
    with pytest.raises(ValueError):
        build_chat_prompt("   ")


# The two-file instruction. Measured on the real pair (2026-10-22): answer first,
# add up the sizes of the causes, and be complete when asked why.

# The text was 2,914 bytes with its closing line, and 3,110 since 2026-10-25,
# when it was told to carry every finding already made and to quote both sides
# of a match (R9, R19). The older lean report is 2,100. This stops it growing
# without anyone deciding to.
TWO_FILES_BYTES = 3_200


def test_the_two_file_instruction_answers_first_and_ends_with_the_next_step():
    header = TWO_FILES.header
    order = [
        "ANSWER -",
        "COMPARABLE -",
        "DIFFERENCES -",
        "PROBLEMS IN B -",
        "NEXT STEP -",
    ]

    positions = [header.index(name) for name in order]

    assert positions == sorted(positions)
    assert "answer the question first" in squeezed(header)


def test_the_two_file_instruction_keeps_the_citation_format():
    expected = 'Cite every claim as [B-17 "one line copied exactly from that part"]'

    assert expected in TWO_FILES.header
    assert "Never write a line number" in TWO_FILES.header


def test_the_two_file_instruction_asks_to_add_up_the_causes_against_the_gap():
    # The right answer for the sample pair is "no, they do not add up". On one
    # pair, with the older wording most tiers wrote "yes, they add up"; with this
    # wording the stronger tiers wrote that the sum does not fit the gap.
    header = squeezed(TWO_FILES.header)

    assert "add those sizes up" in header
    assert "If it does not fit, say so" in header


def test_the_two_file_instruction_asks_for_every_difference_when_asked_why():
    # Without this the answer-first wording lost coverage on the middle tiers
    # (10 of 19 findings against 15).
    assert "be complete" in squeezed(TWO_FILES.header)


def test_the_two_file_instruction_stays_under_its_size_limit():
    whole = f"{TWO_FILES.header}\n{TWO_FILES.closing}"

    assert len(whole.encode()) < TWO_FILES_BYTES


def test_the_two_file_instruction_names_no_language_and_no_field():
    banned = ("python", "pytorch", "gradient", "dataset", "epoch", "notebook")
    text = f"{TWO_FILES.header} {TWO_FILES.closing}".lower()

    assert [word for word in banned if word in text] == []


def test_every_finding_already_made_must_be_carried_or_dismissed():
    # R9: in the 2026-10-24 baseline the weight-decay mismatch handed over by
    # the checks was missing from the report.
    header = squeezed(TWO_FILES.header)

    assert "[mismatch], [B differs] or [A silent] line" in header
    assert "why it is not a cause" in header


def test_a_match_needs_a_quote_from_each_side():
    # R19: the 2026-10-24 baseline listed the flagship divergence as a match.
    assert "Say A and B match only with a quote from each" in squeezed(TWO_FILES.header)

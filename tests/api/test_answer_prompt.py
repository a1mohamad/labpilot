import pytest

from labpilot.api.errors import ArtifactsTooLargeToCompare
from labpilot.api.prompting import build_answer_prompt
from labpilot.ingest import Chunk
from labpilot.prompts import CHAT, ONE_FILE, PROMPT_BUDGET, TWO_FILES
from labpilot.tokens import estimate_tokens


def chunk(index, words=30, side="B"):
    return Chunk(
        text=" ".join(["word"] * words),
        source="m.py",
        start_line=index,
        end_line=index,
        side=side,
        artifact_id=f"{side}-1",
        chunk_index=index,
    )


def test_no_file_gives_the_chat_prompt_and_selects_nothing():
    prompt, selected = build_answer_prompt((), question="explain clipping", files=0)

    assert prompt.startswith(CHAT.header)
    assert prompt.endswith("QUESTION: explain clipping")
    assert selected == ()


def test_no_file_is_never_called_too_large_even_though_nothing_is_selected():
    # With no file, "nothing was selected" is the normal case and not an error.
    build_answer_prompt((), question="hi", files=0)


def test_no_file_carries_the_last_answer_into_the_chat_prompt():
    prompt, _ = build_answer_prompt(
        (), question="do the second one", files=0, last_answer="1. a  2. b"
    )

    assert "The last answer the tool gave:\n1. a  2. b" in prompt


def test_one_file_gives_the_answer_then_problems_prompt_with_its_parts():
    chunks = (chunk(0), chunk(1))

    prompt, selected = build_answer_prompt(chunks, question="what is this?", files=1)

    assert ONE_FILE.header in prompt
    assert prompt.endswith("QUESTION: what is this?")
    assert selected == chunks


def test_one_file_carries_the_last_answer_after_the_parts():
    chunks = (chunk(0),)

    prompt, _ = build_answer_prompt(
        chunks, question="do it", files=1, last_answer="1. a  2. b"
    )

    assert prompt.index("word word word") < prompt.index(
        "The last answer the tool gave:"
    )


def test_one_file_that_is_too_big_keeps_the_prompt_inside_the_budget():
    chunks = tuple(chunk(index, words=300) for index in range(200))

    prompt, selected = build_answer_prompt(chunks, question="what is this?", files=1)

    assert 0 < len(selected) < len(chunks)
    assert estimate_tokens(prompt) <= PROMPT_BUDGET


def test_a_long_last_answer_still_leaves_the_prompt_inside_the_budget():
    # The selector fills the room it is given, so if the last answer were not
    # counted when the room is worked out, this prompt would go past the budget.
    chunks = tuple(chunk(index, words=300) for index in range(200))

    prompt, _ = build_answer_prompt(
        chunks, question="what is this?", files=1, last_answer="x" * 5_000
    )

    assert estimate_tokens(prompt) <= PROMPT_BUDGET


def test_one_file_with_no_room_for_a_single_part_is_refused():
    with pytest.raises(ArtifactsTooLargeToCompare):
        build_answer_prompt(
            (chunk(0, words=100_000),), question="what is this?", files=1
        )


def test_two_files_give_the_two_file_instruction_and_both_sides():
    chunks = (chunk(0, side="A"), chunk(0, side="B"))

    prompt, selected = build_answer_prompt(chunks, question="why?", files=2)

    assert TWO_FILES.header in prompt
    assert prompt.endswith("QUESTION: why?")
    assert "SIDE A" in prompt
    assert "SIDE B" in prompt
    assert selected == chunks


def test_two_files_carry_the_last_answer_after_the_parts():
    chunks = (chunk(0, side="A"), chunk(0, side="B"))

    prompt, _ = build_answer_prompt(
        chunks, question="why is that?", files=2, last_answer="1. a  2. b"
    )

    assert prompt.index("word word word") < prompt.index(
        "The last answer the tool gave:"
    )
    assert prompt.index("The last answer the tool gave:") < prompt.index("QUESTION:")


def test_two_files_that_are_too_big_keep_the_prompt_inside_the_budget():
    chunks = tuple(chunk(index, words=300, side="A") for index in range(100)) + tuple(
        chunk(index, words=300, side="B") for index in range(100)
    )

    prompt, selected = build_answer_prompt(
        chunks, question="why?", files=2, last_answer="x" * 5_000
    )

    assert 0 < len(selected) < len(chunks)
    assert estimate_tokens(prompt) <= PROMPT_BUDGET


@pytest.mark.parametrize(("files", "verb"), [(1, "read"), (2, "compare")])
def test_a_refusal_says_whether_the_person_asked_to_read_or_to_compare(files, verb):
    with pytest.raises(ArtifactsTooLargeToCompare, match=f"too large to {verb}"):
        build_answer_prompt(
            (chunk(0, words=100_000),), question="what is this?", files=files
        )

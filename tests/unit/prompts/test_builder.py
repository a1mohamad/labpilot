import pytest

from labpilot.ingest import Chunk
from labpilot.prompts import FULL, build_prompt, reserve
from labpilot.tokens import estimate_tokens


def _chunk(side: str, index: int, text: str = "body") -> Chunk:
    return Chunk(
        text=text,
        source="f.py",
        start_line=1,
        end_line=1,
        side=side,
        artifact_id="a",
        chunk_index=index,
        header="[f.py · lines 1-1]",
    )


def test_the_question_comes_last():
    chunks = (_chunk("A", 0),)

    prompt = build_prompt(chunks, chunks, question="why?", instructions=FULL)

    assert prompt.rstrip().endswith("QUESTION: why?")


def test_the_instructions_come_before_the_chunks():
    chunks = (_chunk("A", 0),)

    prompt = build_prompt(chunks, chunks, question="why?", instructions=FULL)

    assert prompt.index("RULES") < prompt.index("SIDE A")


def test_an_empty_question_is_our_bug():
    chunks = (_chunk("A", 0),)

    with pytest.raises(ValueError):
        build_prompt(chunks, chunks, question="   ", instructions=FULL)


def test_the_same_inputs_give_the_same_prompt():
    chunks = (_chunk("A", 0), _chunk("B", 0))

    first = build_prompt(chunks, chunks, question="why?", instructions=FULL)
    second = build_prompt(chunks, chunks, question="why?", instructions=FULL)

    assert first == second


def test_reserve_leaves_out_the_chunk_text():
    chunks = (_chunk("A", 0, text="X" * 9000),)

    room = reserve(chunks, question="why?", instructions=FULL)

    assert room < estimate_tokens("X" * 9000)

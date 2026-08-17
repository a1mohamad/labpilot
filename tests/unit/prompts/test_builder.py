import pytest

from labpilot.ingest import Chunk
from labpilot.prompts import COMPARE, FULL, PRIOR_HEADING, build_prompt, reserve
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
    chunks = (_chunk("A", 0, text="X" * 60_000),)

    room = reserve(chunks, question="why?", instructions=FULL)

    assert room < estimate_tokens("X" * 60_000)


def test_reserve_counts_the_instructions_and_the_outline():
    chunks = (_chunk("A", 0), _chunk("B", 0))

    room = reserve(chunks, question="why?", instructions=FULL)

    assert room > estimate_tokens(FULL.header)


def test_prior_findings_reach_the_prompt_under_their_own_heading():
    chunks = (_chunk("A", 0), _chunk("B", 0))

    prompt = build_prompt(
        chunks,
        chunks,
        question="why?",
        instructions=COMPARE,
        prior="| P1 | waste | a helper defined and never called |",
    )

    block = f"\n\n\n{PRIOR_HEADING}\n\n"
    assert block in prompt
    assert "a helper defined and never called" in prompt
    assert prompt.index(block) < prompt.index("QUESTION: why?")


def test_no_prior_findings_adds_no_block():
    chunks = (_chunk("A", 0),)
    block = f"\n\n\n{PRIOR_HEADING}\n\n"

    for empty in ("", "   \n  "):
        prompt = build_prompt(
            chunks, chunks, question="why?", instructions=COMPARE, prior=empty
        )

        # the heading is named in COMPARE's own instructions; only the injected
        # block must be absent
        assert block not in prompt
        assert PRIOR_HEADING in prompt


def test_reserve_counts_the_prior_findings_it_will_send():
    chunks = (_chunk("A", 0), _chunk("B", 0))
    prior = "| P1 | defect | " + "X" * 4_000

    without = reserve(chunks, question="why?", instructions=COMPARE)
    with_prior = reserve(chunks, question="why?", instructions=COMPARE, prior=prior)

    assert with_prior > without + estimate_tokens("X" * 4_000) - 20

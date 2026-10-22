from labpilot.ingest import Chunk
from labpilot.prompts import ONE_FILE, build_prompt, last_answer_block, reserve
from labpilot.tokens import estimate_tokens


def chunk():
    return Chunk(
        text="lr = 3e-4",
        source="m.py",
        start_line=1,
        end_line=2,
        side="B",
        artifact_id="B-1",
        chunk_index=0,
    )


def test_a_block_is_made_only_when_there_is_an_answer():
    assert last_answer_block("   ") == ""
    assert last_answer_block("an answer") == "The last answer the tool gave:\nan answer"


def test_the_last_answer_sits_after_the_parts_and_before_the_question():
    chunks = (chunk(),)

    prompt = build_prompt(
        chunks,
        chunks,
        question="do it",
        instructions=ONE_FILE,
        last_answer="1. a 2. b",
    )

    assert (
        prompt.index("lr = 3e-4")
        < prompt.index("The last answer the tool gave:")
        < prompt.index("QUESTION: do it")
    )


def test_without_a_last_answer_the_prompt_is_the_same_as_before():
    chunks = (chunk(),)

    plain = build_prompt(chunks, chunks, question="do it", instructions=ONE_FILE)
    empty = build_prompt(
        chunks, chunks, question="do it", instructions=ONE_FILE, last_answer=""
    )

    assert plain == empty
    assert "The last answer the tool gave:" not in plain


def test_reserve_counts_the_last_answer():
    chunks = (chunk(),)

    without = reserve(chunks, question="do it", instructions=ONE_FILE)
    with_answer = reserve(
        chunks, question="do it", instructions=ONE_FILE, last_answer="x" * 900
    )

    assert with_answer - without >= estimate_tokens("x" * 900)

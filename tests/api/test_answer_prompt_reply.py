"""What the person said when the run asked them a question reaches the prompt
(D109), for every number of files, and only when there is something to say."""

from __future__ import annotations

import pytest

from labpilot.api.prompting import build_answer_prompt
from labpilot.ingest import Chunk
from labpilot.prompts import USER_REPLY_NOTE

EXCHANGE = "Asked: What F1 did you get?\nAnswer: 0.82 on validation"


def part(side: str, index: int) -> Chunk:
    return Chunk(
        text=f"line {index} of {side}",
        source=f"{side}.py",
        start_line=1,
        end_line=2,
        side=side,
        artifact_id=f"{side}-1",
        chunk_index=index,
        header=f"[{side}.py]",
    )


@pytest.mark.parametrize("files", [0, 1, 2])
def test_the_reply_and_its_note_are_in_the_prompt(files):
    chunks = tuple(part(side, 0) for side in ("A", "B")[:files])

    prompt, _ = build_answer_prompt(
        chunks, question="why lower?", files=files, user_reply=EXCHANGE
    )

    assert USER_REPLY_NOTE in prompt
    assert "Answer: 0.82 on validation" in prompt


@pytest.mark.parametrize("files", [0, 1, 2])
def test_no_reply_leaves_no_note_at_all(files):
    chunks = tuple(part(side, 0) for side in ("A", "B")[:files])

    prompt, _ = build_answer_prompt(chunks, question="why lower?", files=files)

    assert USER_REPLY_NOTE not in prompt


def test_the_reply_sits_after_the_files_with_the_question_last():
    chunks = (part("A", 0), part("B", 0))

    prompt, _ = build_answer_prompt(
        chunks, question="why lower?", files=2, user_reply=EXCHANGE
    )

    assert prompt.index("line 0 of B") < prompt.index("why lower?")
    assert prompt.index("why lower?") < prompt.index("Answer: 0.82 on validation")

"""What is allowed into the saved chat, without a database.

LangGraph writes the state to Postgres as bytes and reads it back later. A class
it has not been told about does not raise when it is read: it quietly comes
back as a plain dict and leaves one log line. So these tests look at the TYPE
that comes back, which is the only thing that shows the difference.
"""

import logging

import pytest

from labpilot.api.checkpoints import SERDE, open_saver
from labpilot.ingest import Chunk
from labpilot.llm import Attempt, LLMResult
from labpilot.store import ArtifactRecord, StoredArtifact

RECORD = ArtifactRecord(
    id="A-x", name="paper.md", side="A", embedding_model="codestral-embed", dim=3
)
CHUNK = Chunk(
    text="lr = 3e-4",
    source="train.py",
    start_line=1,
    end_line=1,
    side="B",
    artifact_id="B-x",
    chunk_index=0,
)
RESULT = LLMResult(
    text="an answer",
    model="fake",
    tier=1,
    finish_reason="STOP",
    attempts=(Attempt(tier=1, model="other", error="HTTP 429"),),
)
STORED = StoredArtifact(artifact=RECORD, chunks=1, characters=9)


def round_trip(value):
    return SERDE.loads_typed(SERDE.dumps_typed(value))


@pytest.mark.parametrize(
    "value", [CHUNK, RESULT, STORED, RECORD], ids=lambda value: type(value).__name__
)
def test_every_class_in_the_state_comes_back_as_itself(value, caplog):
    with caplog.at_level(logging.WARNING):
        back = round_trip(value)

    assert type(back) is type(value)
    assert caplog.text == ""


def test_a_class_nested_inside_another_comes_back_as_itself_too():
    back = round_trip(RESULT)

    assert isinstance(back.attempts[0], Attempt)


def test_the_saver_uses_our_list_of_classes():
    assert open_saver(object()).serde is SERDE

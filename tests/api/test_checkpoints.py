"""What is allowed into the saved chat, without a database.

LangGraph writes the state to Postgres as bytes and reads it back later. A class
it has not been told about does not raise when it is read: it quietly comes
back as a plain dict and leaves one log line. So these tests look at the TYPE
that comes back, which is the only thing that shows the difference.
"""

import logging

import pytest

from labpilot.agent import Plan, Query
from labpilot.api.checkpoints import SERDE, _OneAtATime, open_saver
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
STORED = StoredArtifact(artifact=RECORD, chunks=1, files=1, characters=9)
PLAN = Plan(
    steps=("find_bugs",),
    queries=(Query("B", "CLIP_NORM"),),
)


def round_trip(value):
    return SERDE.loads_typed(SERDE.dumps_typed(value))


@pytest.mark.parametrize(
    "value",
    [CHUNK, RESULT, STORED, RECORD, PLAN],
    ids=lambda value: type(value).__name__,
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


def test_a_plan_comes_back_with_its_queries_as_queries():
    back = round_trip(PLAN)

    assert [type(query) for query in back.queries] == [Query]
    assert list(back.steps) == list(PLAN.steps)
    assert list(back.queries) == list(PLAN.queries)
    assert back.source == PLAN.source


def test_the_saver_does_not_use_pipeline_mode():
    assert open_saver(object()).supports_pipeline is False


class Recorder:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append(("execute", query, params))

    def executemany(self, query, params_seq):
        self.calls.append(("executemany", query, list(params_seq)))

    def fetchone(self):
        return "row"

    def __iter__(self):
        return iter(["a", "b"])


def test_many_rows_are_sent_one_statement_at_a_time_and_never_as_a_batch():
    cursor = Recorder()

    _OneAtATime(cursor).executemany("insert", [(1,), (2,), (3,)])

    assert cursor.calls == [
        ("execute", "insert", (1,)),
        ("execute", "insert", (2,)),
        ("execute", "insert", (3,)),
    ]


def test_everything_else_goes_straight_to_the_real_cursor():
    cursor = _OneAtATime(Recorder())

    assert cursor.fetchone() == "row"
    assert list(cursor) == ["a", "b"]

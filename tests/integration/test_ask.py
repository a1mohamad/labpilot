"""The ask ladder, against a real database.

`database` marked: no API quota, but it needs real rows, because the whole
point of step 1 was that the stuff decision is made from stored aggregates
rather than from anything held in memory.
"""

from __future__ import annotations

import pytest

from labpilot.api import asking, searching
from labpilot.api.checkpoints import open_saver
from labpilot.api.errors import (
    ArtifactChanged,
    ArtifactSidesClash,
    UnknownArtifactId,
)
from labpilot.llm import AllFreeTiersExhausted, LLMResult
from labpilot.prompts import SUMMARY_MAX_TOKENS
from labpilot.prompts.builder import SUMMARIES_NOTE
from labpilot.store import (
    ArtifactRecord,
    ChunkRecord,
    ModelMismatch,
    make_pool,
    write_artifact,
)

pytestmark = pytest.mark.database

MODEL = "codestral-embed"
DIM = 3
V = (1.0, 0.0, 0.0)


# What the planner's tool call returns: a plan with one query of its own.
PLAN = {"steps": [], "queries": [{"side": "B", "text": "weights"}]}


class FakeClient:
    """Answers the planner with PLAN and the report with a fixed text.

    The two kinds of call are kept apart, so `prompts` still holds the report
    prompts only.
    """

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.planner_prompts: list[str] = []
        self.summary_prompts: list[str] = []

    def generate(
        self, prompt: str, *, max_tokens: int = 0, tool=None, problem_with=None
    ) -> LLMResult:
        if tool is not None:
            self.planner_prompts.append(prompt)
            return LLMResult(
                text="a plan",
                model="fake",
                tier=1,
                finish_reason="STOP",
                arguments=PLAN,
            )
        if max_tokens == SUMMARY_MAX_TOKENS:
            self.summary_prompts.append(prompt)
            return LLMResult(
                text="a summary", model="fake", tier=1, finish_reason="STOP"
            )
        self.prompts.append(prompt)
        return LLMResult(text="an answer", model="fake", tier=1, finish_reason="STOP")


class SummariesFail(FakeClient):
    """The same client, except that a summary call fails on every tier.

    `only` limits the failure to the summary prompts that contain that text, so
    one side can fail while the other is still summarized.
    """

    def __init__(self, only: str = "") -> None:
        super().__init__()
        self.only = only

    def generate(
        self, prompt: str, *, max_tokens: int = 0, tool=None, problem_with=None
    ) -> LLMResult:
        if tool is None and max_tokens == SUMMARY_MAX_TOKENS and self.only in prompt:
            raise AllFreeTiersExhausted(())
        return super().generate(
            prompt, max_tokens=max_tokens, tool=tool, problem_with=problem_with
        )


def stored(db, side: str, *, parts: int, words: int) -> str:
    artifact_id = f"{side}-fixture"
    write_artifact(
        db,
        ArtifactRecord(
            id=artifact_id,
            name=f"{side}.py",
            side=side,
            embedding_model=MODEL,
            dim=DIM,
        ),
        [
            ChunkRecord(
                chunk_index=i,
                text=" ".join(["word"] * words),
                header=f"[{side}.py - part {i}]",
                source=f"{side}.py",
                start_line=i,
                end_line=i,
                vector=V,
            )
            for i in range(parts)
        ],
    )
    return artifact_id


def test_a_small_pair_is_stuffed_and_never_searched(db, monkeypatch):
    """Step 1 of the ladder, and it is the step that keeps being under-weighted.

    When the corpus fits, retrieval is not neutral but HARMFUL - a bad
    retriever can hide the very line the report needed. So search must not run
    at all, and the way to prove that is to make it explode if it does.
    """
    a = stored(db, "A", parts=3, words=20)
    b = stored(db, "B", parts=3, words=20)
    monkeypatch.setattr(
        searching, "search", lambda *a, **k: pytest.fail("search must not run")
    )

    result = asking.ask(db, a, b, question="why?", client=FakeClient())

    assert len(result.chunks) == 6, "every stored row was read back"


def test_a_large_pair_is_searched_and_admits_how_much_it_read(db, monkeypatch):
    """The other branch, and the honesty that must come with it.

    A searched side holds only what retrieval returned, so the prompt has to
    say so - otherwise the model treats a handful of chunks as the whole file.
    """
    a = stored(db, "A", parts=60, words=300)
    b = stored(db, "B", parts=60, words=300)
    monkeypatch.setattr(searching, "_embed_question", lambda *a, **k: V)
    client = FakeClient()

    asking.ask(db, a, b, question="why?", client=client)

    assert "NOT searched" in client.prompts[0]
    assert "of 60 parts" in client.prompts[0]


def test_both_summaries_reach_the_report_when_the_pair_is_stuffed(db):
    """The summaries are written into the prompt of the answer, before the parts.

    They are made at the start of every message, in parallel with the planner,
    and only `respond` reads them. The stuffed path reaches `respond` without a
    search, so it needs its own check.
    """
    a = stored(db, "A", parts=3, words=20)
    b = stored(db, "B", parts=3, words=20)
    client = FakeClient()

    asking.ask(db, a, b, question="why?", client=client)

    report = client.prompts[0]
    assert "SUMMARY OF SIDE A\n\na summary" in report
    assert "SUMMARY OF SIDE B\n\na summary" in report
    assert report.index(SUMMARIES_NOTE) < report.index("[A.py - part 0]")


def test_both_summaries_reach_the_report_when_the_pair_is_searched(db, monkeypatch):
    a = stored(db, "A", parts=60, words=300)
    b = stored(db, "B", parts=60, words=300)
    monkeypatch.setattr(searching, "_embed_question", lambda *a, **k: V)
    client = FakeClient()

    asking.ask(db, a, b, question="why?", client=client)

    report = client.prompts[0]
    assert "SUMMARY OF SIDE A\n\na summary" in report
    assert "SUMMARY OF SIDE B\n\na summary" in report
    assert report.index("SUMMARY OF SIDE A") < report.index("NOT searched")


def test_each_side_is_summarized_from_its_own_parts(db):
    """A summary of A written from B's parts would be a quiet, wrong report."""
    a = stored(db, "A", parts=3, words=20)
    b = stored(db, "B", parts=3, words=20)
    client = FakeClient()

    asking.ask(db, a, b, question="why?", client=client)

    assert sorted(
        ("[A.py - part 0]" in prompt, "[B.py - part 0]" in prompt)
        for prompt in client.summary_prompts
    ) == [(False, True), (True, False)]


def test_a_report_is_still_written_when_every_summary_fails(db):
    """A summary is a guide, not the evidence: no summary, no block, same report."""
    a = stored(db, "A", parts=3, words=20)
    b = stored(db, "B", parts=3, words=20)
    client = SummariesFail()

    comparison = asking.ask(db, a, b, question="why?", client=client)

    assert comparison.result.text == "an answer"
    assert "SUMMARY OF SIDE" not in client.prompts[0]
    assert SUMMARIES_NOTE not in client.prompts[0]


def test_one_failed_summary_does_not_remove_the_other(db):
    a = stored(db, "A", parts=3, words=20)
    b = stored(db, "B", parts=3, words=20)
    client = SummariesFail(only="[A.py - part 0]")

    asking.ask(db, a, b, question="why?", client=client)

    report = client.prompts[0]
    assert "SUMMARY OF SIDE A" not in report
    assert "SUMMARY OF SIDE B\n\na summary" in report


def test_an_unknown_artifact_id_is_refused(db):
    """Not a 503 and not an empty answer.

    StorageUnavailable is 503 because the database being down is OUR failure.
    An id we never stored is a fact about the REQUEST, and reporting it as
    "nothing matched" would be a lie about whose fault it is.
    """
    b = stored(db, "B", parts=2, words=20)

    with pytest.raises(UnknownArtifactId, match="ghost"):
        asking.ask(db, "ghost", b, question="why?", client=FakeClient())


def test_a_large_pair_is_searched_through_a_real_pool(db, schema_url, monkeypatch):
    """Both sides come back through pooled connections on the TEST schema.

    The pool is built closed and opens on the first search. If its
    connections did not carry the schema option or did not autocommit, the
    search would find no artifact at all.
    """
    a = stored(db, "A", parts=60, words=300)
    b = stored(db, "B", parts=60, words=300)
    monkeypatch.setattr(searching, "_embed_question", lambda *a, **k: V)
    pool = make_pool(schema_url)
    assert pool.closed

    try:
        comparison = asking.ask(
            db, a, b, question="why?", client=FakeClient(), pool=pool
        )
        opened_by_the_search = not pool.closed
    finally:
        pool.close()

    assert opened_by_the_search
    assert {chunk.side for chunk in comparison.chunks} == {"A", "B"}


def test_two_artifacts_from_the_same_slot_are_refused(db):
    """The side is baked into the id by _artifact_id, so two A ids is not a pair.

    It would build a prompt with no side B at all, and every B-walk in the
    instructions would have nothing to walk.
    """
    a = stored(db, "A", parts=2, words=20)

    with pytest.raises(ArtifactSidesClash):
        asking.ask(db, a, a, question="why?", client=FakeClient())


def test_a_re_ingest_mid_request_is_a_conflict_and_not_our_bug(db, monkeypatch):
    """ModelMismatch is REACHABLE, and reasoning said it was not.

    The draft left it in ALLOWED_TO_ESCAPE because search() is handed the model
    from the very row it checks against. But measure() and search() are two
    round trips, and write_artifact DELETES then re-inserts - so re-ingesting
    an artifact with a different embedder moves the model under a request
    already in flight.

    Nobody's bug, and asking again fixes it: a 500 would blame us and a 404
    would blame the user, so it is a 409.
    """
    a_id = stored(db, "A", parts=400, words=60)
    b_id = stored(db, "B", parts=400, words=60)
    monkeypatch.setattr(searching, "_embed_question", lambda *a, **k: V)

    def re_ingested(*args, **kwargs):
        raise ModelMismatch(
            "artifact was embedded with 'mistral-embed', not 'codestral-embed'"
        )

    monkeypatch.setattr(searching, "search", re_ingested)

    with pytest.raises(ArtifactChanged, match="ask again"):
        asking.ask(db, a_id, b_id, question="why?", client=FakeClient())


def test_the_side_comes_from_the_stored_row_and_not_from_the_slot(db, monkeypatch):
    """Sending B in the first slot must still produce an A-vs-B comparison.

    The side is baked into the id by _artifact_id, so the row already knows
    it. Letting the SLOT decide would be a second source of truth for one
    fact, and the two would disagree the first time a user filled the boxes in
    the order they happened to have the files.
    """
    a_id = stored(db, "A", parts=2, words=5)
    b_id = stored(db, "B", parts=2, words=5)
    client = FakeClient()

    # deliberately the wrong way round
    comparison = asking.ask(db, b_id, a_id, question="why?", client=client)

    by_side = {chunk.side for chunk in comparison.chunks}
    assert by_side == {"A", "B"}
    assert all(
        chunk.artifact_id.startswith(chunk.side) for chunk in comparison.chunks
    ), "a chunk's side must match the artifact it was stored under"

    prompt = client.prompts[0]
    assert "SIDE A" in prompt
    assert "SIDE B" in prompt


# ---------------------------------------------------------------------------
# CHAT MEMORY: the saver, a real Postgres, and the clean-up after each message.
# ---------------------------------------------------------------------------


def rows(db, table: str, thread_id: str) -> int:
    with db.cursor() as cur:
        cur.execute(f"select count(*) from {table} where thread_id = %s", (thread_id,))
        return cur.fetchone()[0]


def talk(db, thread_id: str, *questions: str) -> None:
    a = stored(db, "A", parts=3, words=20)
    b = stored(db, "B", parts=3, words=20)
    for question in questions:
        asking.ask(
            db, a, b, question=question, client=FakeClient(), thread_id=thread_id
        )


def test_a_chat_remembers_every_question_and_comes_back_as_real_objects(
    db, chat_tables, caplog
):
    talk(db, "chat-memory", "first?", "second?", "third?")

    saved = open_saver(db).get_tuple({"configurable": {"thread_id": "chat-memory"}})
    values = saved.checkpoint["channel_values"]

    assert values["history"] == ["first?", "second?", "third?"]
    assert isinstance(values["result"], LLMResult)
    assert "langgraph" not in caplog.text


def test_only_the_newest_copy_of_a_chat_stays_in_the_database(db, chat_tables):
    talk(db, "chat-one-copy", "first?")
    blobs_after_one_message = rows(db, "checkpoint_blobs", "chat-one-copy")

    talk(db, "chat-one-copy", "second?", "third?")

    assert rows(db, "checkpoints", "chat-one-copy") == 1
    assert rows(db, "checkpoint_writes", "chat-one-copy") == 0
    assert rows(db, "checkpoint_blobs", "chat-one-copy") == blobs_after_one_message


def test_cleaning_one_chat_leaves_another_chat_alone(db, chat_tables):
    talk(db, "chat-left-alone", "only?")
    copies_before = rows(db, "checkpoints", "chat-left-alone")
    blobs_before = rows(db, "checkpoint_blobs", "chat-left-alone")

    talk(db, "chat-busy", "first?", "second?", "third?")

    assert rows(db, "checkpoints", "chat-left-alone") == copies_before
    assert rows(db, "checkpoint_blobs", "chat-left-alone") == blobs_before


def test_a_question_with_no_chat_saves_nothing(db, chat_tables):
    a = stored(db, "A", parts=3, words=20)
    b = stored(db, "B", parts=3, words=20)
    with db.cursor() as cur:
        cur.execute("select count(*) from checkpoints")
        before = cur.fetchone()[0]

    asking.ask(db, a, b, question="no chat?", client=FakeClient())

    with db.cursor() as cur:
        cur.execute("select count(*) from checkpoints")
        assert cur.fetchone()[0] == before

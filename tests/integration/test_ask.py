"""The ask ladder, against a real database.

`database` marked: no API quota, but it needs real rows, because the whole
point of step 1 was that the stuff decision is made from stored aggregates
rather than from anything held in memory.
"""

from __future__ import annotations

from collections import Counter

import pytest

from labpilot.agent import Plan
from labpilot.api import asking, searching
from labpilot.api.checkpoints import open_saver
from labpilot.api.errors import (
    ArtifactChanged,
    ArtifactSidesClash,
    UnknownArtifactId,
)
from labpilot.ingest import Chunk
from labpilot.llm import AllFreeTiersExhausted, LLMResult
from labpilot.prompts import FOLLOW_UP_MAX_TOKENS, SUMMARY_MAX_TOKENS
from labpilot.prompts.builder import SUMMARIES_NOTE
from labpilot.store import (
    ArtifactRecord,
    ChunkRecord,
    ModelMismatch,
    StoredArtifact,
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

    def __init__(self, plan: dict | None = None, rewrite_to: str | None = None) -> None:
        self.plan = PLAN if plan is None else plan
        self.rewrite_to = rewrite_to
        self.prompts: list[str] = []
        self.planner_prompts: list[str] = []
        self.summary_prompts: list[str] = []
        self.follow_up_prompts: list[str] = []

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
                arguments=self.plan,
            )
        if max_tokens == FOLLOW_UP_MAX_TOKENS:
            self.follow_up_prompts.append(prompt)
            return LLMResult(
                text=self.standalone(prompt),
                model="fake",
                tier=1,
                finish_reason="STOP",
            )
        if max_tokens == SUMMARY_MAX_TOKENS:
            self.summary_prompts.append(prompt)
            return LLMResult(
                text="a summary", model="fake", tier=1, finish_reason="STOP"
            )
        self.prompts.append(prompt)
        return LLMResult(text="an answer", model="fake", tier=1, finish_reason="STOP")

    def standalone(self, prompt: str) -> str:
        """The rewrite of a follow-up: the fixed text, or the question unchanged."""
        if self.rewrite_to is not None:
            return self.rewrite_to
        return prompt.split("New question:\n", 1)[1].rsplit("\n\n", 1)[0]


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


class PlannerFails(FakeClient):
    """The same client, except that the planner call fails on every tier."""

    def generate(
        self, prompt: str, *, max_tokens: int = 0, tool=None, problem_with=None
    ) -> LLMResult:
        if tool is not None:
            raise AllFreeTiersExhausted(())
        return super().generate(
            prompt, max_tokens=max_tokens, tool=tool, problem_with=problem_with
        )


class RewriteFails(FakeClient):
    """The same client, except that the rewrite call fails on every tier."""

    def generate(
        self, prompt: str, *, max_tokens: int = 0, tool=None, problem_with=None
    ) -> LLMResult:
        if tool is None and max_tokens == FOLLOW_UP_MAX_TOKENS:
            raise AllFreeTiersExhausted(())
        return super().generate(
            prompt, max_tokens=max_tokens, tool=tool, problem_with=problem_with
        )


def watched_searches(monkeypatch) -> list[str]:
    """The artifact id of every vector search, in the order they ran.

    The real search still runs, so the rows are really read. Two searches of
    one side are two entries with the same id.
    """
    real = searching.search
    seen: list[str] = []

    def watch(conn, artifact_id, vector, **kwargs):
        seen.append(artifact_id)
        return real(conn, artifact_id, vector, **kwargs)

    monkeypatch.setattr(searching, "search", watch)
    return seen


def embedded_texts(monkeypatch) -> list[str]:
    """Every text that was embedded as a search question."""
    seen: list[str] = []

    def embed(text, *, model):
        seen.append(text)
        return V

    monkeypatch.setattr(searching, "_embed_question", embed)
    return seen


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


def test_many_queries_make_one_pile_per_side_with_no_duplicates(db, monkeypatch):
    """What reaches the prompt must not grow with the number of queries (D53).

    Every vector is the same here, so every query finds nearly the same rows:
    without the merge, three queries would put each chunk in the prompt three
    times. And the cut must be the one for a side with no reranker (the rerank
    chain is empty under test), not a number per query.
    """
    a = stored(db, "A", parts=60, words=300)
    b = stored(db, "B", parts=60, words=300)
    texts = embedded_texts(monkeypatch)
    searched = watched_searches(monkeypatch)
    plan = {
        "steps": [],
        "queries": [
            {"side": "B", "text": "weights"},
            {"side": "B", "text": "bias"},
            {"side": "A", "text": "learning rate"},
        ],
    }

    comparison = asking.ask(db, a, b, question="why?", client=FakeClient(plan))

    keys = [(chunk.artifact_id, chunk.chunk_index) for chunk in comparison.chunks]
    assert len(keys) == len(set(keys)), "a chunk found by two queries came twice"
    assert Counter(chunk.side for chunk in comparison.chunks) == {
        "A": searching.VECTOR_TOP_N,
        "B": searching.VECTOR_TOP_N,
    }
    # the question on each side, then the three queries of the plan
    assert sorted(searched) == ["A-fixture"] * 2 + ["B-fixture"] * 3
    assert set(texts) == {"why?", "weights", "bias", "learning rate"}


def test_a_report_is_still_written_when_the_planner_fails_on_every_tier(
    db, monkeypatch
):
    """The planner only guesses where to look, so it must never stop the answer.

    The default plan searches the question on each side, and that is exactly
    what the report is written from.
    """
    a = stored(db, "A", parts=60, words=300)
    b = stored(db, "B", parts=60, words=300)
    texts = embedded_texts(monkeypatch)
    searched = watched_searches(monkeypatch)
    client = PlannerFails()

    comparison = asking.ask(db, a, b, question="why?", client=client)

    assert comparison.result.text == "an answer"
    assert sorted(searched) == ["A-fixture", "B-fixture"]
    assert texts == ["why?", "why?"]
    assert "NOT searched" in client.prompts[0]


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


def test_a_follow_up_is_rewritten_and_the_chat_saves_the_standalone_question(
    db, chat_tables
):
    a = stored(db, "A", parts=3, words=20)
    b = stored(db, "B", parts=3, words=20)
    client = FakeClient(rewrite_to="what is the learning rate in A and B?")

    for question in ("why do results differ?", "and the learning rate?"):
        asking.ask(
            db, a, b, question=question, client=client, thread_id="chat-follow-up"
        )

    saved = open_saver(db).get_tuple({"configurable": {"thread_id": "chat-follow-up"}})
    values = saved.checkpoint["channel_values"]

    assert values["history"] == [
        "why do results differ?",
        "what is the learning rate in A and B?",
    ]
    assert len(client.follow_up_prompts) == 1
    assert "why do results differ?" in client.follow_up_prompts[0]
    assert "what is the learning rate in A and B?" in client.prompts[-1]
    # the answer of message 1 was saved, and the rewrite of message 2 was given it
    assert values["last_answer"] == "an answer"
    assert "The last answer the tool gave:\nan answer" in client.follow_up_prompts[0]


def test_a_follow_up_is_searched_as_the_standalone_question(
    db, chat_tables, monkeypatch
):
    """On the searched path the rewritten question is what gets embedded.

    The small pair above is stuffed, so it never searches. This one is too big
    to stuff, so the question is embedded once for each side, and the short
    follow-up must never reach the embedder.
    """
    a = stored(db, "A", parts=60, words=300)
    b = stored(db, "B", parts=60, words=300)
    embedded = embedded_texts(monkeypatch)
    client = FakeClient(rewrite_to="what is the learning rate in A and B?")

    for question in ("why do results differ?", "and the learning rate?"):
        asking.ask(
            db, a, b, question=question, client=client, thread_id="chat-follow-search"
        )

    assert embedded.count("what is the learning rate in A and B?") == 2
    assert "and the learning rate?" not in embedded


def test_a_report_is_still_written_when_the_rewrite_fails_on_every_tier(
    db, chat_tables
):
    a = stored(db, "A", parts=3, words=20)
    b = stored(db, "B", parts=3, words=20)
    client = RewriteFails()

    for question in ("why do results differ?", "and the learning rate?"):
        comparison = asking.ask(
            db, a, b, question=question, client=client, thread_id="chat-rewrite-fails"
        )

    saved = open_saver(db).get_tuple(
        {"configurable": {"thread_id": "chat-rewrite-fails"}}
    )
    values = saved.checkpoint["channel_values"]

    assert comparison.result.text == "an answer"
    assert values["history"] == ["why do results differ?", "and the learning rate?"]
    assert "and the learning rate?" in client.prompts[-1]


def test_a_question_with_no_file_is_a_chat_answer(db):
    client = FakeClient()

    comparison = asking.ask(
        db, "", "", question="explain gradient clipping", client=client
    )

    assert comparison.result.text == "an answer"
    assert comparison.chunks == ()
    assert comparison.totals is None
    assert len(client.prompts) == 1
    assert "No file was given with this question" in client.prompts[0]
    assert client.planner_prompts == []
    assert client.summary_prompts == []


def test_a_question_about_one_file_is_answered_from_that_file_alone(db):
    a = stored(db, "A", parts=3, words=20)
    plan = {"steps": [], "queries": [{"side": "A", "text": "weights"}]}
    client = FakeClient(plan=plan)

    comparison = asking.ask(db, a, "", question="what does this do?", client=client)

    prompt = client.prompts[0]
    assert "Write ANSWER, then PROBLEMS now." in prompt
    assert "DIVERGENCES" not in prompt
    assert "SIDE A" in prompt
    assert "SIDE B" not in prompt
    assert len(client.summary_prompts) == 1
    assert {chunk.side for chunk in comparison.chunks} == {"A"}


def test_a_big_single_file_is_searched_and_ranked_for_its_one_side(db, monkeypatch):
    b = stored(db, "B", parts=60, words=300)
    embedded = embedded_texts(monkeypatch)

    comparison = asking.ask(db, "", b, question="why is it slow?", client=FakeClient())

    assert {chunk.side for chunk in comparison.chunks} == {"B"}
    assert len(comparison.chunks) == searching.VECTOR_TOP_N
    assert comparison.totals == {"B": 60}
    assert embedded.count("why is it slow?") == 1


def test_in_a_chat_with_no_file_the_last_answer_reaches_the_next_prompt(
    db, chat_tables
):
    client = FakeClient(rewrite_to="write the code for the second change")

    for question in ("what can I change?", "do the second one"):
        asking.ask(
            db, "", "", question=question, client=client, thread_id="chat-no-file"
        )

    label = "The last answer the tool gave:\nan answer"
    assert label not in client.prompts[0]
    assert label in client.follow_up_prompts[0]
    assert label in client.prompts[-1]
    assert client.prompts[-1].endswith("QUESTION: write the code for the second change")


def test_a_follow_up_about_two_files_carries_the_last_answer_into_the_report(
    db, chat_tables
):
    a = stored(db, "A", parts=3, words=20)
    b = stored(db, "B", parts=3, words=20)
    client = FakeClient(rewrite_to="explain the last answer more simply")

    for question in ("why do results differ?", "explain that more simply"):
        asking.ask(
            db, a, b, question=question, client=client, thread_id="chat-two-files"
        )

    label = "The last answer the tool gave:\nan answer"
    assert "Write ANSWER, COMPARABLE, DIFFERENCES" in client.prompts[0]
    assert label not in client.prompts[0]
    assert label in client.prompts[-1]
    assert client.prompts[-1].endswith("QUESTION: explain the last answer more simply")


def test_a_lone_subject_sent_in_the_first_slot_is_still_searched_as_side_b(
    db, monkeypatch
):
    """The door takes one id in EITHER slot, so ask() must put it where it belongs.

    Left in slot `a`, the subject was searched as a side A that the question does
    not have, and the search failed on a missing key.
    """
    b = stored(db, "B", parts=60, words=300)
    embedded_texts(monkeypatch)

    comparison = asking.ask(db, b, "", question="why is it slow?", client=FakeClient())

    assert {chunk.side for chunk in comparison.chunks} == {"B"}
    assert comparison.totals == {"B": 60}


def test_a_chat_that_sends_fewer_files_drops_the_summary_of_the_missing_one(
    db, chat_tables
):
    """After a refresh the page sends only the files it remembers, in the SAME chat.

    The real saver keeps every state key between messages, so a summary written
    for a file in message 1 had to be cleared when message 2 did not send it.
    """
    a = stored(db, "A", parts=3, words=20)
    b = stored(db, "B", parts=3, words=20)
    client = FakeClient(rewrite_to="and what does B do?")

    asking.ask(
        db,
        a,
        b,
        question="why do results differ?",
        client=client,
        thread_id="chat-fewer",
    )
    asking.ask(
        db, "", b, question="and what does B do?", client=client, thread_id="chat-fewer"
    )

    assert "SUMMARY OF SIDE A" in client.prompts[0]
    assert "SUMMARY OF SIDE A" not in client.prompts[-1]
    assert "SUMMARY OF SIDE B" in client.prompts[-1]


def test_a_chat_on_the_searched_path_is_saved_and_comes_back_as_real_objects(
    db, chat_tables, monkeypatch, caplog
):
    """The searched path puts more kinds of value in the state than the stuffed one.

    The searches are started with a `Send` that carries the stored sides and a
    `Query`, the found lists are emptied at the end of the merge, and the plan
    is a `Plan`. A class the saver was not told about does not raise: it comes
    back as a plain dict and leaves one log line, so the next message fails far
    from the cause. The stuffed path above never meets any of this.

    It is also the only test whose checkpoint has a real size (about 150 KB). With
    the plain Postgres saver that save failed in about half the runs of an
    afternoon (`SSL error: bad length`, a libpq bug in pipeline mode) and in none
    of the runs of the next hour, so THIS TEST CANNOT HOLD THAT RULE: the network
    decides. The rule is held by the two unit tests of `open_saver` in
    tests/api/test_checkpoints.py. This one fires only when the network is in the
    bad mood, and then the message is the error above.
    """
    a = stored(db, "A", parts=60, words=300)
    b = stored(db, "B", parts=60, words=300)
    monkeypatch.setattr(searching, "_embed_question", lambda *a, **k: V)
    questions = ("first?", "second?")
    for question in questions:
        asking.ask(
            db, a, b, question=question, client=FakeClient(), thread_id="chat-search"
        )

    saved = open_saver(db).get_tuple({"configurable": {"thread_id": "chat-search"}})
    values = saved.checkpoint["channel_values"]

    assert values["history"] == list(questions)
    assert values["chunks"] and all(isinstance(c, Chunk) for c in values["chunks"])
    assert isinstance(values["plan"], Plan)
    assert all(isinstance(s, StoredArtifact) for s in values["sides"].values())
    assert values.get("found", []) == []
    assert "langgraph" not in caplog.text
    assert rows(db, "checkpoints", "chat-search") == 1


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

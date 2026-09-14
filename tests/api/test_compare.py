"""POST /compare, which now takes IDS.

No database and no provider: `connect` is stubbed and `ask` is replaced, so
these test the DOOR - the request shape, the envelope, and how a Comparison
becomes a response. The ladder behind it is tested against real rows in
tests/integration/test_ask.py.

THE UPLOAD TESTS THAT USED TO LIVE HERE MOVED to test_artifacts.py on
2026-09-14. They were never about comparing: read_artifact is the guard, it is
SHARED by both routes, and once /artifacts existed, testing it through
/compare was one test per COMBINATION rather than one per failure.
"""

from __future__ import annotations

import contextlib

import pytest

from labpilot.api.config import ApiConfig
from labpilot.api.contracts import Comparison
from labpilot.api.errors import (
    GenerationUnavailable,
    InvalidQuestion,
    UnknownArtifactId,
)
from labpilot.ingest import Chunk
from labpilot.llm import Attempt, LLMResult
from labpilot.store import ConnectionFailed

COMPARE = f"{ApiConfig.PREFIX}/compare"
BODY = {"a": "A-paper", "b": "B-code", "question": "why do they diverge?"}


@pytest.fixture
def no_database(monkeypatch):
    """The route opens a connection; nothing here should reach a real one."""
    monkeypatch.setattr(
        "labpilot.api.routers.compare.connect",
        lambda *a, **k: contextlib.nullcontext(object()),
    )


def chunk(side: str, index: int, text: str) -> Chunk:
    return Chunk(
        text=text,
        source="train.py" if side == "B" else "paper.md",
        start_line=index * 10 + 1,
        end_line=index * 10 + 3,
        side=side,
        artifact_id=f"{side}-x",
        chunk_index=index,
        header=f"[train.py - part {index}]",
    )


def answered(text: str = 'B adds them [B-0 "return x + y"].') -> Comparison:
    """A Comparison shaped the way `ask` returns one."""
    chunks = (chunk("A", 0, "it should add"), chunk("B", 0, "return x + y"))

    return Comparison(
        result=LLMResult(text=text, model="fake-model", tier=2, finish_reason="STOP"),
        chunks=chunks,
        selected=chunks,
        prompt="a prompt",
    )


def stub(monkeypatch, outcome) -> None:
    """Replace `ask` with a Comparison to return, or an error to raise."""

    def fake_ask(*args, **kwargs):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr("labpilot.api.services.ask", fake_ask)


def test_two_ids_and_a_question_are_enough(client, no_database, monkeypatch):
    """THE POINT OF THE SPLIT: no file crosses the wire to ask a question.

    Under the old shape every turn re-uploaded, re-chunked and re-embedded both
    sides - measured at about fifteen minutes per question for a FastAPI-sized
    repository. Ingest is paid once now, at POST /artifacts.
    """
    stub(monkeypatch, answered())

    response = client.post(COMPARE, json=BODY)

    assert response.status_code == 200
    assert response.json()["model"] == "fake-model"
    assert response.json()["tier"] == 2


def test_the_ids_reach_the_ask_path_in_the_slots_they_were_sent_in(
    client, no_database, monkeypatch
):
    """`a` and `b` are POSITIONAL in ask(), so swapping them swaps the sides.

    A is the reference and B is the subject - the instructions say so in every
    template - and a silent swap would compare the reference against itself
    while reporting nothing wrong.
    """
    seen = {}

    def fake_ask(conn, a_id, b_id, *, question, client):
        seen.update(a=a_id, b=b_id, question=question)
        return answered()

    monkeypatch.setattr("labpilot.api.services.ask", fake_ask)

    client.post(COMPARE, json=BODY)

    assert seen == {"a": "A-paper", "b": "B-code", "question": BODY["question"]}


def test_the_response_counts_the_chunks_of_each_side(client, no_database, monkeypatch):
    """`n/m chunks` is what proves to a user that the file was really read."""
    stub(monkeypatch, answered())

    chunks = client.post(COMPARE, json=BODY).json()["chunks"]

    assert chunks["A"] == {"total": 1, "sent": 1}
    assert chunks["B"] == {"total": 1, "sent": 1}


def test_a_resolved_citation_carries_the_real_line_number(
    client, no_database, monkeypatch
):
    """The one thing an endpoint adds over a print statement.

    The model gives a POINTER; we do the counting and read the line back from
    our own copy, never from the model. A model cannot count lines - given a
    header saying 579-604 it invents a plausible number inside that range.
    """
    stub(monkeypatch, answered())

    citations = client.post(COMPARE, json=BODY).json()["citations"]

    assert citations["written"] == 1
    assert citations["resolved"] == 1
    assert citations["resolved_list"][0]["source"] == "train.py"
    assert citations["resolved_list"][0]["line"] == 1


def test_a_citation_pointing_at_nothing_is_counted_but_not_resolved(
    client, no_database, monkeypatch
):
    """Invention must be VISIBLE, not silently dropped.

    A citation that resolves to nothing is how hallucination stops being an
    invisible failure and becomes a countable one.
    """
    stub(monkeypatch, answered(text='B does [B-0 "a line that is not there"].'))

    citations = client.post(COMPARE, json=BODY).json()["citations"]

    assert citations["written"] == 1
    assert citations["resolved"] == 0


def test_an_unknown_artifact_id_is_a_404_in_our_own_envelope(
    client, no_database, monkeypatch
):
    """404, and in the house envelope rather than FastAPI's own shape.

    StorageUnavailable is 503 because the database being down is OUR failure.
    An id we never stored is a fact about the REQUEST, and a 503 there would
    be a lie about whose fault it is.
    """
    stub(monkeypatch, UnknownArtifactId("no artifact 'ghost' is stored"))

    response = client.post(COMPARE, json=BODY)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_artifact"
    assert response.json()["error"]["request_id"]


def test_an_unreachable_database_is_our_fault_not_the_users(client, monkeypatch):
    """503, never 404 - the mirror of the test above.

    A 404 here would tell the user their artifact is missing when the truth is
    that our storage is down and their upload was fine.
    """

    def dead(*args, **kwargs):
        raise ConnectionFailed("could not reach the database")

    monkeypatch.setattr("labpilot.api.routers.compare.connect", dead)

    response = client.post(COMPARE, json=BODY)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "storage_unavailable"


def test_all_tiers_exhausted_reports_which_tiers_failed(
    client, no_database, monkeypatch
):
    """A 503 that NAMES every tier, so a dead provider is diagnosable.

    Without the list, a spent quota and a total outage look identical from
    outside the process.
    """
    stub(
        monkeypatch,
        GenerationUnavailable(
            "every free tier failed",
            attempts=(Attempt(tier=1, model="gemini-3.7-flash", error="HTTP 429"),),
        ),
    )

    response = client.post(COMPARE, json=BODY)

    assert response.status_code == 503
    assert response.json()["error"]["attempts"] == [
        {"tier": 1, "model": "gemini-3.7-flash", "error": "HTTP 429"}
    ]


def test_a_blank_question_answers_in_our_envelope_and_not_pydantics(
    client, no_database, monkeypatch
):
    """CompareRequest deliberately puts NO min_length on `question`.

    A constraint there would make FastAPI answer in ITS shape, and a client
    would have to parse two different error formats from one endpoint.
    """
    stub(monkeypatch, InvalidQuestion("question must not be empty"))

    response = client.post(COMPARE, json={**BODY, "question": "  "})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_question"


def test_a_missing_field_is_reported_in_the_same_envelope(client, no_database):
    """FastAPI's own validation must still come back in the house envelope."""
    response = client.post(COMPARE, json={"a": "A-paper", "question": "why?"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert "b" in response.json()["error"]["message"]


def test_the_old_upload_door_is_really_gone(client, no_database, monkeypatch):
    """Two doors for one job is what the split exists to remove.

    If multipart still worked here, every question would quietly go on
    re-chunking and re-embedding both sides, and nothing would report it.
    """
    stub(monkeypatch, answered())

    response = client.post(
        COMPARE,
        files={"a": ("a.md", b"# paper", "text/markdown")},
        data={"question": "why?"},
    )

    assert response.status_code == 422

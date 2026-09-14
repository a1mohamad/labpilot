"""The ask ladder, against a real database.

`database` marked: no API quota, but it needs real rows, because the whole
point of step 1 was that the stuff decision is made from stored aggregates
rather than from anything held in memory.
"""

from __future__ import annotations

import pytest

from labpilot.api import services
from labpilot.api.errors import ArtifactSidesClash, UnknownArtifactId
from labpilot.llm import LLMResult
from labpilot.store import ArtifactRecord, ChunkRecord, write_artifact

pytestmark = pytest.mark.database

MODEL = "codestral-embed"
DIM = 3
V = (1.0, 0.0, 0.0)


class FakeClient:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str, *, max_tokens: int = 0) -> LLMResult:
        self.prompts.append(prompt)
        return LLMResult(text="an answer", model="fake", tier=1, finish_reason="STOP")


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
        services, "search", lambda *a, **k: pytest.fail("search must not run")
    )

    result = services.ask(db, a, b, question="why?", client=FakeClient())

    assert len(result.chunks) == 6, "every stored row was read back"


def test_a_large_pair_is_searched_and_admits_how_much_it_read(db, monkeypatch):
    """The other branch, and the honesty that must come with it.

    A searched side holds only what retrieval returned, so the prompt has to
    say so - otherwise the model treats a handful of chunks as the whole file.
    """
    a = stored(db, "A", parts=60, words=300)
    b = stored(db, "B", parts=60, words=300)
    monkeypatch.setattr(services, "_embed_question", lambda *a, **k: V)
    client = FakeClient()

    services.ask(db, a, b, question="why?", client=client)

    assert "NOT searched" in client.prompts[0]
    assert "of 60 parts" in client.prompts[0]


def test_an_unknown_artifact_id_is_refused(db):
    """Not a 503 and not an empty answer.

    StorageUnavailable is 503 because the database being down is OUR failure.
    An id we never stored is a fact about the REQUEST, and reporting it as
    "nothing matched" would be a lie about whose fault it is.
    """
    b = stored(db, "B", parts=2, words=20)

    with pytest.raises(UnknownArtifactId, match="ghost"):
        services.ask(db, "ghost", b, question="why?", client=FakeClient())


def test_two_artifacts_from_the_same_slot_are_refused(db):
    """The side is baked into the id by _artifact_id, so two A ids is not a pair.

    It would build a prompt with no side B at all, and every B-walk in the
    instructions would have nothing to walk.
    """
    a = stored(db, "A", parts=2, words=20)

    with pytest.raises(ArtifactSidesClash):
        services.ask(db, a, a, question="why?", client=FakeClient())

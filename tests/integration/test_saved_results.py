"""D104: saved results in Postgres, and two real ask() calls on the same files."""

import pytest

from labpilot.agent import Bug
from labpilot.api import asking
from labpilot.store import (
    ArtifactRecord,
    ChunkRecord,
    read_saved,
    write_artifact,
    write_saved,
)
from tests.integration.test_ask import PLAN, FakeClient

pytestmark = pytest.mark.database

V = (1.0, 0.0, 0.0)


def stored(db, side, *, parts=3, words=20, name=None):
    artifact_id = f"{side}-saved"
    write_artifact(
        db,
        ArtifactRecord(
            id=artifact_id,
            name=name or f"{side}.py",
            side=side,
            embedding_model="codestral-embed",
            dim=3,
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


def test_a_saved_result_comes_back_and_a_second_save_replaces_it(db):
    b = stored(db, "B")

    write_saved(db, "bugs:x", "msgpack", b"first", artifacts=(b,))
    write_saved(db, "bugs:x", "msgpack", b"second", artifacts=(b,))

    assert read_saved(db, "bugs:x") == ("msgpack", b"second")
    assert read_saved(db, "nothing saved here") is None


def test_saved_results_go_with_their_artifacts(db):
    a = stored(db, "A")
    b = stored(db, "B")
    write_saved(db, "differences:x", "msgpack", b"pair", artifacts=(a, b))

    write_saved(db, "claims:x", "msgpack", b"one", artifacts=(a,))
    # Storing B again (same id, rows written again) drops what its old rows said.
    stored(db, "B")

    assert read_saved(db, "differences:x") is None
    assert read_saved(db, "claims:x") == ("msgpack", b"one")

    # And the same for A, the first artifact of a saved row.
    stored(db, "A")

    assert read_saved(db, "claims:x") is None


def test_a_saved_result_needs_one_or_two_artifacts(db):
    with pytest.raises(ValueError):
        write_saved(db, "k", "msgpack", b"x", artifacts=())


BUG = Bug("logic", "the step is never updated", "[B.py - part 0]", "word word")


def test_the_second_message_reads_the_bug_hunt_and_says_so(db, monkeypatch):
    a = stored(db, "A")
    b = stored(db, "B")
    hunts = []

    def fake_bug_finder(conn, **clients):
        def find(artifact, summary):
            hunts.append(artifact)
            return (BUG,)

        return find

    monkeypatch.setattr(asking, "make_bug_finder", fake_bug_finder)
    first_plan = {**PLAN, "steps": ["find_bugs"]}

    first = asking.ask(db, a, b, question="why?", client=FakeClient(first_plan))
    # A follow-up planned with no step at all: the saved hunt is added, read
    # from the database, and the hunt does not run again.
    second = asking.ask(db, a, b, question="explain the bug", client=FakeClient(PLAN))

    assert hunts == [b]
    assert first.reused == ()
    assert second.reused == ("bugs",)


class LongAnswerClient(FakeClient):
    """The report is long: its start is far more than 2,000 characters back."""

    ANSWER = "START OF THE REPORT: bug 1 is the clip norm. " + "x" * 9_000 + " END."

    def generate(self, prompt, *, max_tokens=0, tool=None, problem_with=None):
        result = super().generate(
            prompt, max_tokens=max_tokens, tool=tool, problem_with=problem_with
        )
        if result.text == "an answer":
            return type(result)(
                text=self.ANSWER, model="fake", tier=1, finish_reason="STOP"
            )
        return result


def test_a_follow_up_in_a_saved_chat_sees_the_whole_last_answer(db, chat_tables):
    # D104: "fix bug 1" needs the part of the report that names bug 1, which is
    # at its START. The old design kept only the last 2,000 characters.
    a = stored(db, "A")
    b = stored(db, "B")
    client = LongAnswerClient()

    for question in ("why?", "fix bug 1"):
        asking.ask(db, a, b, question=question, client=client, thread_id="d104")

    assert "START OF THE REPORT: bug 1 is the clip norm." in client.prompts[1]
    assert "START OF THE REPORT" in client.follow_up_prompts[0]

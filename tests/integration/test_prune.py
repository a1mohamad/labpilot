"""PRUNE against hand-made rows: no graph, no model, one rule per test.

The chat tests in test_ask.py run the whole pipeline and then COUNT rows. That
is the right place to see the end result, but a count is blunt. With
`durability="exit"` a message leaves no pending writes at all, so "writes == 0"
passes even if the part of the SQL that deletes them is gone. Here every row is
placed by hand, so each rule of the query has a test that can fail on it alone.

The ids are text and sort the way the real ones do (newest = biggest).
"""

import json
import uuid

import pytest

from labpilot.api.checkpoints import prune


@pytest.fixture
def chat() -> str:
    return f"chat-{uuid.uuid4().hex[:8]}"


def add_copy(db, chat: str, copy_id: str, versions: dict[str, str]) -> None:
    db.execute(
        "insert into checkpoints (thread_id, checkpoint_ns, checkpoint_id, checkpoint) "
        "values (%s, '', %s, %s::jsonb)",
        (chat, copy_id, json.dumps({"channel_versions": versions})),
    )


def add_write(db, chat: str, copy_id: str) -> None:
    db.execute(
        "insert into checkpoint_writes "
        "(thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, blob) "
        "values (%s, '', %s, 'task', 0, 'history', %s)",
        (chat, copy_id, b"x"),
    )


def add_blob(db, chat: str, channel: str, version: str) -> None:
    db.execute(
        "insert into checkpoint_blobs "
        "(thread_id, checkpoint_ns, channel, version, type, blob) "
        "values (%s, '', %s, %s, 'bytes', %s)",
        (chat, channel, version, b"x"),
    )


def copies(db, chat: str) -> set[str]:
    rows = db.execute(
        "select checkpoint_id from checkpoints where thread_id = %s", (chat,)
    ).fetchall()
    return {row[0] for row in rows}


def writes(db, chat: str) -> set[str]:
    rows = db.execute(
        "select checkpoint_id from checkpoint_writes where thread_id = %s", (chat,)
    ).fetchall()
    return {row[0] for row in rows}


def blobs(db, chat: str) -> set[tuple[str, str]]:
    rows = db.execute(
        "select channel, version from checkpoint_blobs where thread_id = %s", (chat,)
    ).fetchall()
    return {(row[0], row[1]) for row in rows}


@pytest.fixture
def three_messages(db, chat_tables, chat):
    """Three saved copies, the way three messages leave them.

    `sides` never changes, so every copy points at the SAME blob of it, version 1,
    which is also the OLDEST version in the table. `history` and `result` change
    every message, so each copy points at its own.
    """
    for number in ("1", "2", "3"):
        add_copy(
            db,
            chat,
            f"00{number}",
            {"history": number, "result": number, "sides": "1"},
        )
        add_write(db, chat, f"00{number}")
        add_blob(db, chat, "history", number)
        add_blob(db, chat, "result", number)
    add_blob(db, chat, "sides", "1")
    return chat


def test_only_the_newest_copy_of_the_chat_is_kept(db, three_messages):
    prune(db, three_messages)

    assert copies(db, three_messages) == {"003"}


def test_the_pending_writes_of_the_old_copies_are_deleted_and_the_newest_ones_kept(
    db, three_messages
):
    prune(db, three_messages)

    assert writes(db, three_messages) == {"003"}


def test_a_blob_the_newest_copy_points_to_is_kept_even_when_it_is_old(
    db, three_messages
):
    prune(db, three_messages)

    assert ("sides", "1") in blobs(db, three_messages)


def test_a_blob_only_an_old_copy_points_to_is_deleted(db, three_messages):
    prune(db, three_messages)

    assert blobs(db, three_messages) == {
        ("history", "3"),
        ("result", "3"),
        ("sides", "1"),
    }


@pytest.fixture
def another_chat(db, chat_tables) -> str:
    """A second chat whose ids are all NEWER than the first chat's."""
    other = f"other-{uuid.uuid4().hex[:8]}"
    add_copy(db, other, "900", {"history": "9"})
    add_copy(db, other, "950", {"history": "9"})
    add_write(db, other, "900")
    add_blob(db, other, "history", "8")
    add_blob(db, other, "history", "9")
    return other


def test_another_chat_is_never_touched_even_when_its_ids_are_newer(
    db, three_messages, another_chat
):
    prune(db, three_messages)

    assert copies(db, another_chat) == {"900", "950"}
    assert writes(db, another_chat) == {"900"}
    assert blobs(db, another_chat) == {("history", "8"), ("history", "9")}


def test_the_newest_copy_is_picked_among_this_chats_own_copies(
    db, three_messages, another_chat
):
    """Ids are only comparable inside one chat. If `newest` looked at every chat
    it would pick the other chat's 950, and every copy of this chat would count
    as old."""
    prune(db, three_messages)

    assert copies(db, three_messages) == {"003"}

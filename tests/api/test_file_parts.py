import logging

import psycopg
import pytest

from labpilot.api import file_parts
from labpilot.api.errors import UnknownArtifactId
from labpilot.api.file_parts import FileParts, read_parts
from labpilot.store import StoredChunk, UnknownArtifact


class Failed(Exception):
    pass


def stored(index, text, source="a.py"):
    return StoredChunk(
        chunk_index=index,
        text=text,
        header=f"[{source} · part {index}]",
        source=source,
        start_line=index,
        end_line=index,
    )


def parts_of(monkeypatch, rows, *, limit=None):
    monkeypatch.setattr(file_parts, "read_chunks", lambda conn, artifact_id: rows)
    return read_parts("conn", "B-1", limit=limit, error=Failed)


def test_the_parts_keep_their_order_and_their_numbers_mean_the_same_part(monkeypatch):
    parts = parts_of(monkeypatch, [stored(0, "x = 1"), stored(1, "y = 2")])

    assert parts.texts == ("[a.py · part 0]\nx = 1", "[a.py · part 1]\ny = 2")
    assert parts.sources == ("[a.py · part 0]", "[a.py · part 1]")
    assert [chunk.chunk_index for chunk in parts.chunks] == [0, 1]
    assert {chunk.side for chunk in parts.chunks} == {"B"}


def test_a_file_that_does_not_fit_the_limit_is_skipped_whole(monkeypatch, caplog):
    rows = [stored(0, "x" * 300, "big.py"), stored(1, "y = 2", "small.py")]

    with caplog.at_level(logging.WARNING):
        parts = parts_of(monkeypatch, rows, limit=50)

    assert parts.sources == ("[small.py · part 1]",)
    assert "1 of 2 parts, 1 of 2 files" in caplog.text


def test_no_part_to_read_is_the_step_error(monkeypatch):
    with pytest.raises(Failed):
        parts_of(monkeypatch, [])


def test_a_missing_artifact_is_a_404_and_a_dead_connection_the_step_error(
    monkeypatch,
):
    def missing(conn, artifact_id):
        raise UnknownArtifact(artifact_id)

    def dead(conn, artifact_id):
        raise psycopg.OperationalError("server closed the connection")

    monkeypatch.setattr(file_parts, "read_chunks", missing)
    with pytest.raises(UnknownArtifactId):
        read_parts("conn", "B-1", limit=None, error=Failed)

    monkeypatch.setattr(file_parts, "read_chunks", dead)
    with pytest.raises(Failed, match="could not read B-1"):
        read_parts("conn", "B-1", limit=None, error=Failed)


def test_a_finding_finds_its_part_by_the_source_the_prompt_gave(monkeypatch):
    parts = parts_of(monkeypatch, [stored(0, "x = 1"), stored(1, "y = 2")])

    assert parts.chunk_for("[a.py · part 1]").chunk_index == 1
    assert parts.chunk_for("[nowhere]") is None


def test_the_groups_are_parts_too_and_only_keeps_the_order(monkeypatch):
    parts = parts_of(monkeypatch, [stored(i, "word " * 100) for i in range(4)])

    groups = parts.groups(150)
    kept = parts.only(lambda chunk: chunk.chunk_index % 2 == 1)

    assert all(isinstance(group, FileParts) for group in groups)
    assert [c.chunk_index for g in groups for c in g.chunks] == [0, 1, 2, 3]
    assert len(groups) > 1
    assert [chunk.chunk_index for chunk in kept.chunks] == [1, 3]

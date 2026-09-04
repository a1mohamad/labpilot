from __future__ import annotations

import pytest

from labpilot.store import ArtifactRecord, ChunkRecord, write_artifact
from labpilot.store.defaults import INSERT_BATCH_SIZE

pytestmark = pytest.mark.database

DIM = 4


def artifact(**overrides) -> ArtifactRecord:
    fields = {
        "id": "w1",
        "name": "train.py",
        "side": "B",
        "embedding_model": "codestral-embed",
        "dim": DIM,
    }
    return ArtifactRecord(**{**fields, **overrides})


def chunk(index: int, *, dim: int = DIM) -> ChunkRecord:
    return ChunkRecord(
        chunk_index=index,
        text=f"line {index}",
        source="train.py",
        start_line=index * 10,
        end_line=index * 10 + 5,
        header=f"[train.py - part {index}]",
        vector=tuple(float(index + n) for n in range(dim)),
    )


def test_a_written_artifact_comes_back_with_its_fields_unchanged(db):
    assert write_artifact(db, artifact(), [chunk(0), chunk(1), chunk(2)]) == 3

    with db.cursor() as cur:
        cur.execute(
            "select chunk_index, text, header, source, start_line, end_line"
            " from chunks where artifact_id = 'w1' order by chunk_index"
        )
        assert cur.fetchall() == [
            (0, "line 0", "[train.py - part 0]", "train.py", 0, 5),
            (1, "line 1", "[train.py - part 1]", "train.py", 10, 15),
            (2, "line 2", "[train.py - part 2]", "train.py", 20, 25),
        ]


def test_writing_the_same_artifact_twice_replaces_it(db):
    write_artifact(db, artifact(id="twice"), [chunk(0), chunk(1), chunk(2)])
    write_artifact(db, artifact(id="twice"), [chunk(0)])

    with db.cursor() as cur:
        cur.execute("select count(*) from chunks where artifact_id = 'twice'")
        assert cur.fetchone()[0] == 1
        cur.execute("select count(*) from artifacts where id = 'twice'")
        assert cur.fetchone()[0] == 1


def test_a_failure_midway_leaves_nothing_behind(db):
    def dying():
        # more than one batch, so a real INSERT has already run when it fails
        for index in range(INSERT_BATCH_SIZE + 4):
            yield chunk(index)
        raise RuntimeError("the embedder died")

    with pytest.raises(RuntimeError):
        write_artifact(db, artifact(id="dead"), dying())

    with db.cursor() as cur:
        cur.execute("select count(*) from chunks where artifact_id = 'dead'")
        assert cur.fetchone()[0] == 0
        cur.execute("select count(*) from artifacts where id = 'dead'")
        assert cur.fetchone()[0] == 0


def test_a_vector_of_the_wrong_width_is_refused(db):
    with pytest.raises(ValueError, match="dimensions"):
        write_artifact(db, artifact(id="wide"), [chunk(0), chunk(1, dim=DIM + 1)])

    with db.cursor() as cur:
        cur.execute("select count(*) from artifacts where id = 'wide'")
        assert cur.fetchone()[0] == 0


def test_an_artifact_with_no_chunks_is_refused(db):
    with pytest.raises(ValueError, match="no chunks"):
        write_artifact(db, artifact(id="empty"), [])

    with db.cursor() as cur:
        cur.execute("select count(*) from artifacts where id = 'empty'")
        assert cur.fetchone()[0] == 0


def test_the_vectors_survive_only_to_float4_precision(db):
    sent = (1 / 3, 0.1234567890123456, -0.5, 0.25)
    record = ChunkRecord(
        chunk_index=0, text="t", source="s", start_line=1, end_line=1, vector=sent
    )
    write_artifact(db, artifact(id="prec"), [record])

    with db.cursor() as cur:
        cur.execute("select v from chunks where artifact_id = 'prec'")
        back = [float(x) for x in cur.fetchone()[0].strip("[]").split(",")]

    assert back == pytest.approx(sent, rel=1e-6)
    assert back != list(sent)  # float4, measured: NOT exact. Do not "fix" this.

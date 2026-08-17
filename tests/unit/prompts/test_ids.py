from labpilot.ingest import Chunk
from labpilot.prompts._ids import assign_ids


def _chunk(side: str, index: int, source: str = "f.py") -> Chunk:
    return Chunk(
        text="x",
        source=source,
        start_line=1,
        end_line=1,
        side=side,
        artifact_id="a",
        chunk_index=index,
    )


def test_each_side_is_numbered_from_zero_independently():
    chunks = (_chunk("A", 0), _chunk("B", 0), _chunk("A", 1), _chunk("B", 1))

    assert list(assign_ids(chunks)) == ["A-0", "B-0", "A-1", "B-1"]


def test_numbering_continues_across_files_on_the_same_side():
    chunks = (
        _chunk("B", 0, "train.py"),
        _chunk("B", 1, "train.py"),
        _chunk("B", 0, "model.py"),
    )

    ids = assign_ids(chunks)

    assert list(ids) == ["B-0", "B-1", "B-2"]
    assert ids["B-2"].source == "model.py"


def test_no_chunks_gives_no_ids():
    assert assign_ids(()) == {}


def test_side_b_ids_do_not_move_when_side_a_is_absent():
    """The two-pass design sends B alone, then A and B together.

    A citation the scan pass writes as B-1 must point at the same chunk when the
    compare pass sees it. A shared counter across sides would break that
    silently, and every carried-over finding would cite the wrong part.
    """
    side_a = (_chunk("A", 0), _chunk("A", 1))
    side_b = (_chunk("B", 0), _chunk("B", 1), _chunk("B", 2))

    alone = assign_ids(side_b)
    together = assign_ids(side_a + side_b)

    for name, chunk in alone.items():
        assert together[name] is chunk, name

import pytest

from labpilot.ingest import Chunk, chunk_bytes
from labpilot.prompts import build_context
from labpilot.prompts.context import DROPPED, _labels


def _chunk(side: str, index: int, text: str = "body") -> Chunk:
    return Chunk(
        text=text,
        source="f.py",
        start_line=1,
        end_line=1,
        side=side,
        artifact_id="a",
        chunk_index=index,
        header="[f.py · lines 1-1]",
    )


def test_every_chunk_appears_in_the_outline():
    chunks = (_chunk("A", 0), _chunk("A", 1))

    context = build_context(chunks, (chunks[0],))

    assert "A-0" in context
    assert "A-1" in context


def test_only_selected_chunks_show_their_text():
    kept = _chunk("A", 0, text="this was kept")
    dropped = _chunk("A", 1, text="this was dropped")

    context = build_context((kept, dropped), (kept,))

    assert "this was kept" in context
    assert "this was dropped" not in context


def test_a_dropped_chunk_is_marked_in_the_outline():
    chunks = (_chunk("A", 0), _chunk("A", 1))

    context = build_context(chunks, (chunks[0],))

    assert "A-1  text NOT included" in context


def test_a_side_with_nothing_selected_says_so():
    chunks = (_chunk("A", 0), _chunk("B", 0))

    context = build_context(chunks, (chunks[0],))

    assert "(no part of this side was included)" in context


def test_a_side_with_no_chunks_is_left_out():
    chunks = (_chunk("A", 0),)

    context = build_context(chunks, chunks)

    assert "SIDE B" not in context


def test_a_selected_chunk_that_is_not_in_chunks_is_our_bug():
    chunks = (_chunk("A", 0),)
    stranger = _chunk("A", 9)

    with pytest.raises(ValueError):
        build_context(chunks, (stranger,))


def _in_file(side: str, index: int, source: str, label: str = "") -> Chunk:
    """A chunk that knows which file it came from, headed the way ingest heads it."""
    middle = f" · {label}" if label else ""
    return Chunk(
        text="body",
        source=source,
        start_line=index,
        end_line=index + 1,
        side=side,
        artifact_id="a",
        chunk_index=index,
        header=f"[{source}{middle} · lines {index}-{index + 1}]",
    )


def test_a_small_side_still_lists_every_part_one_by_one():
    """Level 1 of the ladder, and the richest honesty we can give.

    A handful of chunks costs a handful of rows, so nothing degrades and the
    model learns the label and line range of every part it did NOT receive.
    """
    chunks = tuple(_in_file("A", i, "f.py", f"def step{i}") for i in range(4))

    context = build_context(chunks, (chunks[0],))

    assert "ALL PARTS, IN ORDER" in context
    assert context.count(DROPPED) == 3


def test_a_side_too_wide_to_list_part_by_part_falls_back_to_files():
    """Level 2, and the reason the ladder exists at all.

    300 chunks is 7,800 tokens of per-chunk rows against a 26,000 prompt - a
    table of contents crowding out the evidence it describes. Two files is two
    rows instead, and the labels still name what each file defines.

    The COUNT is a literal, never derived from OUTLINE_BUDGET: a threshold test
    whose input is computed from the threshold can never fail.
    """
    chunks = tuple(
        _in_file("B", i, "big.py" if i < 150 else "other.py", f"def step{i}")
        for i in range(300)
    )

    context = build_context(chunks, (chunks[0],))

    assert "ALL PARTS, IN ORDER" not in context
    assert "FILES" in context
    assert "big.py  B-0..B-149  150 parts" in context
    assert "other.py  B-150..B-299  150 parts" in context
    assert "defines:" in context


def test_a_side_with_too_many_labels_drops_them_and_keeps_the_files():
    """Level 3. The labels are the first thing sacrificed, not the file list.

    Measured on labpilot/: `defines:` compresses 410 chunks to 270 labels, a
    ratio of only 1.5, so it is 2.5x cheaper than per-chunk and nowhere near
    free. When even that does not fit, the file rows survive alone - because a
    file list is what keeps every citation locatable.
    """
    chunks = tuple(
        _in_file("B", i, f"f{i}.py", f"def {'x' * 300}{i}") for i in range(100)
    )

    context = build_context(chunks, (chunks[0],))

    assert "FILES" in context
    assert "defines:" not in context
    assert "f99.py" in context


def test_a_side_where_everything_was_sent_marks_nothing_as_missing():
    """The stuff path, and it is not a degradation - the job simply changes.

    Nothing was dropped, so there is no accounting to do. A per-chunk outline
    here would be pure duplication: _text() already prints `{id}  {header}`
    immediately above every chunk, two lines further down.

    The file list stays because it is navigation, not accounting.
    """
    chunks = tuple(_in_file("A", i, "f.py") for i in range(3))

    context = build_context(chunks, chunks)

    assert DROPPED not in context
    assert "FILES" in context
    assert "f.py  A-0..A-2  3 parts" in context


def test_a_file_split_across_the_corpus_never_claims_one_span():
    """THE CONTIGUITY INVARIANT, and a span is a citation pointing at a file.

    `B-40..B-70` is only true if that file's chunks sit together. They do
    today, because chunk_source walks files in sorted order - but NOTHING
    enforces it, and a span that silently swallows another file's chunks sends
    the model to the wrong file with full confidence.

    So _by_file groups CONSECUTIVE runs rather than sorting and grouping. Here
    f1 is interrupted by f2, and the honest answer is three rows with three
    correct spans - never one row claiming B-0..B-2, which would cover a chunk
    belonging to f2.

    Sorting and grouping passes every other test in this file. Only this one
    notices.
    """

    # Wide enough to reach the per-file level, where spans are printed at all.
    def source_of(i: int) -> str:
        return "f2.py" if 100 <= i < 200 else "f1.py"

    chunks = tuple(_in_file("B", i, source_of(i)) for i in range(300))

    context = build_context(chunks, (chunks[0],))

    assert "B-0..B-299" not in context, "a span must never cover another file"
    assert context.count("f1.py  B-") == 2, "f1 is split, so it gets two rows"
    assert "f1.py  B-0..B-99" in context
    assert "f1.py  B-200..B-299" in context


def test_defines_recovers_the_label_ingest_actually_wrote():
    """The one place prompts/ READS ingest's header format instead of printing it.

    Not a new coupling - this module already renders chunk.header verbatim -
    but it is a real one, so it is pinned rather than trusted. If _header ever
    stops writing `[source - label - lines]`, `defines:` would quietly list
    nothing and the outline would lose its labels with no error anywhere.

    Built by the REAL chunker, so the format is ingest's and not the fixture's.
    """
    body = "\n".join(f"    x{i} = {i}" for i in range(80))
    source = f"def alpha():\n{body}\n\n\ndef beta():\n{body}\n".encode()
    chunks = chunk_bytes(source, source="real.py", side="B", artifact_id="r")
    assert len(chunks) >= 2, "the fixture must produce labelled parts"

    labels = _labels([(f"B-{i}", c) for i, c in enumerate(chunks)])

    assert "def alpha" in labels
    assert "def beta" in labels


def test_a_partial_side_never_claims_everything_was_included():
    """THE LIE THE SEARCH PATH WOULD TELL, and the reason `totals` exists.

    On the search path the chunks handed to build_context are all we RETRIEVED,
    not all there is - and every one of them is "kept". Without the total, the
    outline renders "every part below is included" over 2 rows of an 8,333-part
    corpus, and the model reads it as the whole file.

    That is exactly the failure the outline exists to prevent: a gap in OUR
    retrieval reported as a defect in the USER's code.
    """
    retrieved = tuple(_in_file("B", i, "train.py") for i in range(2))

    honest = build_context(retrieved, retrieved, totals={"B": 8_333})
    lying = build_context(retrieved, retrieved)

    assert "every part below is included" in lying, "the case being guarded"
    assert "every part below is included" not in honest


def test_a_partial_side_says_how_much_of_it_was_read():
    """A count the model can reason with, not just the absence of a claim."""
    retrieved = tuple(_in_file("B", i, "train.py") for i in range(2))

    context = build_context(retrieved, retrieved, totals={"B": 8_333})

    assert "2 of 8333 parts" in context
    assert "NOT searched" in context


def test_a_side_that_was_read_whole_is_not_marked_partial():
    """The stuff path must not apologise for something it did not do."""
    chunks = tuple(_in_file("A", i, "f.py") for i in range(3))

    context = build_context(chunks, chunks, totals={"A": 3})

    assert "NOT searched" not in context
    assert "every part below is included" in context

from __future__ import annotations

from pathlib import Path

import pytest

from labpilot.ingest import chunk_bytes, chunk_file
from labpilot.ingest.chunker import LOADERS
from labpilot.ingest.defaults import MAX_CHUNK_TOKENS, MIN_CHUNK_TOKENS
from labpilot.ingest.errors import LoaderError, LooksGenerated, NotUtf8Text
from labpilot.tokens import estimate_tokens

SAMPLES = Path("data/samples/quora_siamese")

CODE = """import os


class Empty:
    pass


class Holder:
    def one(self):
        return 1

    def two(self):
        return 2
"""


@pytest.fixture(scope="module")
def code_chunks():
    return chunk_file(SAMPLES / "B_train.py", side="B", artifact_id="quora")


@pytest.fixture(scope="module")
def paper_chunks():
    return chunk_file(SAMPLES / "A_paper.md", side="A", artifact_id="quora")


def test_no_chunk_text_exceeds_the_hard_cap(code_chunks, paper_chunks):
    for chunk in (*code_chunks, *paper_chunks):
        assert estimate_tokens(chunk.text) <= MAX_CHUNK_TOKENS


@pytest.mark.xfail(
    strict=True,
    reason="the cap is enforced on chunk.text, but embed_text is what is sent. "
    "Slice 3 must move the check onto the string we actually send; when it "
    "does, this XPASSes and the marker must be deleted.",
)
def test_no_chunk_exceeds_the_hard_cap_once_its_header_is_added(
    code_chunks, paper_chunks
):
    for chunk in (*code_chunks, *paper_chunks):
        assert estimate_tokens(chunk.embed_text) <= MAX_CHUNK_TOKENS


def test_no_chunk_falls_under_the_minimum(code_chunks, paper_chunks):
    for chunk in (*code_chunks, *paper_chunks):
        assert estimate_tokens(chunk.text) >= MIN_CHUNK_TOKENS


def test_chunk_index_counts_from_zero_without_gaps(code_chunks):
    assert [chunk.chunk_index for chunk in code_chunks] == list(range(len(code_chunks)))


def test_side_and_artifact_travel_onto_every_chunk(code_chunks, paper_chunks):
    assert {chunk.side for chunk in code_chunks} == {"B"}
    assert {chunk.side for chunk in paper_chunks} == {"A"}
    assert {chunk.artifact_id for chunk in code_chunks} == {"quora"}


def test_the_embedder_fields_are_left_empty(code_chunks):
    assert all(chunk.embedding_model is None for chunk in code_chunks)
    assert all(chunk.dim is None for chunk in code_chunks)


def test_the_header_names_the_source_and_the_lines(code_chunks):
    chunk = code_chunks[0]
    assert chunk.header.startswith("[B_train.py · ")
    assert f"lines {chunk.start_line}-{chunk.end_line}]" in chunk.header


@pytest.mark.parametrize("name", ["B_train.py", "A_paper.md"])
def test_text_is_a_verbatim_slice_of_the_lines_it_cites(name):
    path = SAMPLES / name
    source = path.read_text(encoding="utf-8").splitlines()
    side = "B" if name.endswith(".py") else "A"
    for chunk in chunk_file(path, side=side, artifact_id="quora"):
        cited = "\n".join(source[chunk.start_line - 1 : chunk.end_line])
        assert chunk.text in cited


def test_a_merged_chunk_keeps_the_blank_lines_between_its_parts():
    chunks = chunk_bytes(
        CODE.encode("utf-8"), source="tiny.py", side="B", artifact_id="t"
    )
    lines = CODE.splitlines()
    merged = next(c for c in chunks if "class Holder" in c.text)
    assert merged.text == "\n".join(lines[merged.start_line - 1 : merged.end_line])


def test_an_oversized_definition_is_numbered_into_parts(code_chunks):
    headers = [chunk.header for chunk in code_chunks]
    assert any("def fit · part 1/" in header for header in headers)


def test_a_bare_class_header_merges_with_what_follows_it():
    chunks = chunk_bytes(
        CODE.encode("utf-8"), source="tiny.py", side="B", artifact_id="t"
    )
    holder = next(c for c in chunks if "class Holder" in c.text)
    assert "def one" in holder.text


def test_an_unknown_extension_falls_back_to_the_recursive_splitter():
    prose = (("word " * 20).strip() + "\n") * 100

    chunks = chunk_bytes(
        prose.encode("utf-8"), source="notes.txt", side="A", artifact_id="t"
    )

    assert chunks
    assert all("·" not in chunk.header.split(" · lines")[0] for chunk in chunks)


def test_an_empty_file_yields_no_chunks():
    assert chunk_bytes(b"", source="empty.py", side="B", artifact_id="t") == ()


def test_a_byte_order_mark_changes_nothing_about_the_chunks():
    plain = chunk_bytes(
        CODE.encode("utf-8"), source="tiny.py", side="B", artifact_id="t"
    )
    marked = chunk_bytes(
        "\ufeff".encode("utf-8") + CODE.encode("utf-8"),
        source="tiny.py",
        side="B",
        artifact_id="t",
    )

    assert [chunk.header for chunk in marked] == [chunk.header for chunk in plain]
    assert [chunk.text for chunk in marked] == [chunk.text for chunk in plain]


def test_bytes_that_are_not_utf8_are_refused_by_the_one_decoder():
    with pytest.raises(NotUtf8Text):
        chunk_bytes(b"# caf\xe9\nx = 1\n", source="a.py", side="B", artifact_id="t")


@pytest.mark.parametrize("suffix", sorted(LOADERS))
def test_a_loader_refuses_what_it_cannot_read_with_our_own_error(suffix):
    with pytest.raises(LoaderError):
        LOADERS[suffix](b"\x89PNG\r\n\x1a\n\x00\x00 not a document at all")


def test_a_real_paper_becomes_chunks_that_name_their_page():
    raw = (Path("data/samples/pdf") / "two_column.pdf").read_bytes()

    chunks = chunk_bytes(raw, source="paper.pdf", side="A", artifact_id="paper")

    assert chunks
    assert any("page 1" in chunk.header for chunk in chunks)
    assert "ﬁ" not in "".join(chunk.text for chunk in chunks)


def test_a_minified_file_is_refused_not_stored_as_chunks_that_all_cite_line_one():
    """Measured before the guard existed: 65 chunks, every one reporting
    lines (1, 1). Wrong every time, and it looks right."""
    minified = ("function a(b,c){return b+c};" * 3000).encode("utf-8")
    assert b"\n" not in minified, "the point is that it has no lines"

    with pytest.raises(LooksGenerated):
        chunk_bytes(minified, source="bundle.min.js", side="B", artifact_id="x")


def test_real_source_code_is_never_mistaken_for_a_generated_file():
    # 1,386 real files peak at a mean line of 69; the limit is 500.
    code = ("def add(x, y):\n    return x + y\n\n" * 300).encode("utf-8")

    assert chunk_bytes(code, source="a.py", side="B", artifact_id="x")


def test_our_own_loaded_documents_stay_under_the_generated_file_limit():
    """A Word paragraph is a single long line -- the loaded fixture reaches a
    mean of 69.3. If the limit ever drops near that, real papers get refused."""
    for name in ("pdf/two_column.pdf", "docx/ddos_ensemble.docx"):
        raw = (Path("data/samples") / name).read_bytes()
        assert chunk_bytes(raw, source=Path(name).name, side="A", artifact_id="x")

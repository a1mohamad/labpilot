from __future__ import annotations

from pathlib import Path

import pytest

from labpilot.ingest import chunk_file, chunk_text
from labpilot.ingest.defaults import MAX_CHUNK_TOKENS, MIN_CHUNK_TOKENS
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


def test_no_chunk_exceeds_the_hard_cap(code_chunks, paper_chunks):
    for chunk in (*code_chunks, *paper_chunks):
        assert estimate_tokens(chunk.text) <= MAX_CHUNK_TOKENS


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


def test_text_stays_inside_the_lines_it_cites(code_chunks):
    source = (SAMPLES / "B_train.py").read_text(encoding="utf-8").splitlines()
    for chunk in code_chunks:
        cited = "\n".join(source[chunk.start_line - 1 : chunk.end_line])
        assert chunk.text.splitlines()[0] in cited


def test_an_oversized_definition_is_numbered_into_parts(code_chunks):
    headers = [chunk.header for chunk in code_chunks]
    assert any("def fit · part 1/" in header for header in headers)


def test_a_bare_class_header_merges_with_what_follows_it():
    chunks = chunk_text(CODE, source="tiny.py", side="B", artifact_id="t")
    holder = next(c for c in chunks if "class Holder" in c.text)
    assert "def one" in holder.text


def test_an_unknown_extension_falls_back_to_the_recursive_splitter():
    chunks = chunk_text("word " * 400, source="notes.txt", side="A", artifact_id="t")
    assert chunks
    assert all("·" not in chunk.header.split(" · lines")[0] for chunk in chunks)


def test_an_empty_file_yields_no_chunks():
    assert chunk_text("", source="empty.py", side="B", artifact_id="t") == ()

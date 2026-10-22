"""fits_whole: what the outline costs, and the promise that "fits" keeps every part.

Two things changed on 2026-10-22 and each needs its own guard.

THE OUTLINE IS PRICED BY ITS SHAPE. When every part is sent the outline is a
plain list: a heading and one row per FILE. It used to be charged as a flat
4,000 tokens, which over-charged almost everything that fits and knew nothing
about a repository with very many tiny files. `measure()` now counts the files
and `fits_whole` charges FILE_ROW_TOKENS for each, so the charge has to stay
above what a real row costs.

"FITS" MUST MEAN EVERY PART IS SENT. A probe found a pair that `fits_whole`
accepted and whose stuffed prompt then lost 2 of 280 parts without a word,
because the budgeted selection charged the long outline of a prompt that sends
nothing. With the exact charge there would be many more such pairs, so the
stuffed path now sends everything whenever the finished prompt fits.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labpilot.api import reading
from labpilot.api.prompting import build_answer_prompt
from labpilot.api.source_chunks import chunk_source
from labpilot.ingest import Chunk, chunk_file
from labpilot.prompts import (
    FILE_ROW_TOKENS,
    PROMPT_BUDGET,
    PROMPT_EXTRAS_TOKENS,
    Instructions,
    build_context,
    build_prompt,
)
from labpilot.sources import open_folder
from labpilot.store import ArtifactRecord, StoredArtifact
from labpilot.tokens import estimate_tokens

QUESTION = "Compare these and explain why the results diverge."
SAMPLES = Path("data/samples/quora_siamese")


def stored(side, *, files, characters, chunks=0):
    return StoredArtifact(
        artifact=ArtifactRecord(
            id=f"{side}-1", name="m.py", side=side, embedding_model="m", dim=3
        ),
        chunks=chunks,
        files=files,
        characters=characters,
    )


# ---- the charge, with the real constants swapped for round ones ---------------


@pytest.fixture
def round_numbers(monkeypatch):
    """A budget of 10,000, a row of 10, no extras and a one-token instruction.

    The question is "q", so the fixed text is "hq": 2 characters, 1 token.
    """
    monkeypatch.setattr(reading, "PROMPT_BUDGET", 10_000)
    monkeypatch.setattr(reading, "PROMPT_EXTRAS_TOKENS", 0)
    monkeypatch.setattr(reading, "FILE_ROW_TOKENS", 10)
    monkeypatch.setattr(
        reading, "instructions_for", lambda files: Instructions("tiny", "h", "")
    )


def test_no_artifact_means_no_outline(round_numbers, monkeypatch):
    monkeypatch.setattr(reading, "PROMPT_BUDGET", 1)

    assert reading.fits_whole({}, question="q") is True


@pytest.mark.parametrize(
    ("files", "fits"),
    [(1, True), (8, True), (9, False), (10, False)],
    ids=["one file", "the last that fits", "the first that does not", "a repository"],
)
def test_the_outline_costs_a_row_for_every_file_and_a_heading(
    round_numbers, files, fits
):
    # 9,900 tokens of evidence + 1 fixed + (files + 1) rows of 10 against 10,000:
    # 8 files is 9,991 and 9 files is 10,001.
    sides = {"B": stored("B", files=files, characters=9_900 * 3)}

    assert reading.fits_whole(sides, question="q") is fits


def test_each_artifact_pays_for_its_own_heading(round_numbers):
    # Two sides of 4 files: (4 + 1) rows each is 100, and 9,900 + 100 + 1 is
    # 10,001. Without a heading for each side it would be 9,981 and fit.
    sides = {
        "A": stored("A", files=4, characters=4_950 * 3),
        "B": stored("B", files=4, characters=4_950 * 3),
    }

    assert reading.fits_whole(sides, question="q") is False


def test_the_extras_are_reserved(round_numbers, monkeypatch):
    monkeypatch.setattr(reading, "PROMPT_EXTRAS_TOKENS", 100)

    # 9,870 + 20 outline + 1 fixed + 100 extras = 9,991; 9,880 makes 10,001.
    assert reading.fits_whole(
        {"B": stored("B", files=1, characters=9_870 * 3)}, question="q"
    )
    assert not reading.fits_whole(
        {"B": stored("B", files=1, characters=9_880 * 3)}, question="q"
    )


# ---- the constants against the real thing ---------------------------------------


def file_rows(context: str) -> list[str]:
    """The rows of the plain file list, as the prompt really prints them."""
    rows: list[str] = []
    for block in context.split("FILES - every part below is included\n")[1:]:
        rows += block.split("\n\n", 1)[0].splitlines()

    return rows


def test_a_file_row_never_costs_more_than_the_charge_for_it():
    pair = chunk_file(SAMPLES / "A_paper.md", side="A", artifact_id="A-p") + chunk_file(
        SAMPLES / "B_train.py", side="B", artifact_id="B-p"
    )
    with open_folder(Path("labpilot")) as source:
        repository = tuple(chunk_source(source, side="B"))

    for chunks in (pair, repository):
        rows = file_rows(build_context(chunks, chunks))
        assert len(rows) >= 2, "the outline was not found, so this checks nothing"
        costliest = max(estimate_tokens(row + "\n") for row in rows)
        assert costliest <= FILE_ROW_TOKENS, rows


def test_the_extras_cover_the_largest_summaries_and_last_answer():
    chunks = chunk_file(SAMPLES / "A_paper.md", side="A", artifact_id="A-p")
    instructions = Instructions("tiny", "h", "")
    long_summary = " ".join(["overview"] * 150)

    bare = build_prompt(chunks, chunks, question="q", instructions=instructions)
    full = build_prompt(
        chunks,
        chunks,
        question="q",
        instructions=instructions,
        summaries={"A": long_summary, "B": long_summary},
        last_answer="x" * 5_000,
    )

    assert estimate_tokens(full) - estimate_tokens(bare) <= PROMPT_EXTRAS_TOKENS


# ---- "fits" keeps every part ---------------------------------------------------


def make(side, count, chars):
    return tuple(
        Chunk(
            text="word " * (chars // 5),
            source=f"{side.lower()}{index // 4}.py",
            start_line=index,
            end_line=index,
            side=side,
            artifact_id=f"{side}-1",
            chunk_index=index,
            header=f"[{side.lower()}{index // 4}.py · lines {index}-{index}]",
        )
        for index in range(count)
    )


def stored_from(side, chunks):
    return stored(
        side,
        files=len({chunk.source for chunk in chunks}),
        characters=sum(len(chunk.embed_text) for chunk in chunks),
        chunks=len(chunks),
    )


def test_the_pair_the_probe_found_keeps_every_part():
    # 140 parts a side at 230 characters: fits_whole said yes, and the old
    # budgeted selection then kept 278 of 280.
    a, b = make("A", 140, 230), make("B", 140, 230)
    sides = {"A": stored_from("A", a), "B": stored_from("B", b)}

    assert reading.fits_whole(sides, question=QUESTION)
    _, selected = build_answer_prompt(a + b, question=QUESTION, files=2, totals=None)

    assert len(selected) == len(a + b)


def test_a_verdict_of_fits_keeps_every_part_with_the_largest_extras():
    """Every size, one side or two, with summaries and a last answer at their
    largest. If `fits_whole` says yes the prompt must hold every part and stay
    inside the budget, or the extras and the row charge are too small."""
    long_summary = " ".join(["overview"] * 150)
    summaries = {"A": long_summary, "B": long_summary}
    checked = 0

    for per_side in (20, 60, 100, 120, 140, 160):
        for chars in range(100, 700, 25):
            a, b = make("A", per_side, chars), make("B", per_side, chars)
            cases = [
                ({"A": stored_from("A", a), "B": stored_from("B", b)}, a + b, 2),
                ({"B": stored_from("B", b)}, b, 1),
            ]
            for sides, chunks, files in cases:
                if not reading.fits_whole(sides, question=QUESTION):
                    continue
                prompt, selected = build_answer_prompt(
                    chunks,
                    question=QUESTION,
                    files=files,
                    totals=None,
                    summaries=summaries,
                    last_answer="x" * 5_000,
                )
                assert len(selected) == len(chunks), (per_side, chars, files)
                assert estimate_tokens(prompt) <= PROMPT_BUDGET, (per_side, chars)
                checked += 1

    assert checked >= 40, "the sweep reached too few cases to prove anything"

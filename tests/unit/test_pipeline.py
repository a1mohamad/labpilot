from __future__ import annotations

from pathlib import Path

import pytest

from labpilot.ingest import chunk_file
from labpilot.prompts import (
    FULL,
    PROMPT_BUDGET,
    build_context,
    build_prompt,
    reserve,
    resolve,
)
from labpilot.retrieval import select
from labpilot.tokens import estimate_tokens

SAMPLES = Path("data/samples/quora_siamese")
QUESTION = "Compare these and explain why the results diverge."


@pytest.fixture(scope="module")
def chunks():
    return chunk_file(
        SAMPLES / "A_paper.md", side="A", artifact_id="quora"
    ) + chunk_file(SAMPLES / "B_train.py", side="B", artifact_id="quora")


@pytest.fixture(scope="module")
def picked(chunks):
    room = PROMPT_BUDGET - reserve(chunks, question=QUESTION, instructions=FULL)
    return select(chunks, budget=room)


@pytest.fixture(scope="module")
def prompt(chunks, picked):
    return build_prompt(chunks, picked, question=QUESTION, instructions=FULL)


def test_the_whole_prompt_fits_the_budget(prompt):
    assert estimate_tokens(prompt) <= PROMPT_BUDGET


def test_the_evidence_budget_is_not_eaten_by_the_instructions(picked):
    evidence = sum(estimate_tokens(chunk.embed_text) for chunk in picked)

    assert evidence >= 14_000


def test_the_pipeline_keeps_both_sides(picked):
    assert {chunk.side for chunk in picked} == {"A", "B"}


def test_every_part_is_listed_even_when_its_text_was_dropped(chunks, picked):
    context = build_context(chunks, picked)

    assert len(picked) < len(chunks)
    assert context.count("text NOT included") == len(chunks) - len(picked)


def test_every_selected_chunk_can_still_be_checked_against_its_file(picked):
    sources = {
        name: (SAMPLES / name).read_text(encoding="utf-8").splitlines()
        for name in ("A_paper.md", "B_train.py")
    }
    for chunk in picked:
        lines = sources[chunk.source]
        cited = "\n".join(lines[chunk.start_line - 1 : chunk.end_line])
        assert chunk.text in cited


def test_an_id_shown_in_the_prompt_resolves_back_to_the_right_line(chunks, prompt):
    first = next(chunk for chunk in chunks if chunk.side == "B")
    lines = first.text.splitlines()
    offset = next(index for index, line in enumerate(lines) if line.strip())

    assert "B-0  " in prompt

    found = resolve("B-0", lines[offset], chunks)

    assert found.source == "B_train.py"
    assert found.line == first.start_line + offset


def test_the_pipeline_gives_the_same_prompt_every_time(chunks, picked):
    first = build_prompt(chunks, picked, question=QUESTION, instructions=FULL)
    second = build_prompt(chunks, picked, question=QUESTION, instructions=FULL)

    assert first == second


def test_every_format_we_can_read_is_also_a_format_we_can_fetch():
    # The slice 3 rule, enforced instead of written down: a suffix added to
    # LOADERS or SPLITTERS but not to READABLE_SUFFIXES is a handler that
    # sources/ silently skips, and a suffix added the other way round is a
    # file walked in and then cut blindly.
    from labpilot.ingest.chunker import LOADERS, SPLITTERS
    from labpilot.sources.defaults import READABLE_SUFFIXES

    assert set(LOADERS) <= READABLE_SUFFIXES
    assert set(SPLITTERS) <= READABLE_SUFFIXES


def test_a_notebook_is_loaded_before_it_is_split_whichever_door_it_arrives_by():
    import json

    from labpilot.ingest import chunk_text

    raw = json.dumps(
        {
            "cells": [
                {
                    "cell_type": "code",
                    "source": ["lr = 3e-4\n"],
                    "outputs": [],
                    "execution_count": 1,
                }
            ],
            "nbformat": 4,
        }
    )

    chunks = chunk_text(raw, source="run.ipynb", side="B", artifact_id="nb")

    assert len(chunks) == 1
    assert "lr = 3e-4" in chunks[0].text
    assert '\n",' not in chunks[0].text
    assert "cell 1 code" in chunks[0].header

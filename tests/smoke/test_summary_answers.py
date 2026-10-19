"""THE REAL SUMMARIZER, ON A STORED FILE, WITH A REAL MODEL.

The summary is sections 1 and 2 of the report and the whole answer when the gate
halts (slice 8), but the weekly run only watched the planner. A summary tier that
died in the night, or a prompt that stopped producing prose, would first show up
as a bad report.

WHAT THIS SPENDS, per run: ONE ingest of embedder quota (a small file) and ONE
generation call on whatever tier leads the chain. It needs a live Postgres, so
it carries both gates.

WHAT IT CHECKS: an answer comes back, and it is plain prose of a sensible
length. It does NOT check that the summary is a good one.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from dotenv import load_dotenv

from labpilot.api import ingestion, summaries
from labpilot.llm import LLMClient

load_dotenv()

SAMPLES = Path("data/samples/quora_siamese")


@pytest.mark.smoke
def test_the_summarizer_gives_plain_prose_for_a_stored_file(db):
    stored = ingestion.ingest_artifact(
        db, (SAMPLES / "B_train.py").read_bytes(), name="B_train.py", side="B"
    )

    text = summaries.make_summarizer(db, LLMClient())(stored.artifact.id)

    print(text)

    assert text.strip(), "an empty summary is a failed tier, not an answer"
    # The prompt asks for at most 150 words. A model may overshoot a little, but
    # three times the limit means the instruction stopped working.
    assert len(text.split()) <= 450
    assert not text.lstrip().startswith("#"), "the prompt asks for no headings"

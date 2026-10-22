"""The summaries from stored rows to a summary, with only the provider's wire mocked.

tests/api/test_summaries.py patches `read_chunks`, and tests/unit/agent drives the
graph with fake summary functions. Two joins were never run:

- the real rows, in the real order, reaching the provider's request, and the
  prompt saying honestly how many of them were sent;
- the two summaries running AT THE SAME TIME over ONE database connection,
  which is how the graph runs them. The lesson 3 notes say this "was NOT
  tested", and a shared connection used from two threads is exactly the kind
  of thing that works until it does not.

`database` marked and free: `responses` answers in place of the provider.
"""

from __future__ import annotations

import json
import re
import threading

import pytest
import responses

from labpilot.agent import Plan, build_graph
from labpilot.api import summaries
from labpilot.api.errors import UnknownArtifactId
from labpilot.llm import GeminiProvider, LLMClient, LLMResult
from labpilot.store import ArtifactRecord, ChunkRecord, write_artifact

pytestmark = pytest.mark.database

BASE = "https://provider.test/v1beta/models"
V = (1.0, 0.0, 0.0)


def provider() -> GeminiProvider:
    return GeminiProvider(
        name="Summary tier",
        tier=1,
        url=BASE,
        model="one",
        api_key_env="TEST_API_KEY",
        context_window=1_000_000,
        max_output_tokens=64_000,
    )


def answered(text: str = "A short summary.") -> dict:
    return {
        "modelVersion": "one-001",
        "candidates": [
            {"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}
        ],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
    }


def store(db, side: str, *, parts: int, words: int = 5, reverse: bool = False) -> str:
    """`parts` chunks whose text starts with a marker that names side and index."""
    rows = [
        ChunkRecord(
            chunk_index=i,
            text=f"{side}_MARK_{i:03d} " + "word " * words,
            header=f"[{side}.py · def f{i} · lines {i}-{i}]",
            source=f"{side}.py",
            start_line=i,
            end_line=i,
            vector=V,
        )
        for i in range(parts)
    ]
    artifact_id = f"{side}-summary"
    write_artifact(
        db,
        ArtifactRecord(
            id=artifact_id,
            name=f"{side}.py",
            side=side,
            embedding_model="codestral-embed",
            dim=3,
        ),
        list(reversed(rows)) if reverse else rows,
    )
    return artifact_id


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "secret-key")
    monkeypatch.setattr("labpilot.llm.chain.time.sleep", lambda _seconds: None)


def sent_prompt() -> str:
    return json.loads(responses.calls[0].request.body)["contents"][0]["parts"][0][
        "text"
    ]


@responses.activate
def test_the_stored_parts_reach_the_provider_in_order_and_the_text_comes_back(db):
    # written back to front on purpose: the order must come from chunk_index
    # and not from where Postgres happens to keep the rows
    artifact = store(db, "B", parts=3, reverse=True)
    responses.post(f"{BASE}/one:generateContent", json=answered("It trains a model."))

    text = summaries.make_summarizer(db, LLMClient(chain=(provider(),)))(artifact)

    assert text == "It trains a model."
    prompt = sent_prompt()
    assert "All 3 parts are sent to you below." in prompt
    positions = [prompt.index(f"B_MARK_{i:03d}") for i in range(3)]
    assert positions == sorted(positions)
    assert "[B.py · def f0 · lines 0-0]" in prompt


@responses.activate
def test_a_big_artifact_is_cut_to_its_first_parts_and_the_prompt_says_so(db):
    artifact = store(db, "B", parts=150, words=120)
    responses.post(f"{BASE}/one:generateContent", json=answered())

    summaries.make_summarizer(db, LLMClient(chain=(provider(),)))(artifact)

    prompt = sent_prompt()
    found = re.search(r"Only the first (\d+) of 150 parts", prompt)
    assert found, "a cut artifact must say it was cut"
    sent = int(found.group(1))
    assert 0 < sent < 150
    assert f"B_MARK_{sent - 1:03d}" in prompt
    assert f"B_MARK_{sent:03d}" not in prompt


def test_an_artifact_that_is_not_stored_is_the_api_error(db):
    summarize = summaries.make_summarizer(db, LLMClient(chain=(provider(),)))

    with pytest.raises(UnknownArtifactId):
        summarize("A-never-stored")


class MeetingClient:
    """Answers with the marker of the FIRST part it was shown, after meeting.

    The barrier only opens when both sides' calls are in flight together, so a
    graph that quietly ran them one after the other would time out here. The
    answer names the side, so a mix-up of the two artifacts shows up too.
    """

    def __init__(self) -> None:
        self.barrier = threading.Barrier(2, timeout=10)

    def generate(self, prompt: str, *, max_tokens: int) -> LLMResult:
        self.barrier.wait()
        marker = re.search(r"([AB])_MARK_\d{3}", prompt)
        return LLMResult(text=f"summary of {marker.group(0)}", model="fake", tier=1)


def graph(summarize):
    return build_graph(
        measure=lambda a, b: "sides",
        fits=lambda sides, question: True,
        stuff=lambda sides, question: ((), None),
        search_one=lambda sides, query: (),
        totals_of=lambda sides: {"A": 1},
        rank_side=lambda question, pile: pile,
        plan=lambda question, a, b: Plan(steps=(), queries=()),
        make_prompt=lambda chunks, **_: ("the prompt", ()),
        generate=lambda prompt: "the result",
        summarize=summarize,
    )


def test_two_summaries_run_together_over_one_connection_and_stay_separate(db):
    a = store(db, "A", parts=4)
    b = store(db, "B", parts=4)

    for _ in range(5):
        summarize = summaries.make_summarizer(db, MeetingClient())
        final = graph(summarize).invoke({"question": "why?", "a": a, "b": b})

        assert final["summary_a"] == "summary of A_MARK_000"
        assert final["summary_b"] == "summary of B_MARK_000"

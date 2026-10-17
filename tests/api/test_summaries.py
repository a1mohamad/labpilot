from types import SimpleNamespace

import pytest

from labpilot.api import summaries
from labpilot.api.errors import GenerationUnavailable, UnknownArtifactId
from labpilot.llm import AllFreeTiersExhausted
from labpilot.prompts import SUMMARY_MAX_TOKENS
from labpilot.store import StoredChunk, UnknownArtifact


def chunk(index: int, text: str) -> StoredChunk:
    return StoredChunk(
        chunk_index=index,
        text=text,
        header=f"[a.py · part {index}]",
        source="a.py",
        start_line=1,
        end_line=2,
    )


class FakeClient:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls = []

    def generate(self, prompt, *, max_tokens):
        self.calls.append((prompt, max_tokens))
        if self.error:
            raise self.error
        return SimpleNamespace(text="a short summary")


def make(monkeypatch, client, *, chunks=(), error=None):
    def fake_read(conn, artifact_id):
        if error:
            raise error
        return tuple(chunks)

    monkeypatch.setattr(summaries, "read_chunks", fake_read)
    return summaries.make_summarizer(object(), client)


def test_the_summary_is_the_text_the_model_wrote(monkeypatch):
    summarize = make(monkeypatch, FakeClient(), chunks=[chunk(0, "alpha body")])

    assert summarize("A-1") == "a short summary"


def test_the_model_is_given_the_parts_and_a_token_budget(monkeypatch):
    client = FakeClient()
    chunks = [chunk(0, "alpha body"), chunk(1, "beta body")]

    make(monkeypatch, client, chunks=chunks)("A-1")

    prompt, max_tokens = client.calls[0]
    assert "alpha body" in prompt
    assert "beta body" in prompt
    assert max_tokens == SUMMARY_MAX_TOKENS


def test_an_unknown_artifact_becomes_the_api_error(monkeypatch):
    summarize = make(monkeypatch, FakeClient(), error=UnknownArtifact("no artifact"))

    with pytest.raises(UnknownArtifactId):
        summarize("A-missing")


def test_when_every_tier_fails_the_error_becomes_the_api_error(monkeypatch):
    client = FakeClient(error=AllFreeTiersExhausted(()))
    summarize = make(monkeypatch, client, chunks=[chunk(0, "alpha body")])

    with pytest.raises(GenerationUnavailable):
        summarize("A-1")

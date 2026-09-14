"""Ingest twice, then ask - over real HTTP, against a real database.

THE ONE LEVEL NOTHING ELSE COVERS. Every other test holds one seam still:
test_artifacts.py fakes the store, test_ask.py writes rows by hand and skips
the API, test_api_over_the_chain.py stubs the store to exercise the chain.
Nothing runs POST /artifacts and POST /compare against each other, which is
the entire shape slice 7 exists to produce:

    once      POST /artifacts   a file   ->  an id
    per turn  POST /compare     two ids  ->  a report

Real: HTTP, chunking, embedding calls, Postgres, the stuff/search decision,
selection, the prompt, and citation resolution. Faked: only the two things
that cost money - the embedder and the model.
"""

from __future__ import annotations

import contextlib

import pytest
from fastapi.testclient import TestClient

from labpilot.api import ApiConfig, app, get_client, services
from labpilot.embed.contracts import EmbeddingBatch
from labpilot.llm import LLMResult

pytestmark = pytest.mark.database

PAPER = b"# Method\n\nWe add two numbers and report the sum.\n"

# TWO functions, each long enough to become its own chunk, so the cited line
# does NOT sit on line 1. A one-chunk fixture cannot tell a correct start_line
# from a lost one, because both resolve to the same place - measured, by a
# mutation that forced start_line=1 and broke nothing at all.
CODE = (
    "def normalise(values, offset):\n"
    + "".join(f"    values[{n}] = values[{n}] * 31 + offset\n" for n in range(25))
    + "    return values\n\n\n"
    "def add(x, y):\n"
    + "".join(f"    scratch_{n} = x * {n} + y\n" for n in range(25))
    + "    return x + y\n"
).encode("utf-8")

# `return x + y` is the LAST line of the SECOND chunk, at line 56 of the file.
CITED_LINE = 56
ANSWER = 'B adds the two arguments [B-1 "return x + y"].'


class CountingEmbedder:
    """Counts what it was asked to embed, split by task.

    That split is the whole claim of the ingest/ask split: a DOCUMENT embed is
    the expensive one and must happen once per artifact, ever. A QUERY embed is
    ~20 tokens and may happen per turn.
    """

    name, model, dim = "Counting", "fake-embed", 3

    def __init__(self) -> None:
        self.documents = 0
        self.queries = 0

    def embed(self, texts, *, task: str = "document"):
        if task == "query":
            self.queries += len(texts)
        else:
            self.documents += len(texts)

        return EmbeddingBatch(
            vectors=tuple((1.0, 0.0, float(i)) for i, _ in enumerate(texts)),
            model=self.model,
            dim=self.dim,
            prompt_tokens=0,
        )


class FakeClient:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str, *, max_tokens: int = 0) -> LLMResult:
        self.prompts.append(prompt)
        return LLMResult(text=ANSWER, model="fake-model", tier=1, finish_reason="STOP")


@pytest.fixture
def embedder(db, monkeypatch) -> CountingEmbedder:
    counting = CountingEmbedder()
    monkeypatch.setattr(services, "_pick_embedder", lambda **kw: (counting, 0.1))
    monkeypatch.setattr(services, "MIGRATION", (counting,))

    # Both routes open their own connection. They must land in the TEST
    # schema, not the real one - the fixture connection already carries the
    # search path as a startup option.
    held = contextlib.nullcontext(db)
    monkeypatch.setattr("labpilot.api.routers.artifacts.connect", lambda *a, **k: held)
    monkeypatch.setattr("labpilot.api.routers.compare.connect", lambda *a, **k: held)
    return counting


@pytest.fixture
def llm() -> FakeClient:
    return FakeClient()


@pytest.fixture
def api(llm, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-real")
    app.dependency_overrides[get_client] = lambda: llm
    with TestClient(app) as running:
        yield running
    app.dependency_overrides.clear()


def ingest(api, name: str, raw: bytes, side: str) -> str:
    response = api.post(
        f"{ApiConfig.PREFIX}/artifacts",
        data={"side": side},
        files={"file": (name, raw, "text/plain")},
    )
    assert response.status_code == 201, response.text
    return response.json()["artifact_id"]


def test_two_uploads_then_a_question_produces_a_cited_answer(api, embedder, llm):
    """The walking skeleton of Option 2, end to end.

    The citation is the part that matters. The model gives a POINTER; we read
    the line back from OUR copy - and that copy has now been through Postgres
    and come back. If the store dropped a header, shifted a start_line, or
    reordered the chunks, the quote would still be found in the text and would
    resolve to the WRONG line, confidently and with nothing raising.
    """
    a_id = ingest(api, "paper.md", PAPER, "A")
    b_id = ingest(api, "train.py", CODE, "B")

    assert a_id.startswith("A-") and b_id.startswith("B-")

    response = api.post(
        f"{ApiConfig.PREFIX}/compare",
        json={"a": a_id, "b": b_id, "question": "why do the results diverge?"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer"] == ANSWER
    assert body["chunks"]["A"]["total"] >= 1
    assert body["chunks"]["B"]["total"] >= 1

    cited = body["citations"]["resolved_list"]
    assert body["citations"]["written"] == 1
    assert len(cited) == 1
    assert cited[0]["source"] == "train.py"
    assert cited[0]["line"] == CITED_LINE
    assert cited[0]["text"] == "    return x + y"
    assert cited[0]["unique"] is True


def a_repository_sized_file(routines: int) -> bytes:
    """Big enough that the pair cannot be stuffed, so retrieval really runs."""
    body = "\n".join(f"    step_{n} = compute({n}) * 31 + offset" for n in range(20))
    return "\n\n".join(
        f"def routine_{index}(offset):\n{body}\n    return step_0\n"
        for index in range(routines)
    ).encode("utf-8")


def test_a_second_question_searches_the_stored_corpus_and_never_re_ingests(
    api, embedder, llm
):
    """THE REASON THE ENDPOINT WAS SPLIT IN TWO, on the expensive branch.

    Under the old single endpoint every question re-uploaded, re-chunked and
    re-embedded both sides - about fifteen minutes per question for a
    FastAPI-sized repository. So the claim is not "it is faster", it is "the
    expensive work happens once", and the honest way to check that is to count
    DOCUMENT embeds and watch them stop while QUERY embeds carry on.

    This is also the only place the search branch runs end to end over HTTP:
    too large to stuff, so measure -> embed the question -> search per side ->
    gate -> rerank -> select -> prompt, against real rows.
    """
    a_id = ingest(api, "paper.md", PAPER, "A")
    b_id = ingest(api, "train.py", a_repository_sized_file(120), "B")

    ingested = embedder.documents
    assert ingested > 50, "the fixture must be large enough to need retrieval"
    assert embedder.queries == 0, "ingest embeds documents, never queries"

    for question in ("why do they diverge?", "what should I run next?"):
        response = api.post(
            f"{ApiConfig.PREFIX}/compare",
            json={"a": a_id, "b": b_id, "question": question},
        )
        assert response.status_code == 200, response.text

    assert embedder.documents == ingested, (
        "asking a question must never re-embed the corpus"
    )
    # One query embed per SIDE per question: the two artifacts may hold two
    # different embedders, so each side's question is embedded in its own space.
    assert embedder.queries == 4

    sent = response.json()["chunks"]["B"]
    assert sent["sent"] < sent["total"], "a large side must really be retrieved from"
    assert "NOT searched" in llm.prompts[-1], (
        "a partial side must SAY it is partial, or the model reads a handful "
        "of chunks as the whole file"
    )

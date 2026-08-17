from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from labpilot.api import MAX_UPLOAD_BYTES, app, get_client
from labpilot.ingest import chunk_file
from labpilot.llm import AllFreeTiersExhausted, Attempt, LLMResult
from labpilot.prompts import PROMPT_BUDGET, REPORT
from labpilot.tokens import estimate_tokens

SAMPLES = Path("data/samples/quora_siamese")
QUESTION = "Compare these and explain why the results diverge."

PAPER = ("a.md", b"# Method\n\nWe add two numbers.\n", "text/markdown")
CODE = ("b.py", b"def add(x, y):\n    return x + y\n", "text/x-python")

ANSWER = 'B adds two numbers [B-0 "return x + y"].'


@dataclass
class FakeClient:
    result: LLMResult
    error: Exception | None = None
    prompts: list[str] = field(default_factory=list)

    def generate(self, prompt: str, *, max_tokens: int = 0) -> LLMResult:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error

        return self.result


@pytest.fixture
def fake():
    return FakeClient(
        result=LLMResult(text=ANSWER, model="fake-model", tier=1, finish_reason="STOP")
    )


@pytest.fixture
def client(fake):
    app.dependency_overrides[get_client] = lambda: fake
    yield TestClient(app)
    app.dependency_overrides.clear()


def post(client, *, a=PAPER, b=CODE, question=QUESTION):
    return client.post("/compare", files={"a": a, "b": b}, data={"question": question})


def test_compare_returns_the_answer_and_the_model_that_produced_it(client):
    response = post(client)

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == ANSWER
    assert body["model"] == "fake-model"
    assert body["tier"] == 1
    assert body["finish_reason"] == "STOP"


def test_the_response_counts_the_chunks_of_each_side(client):
    body = post(client).json()

    assert body["chunks"]["A"] == {"total": 1, "sent": 1}
    assert body["chunks"]["B"] == {"total": 1, "sent": 1}


def test_a_resolved_citation_carries_the_real_line_number(client):
    body = post(client).json()

    assert body["citations"]["written"] == 1
    assert body["citations"]["resolved"] == 1
    cited = body["citations"]["resolved_list"][0]
    assert cited["source"] == "b.py"
    assert cited["line"] == 2
    assert cited["text"] == "    return x + y"


def test_a_citation_pointing_at_nothing_is_counted_but_not_resolved(client, fake):
    fake.result = LLMResult(
        text='B trains a model [B-0 "optimizer.zero_grad()"].',
        model="fake-model",
        tier=1,
    )

    body = post(client).json()

    assert body["citations"]["written"] == 1
    assert body["citations"]["resolved"] == 0
    assert body["citations"]["resolved_list"] == []


def test_a_binary_upload_is_rejected_as_not_text(client):
    response = post(client, b=("logo.png", b"\x89PNG\r\n\x1a\n\x00\x00", "image/png"))

    assert response.status_code == 422
    assert "not UTF-8" in response.json()["detail"]


def test_an_upload_over_the_size_limit_is_rejected(client):
    huge = b"x = 1\n" * 200_000
    assert len(huge) > MAX_UPLOAD_BYTES, "this payload must exceed the real limit"

    response = post(client, b=("big.py", huge, "text/x-python"))

    assert response.status_code == 413
    assert str(MAX_UPLOAD_BYTES) in response.json()["detail"]


def test_an_upload_under_the_size_limit_is_accepted(client):
    ordinary = b"x = 1\n" * 100_000
    assert len(ordinary) < MAX_UPLOAD_BYTES

    assert post(client, b=("ordinary.py", ordinary, "text/x-python")).status_code == 200


def test_an_upload_without_a_file_extension_is_rejected(client):
    response = post(client, b=("train", b"x = 1\n", "text/plain"))

    assert response.status_code == 422
    assert "extension" in response.json()["detail"]


def test_an_empty_upload_is_rejected(client):
    response = post(client, b=("empty.py", b"", "text/x-python"))

    assert response.status_code == 422
    assert "no text" in response.json()["detail"]


def test_a_blank_question_is_rejected(client):
    response = post(client, question="   ")

    assert response.status_code == 422
    assert "question" in response.json()["detail"]


def test_a_rejected_upload_never_reaches_the_model(client, fake):
    post(client, b=("logo.png", b"\x89PNG\r\n\x1a\n", "image/png"))

    assert fake.prompts == []


def test_all_tiers_exhausted_reports_which_tiers_failed(client, fake):
    fake.error = AllFreeTiersExhausted(
        (
            Attempt(tier=1, model="gemini-3.7-flash", error="HTTP 429"),
            Attempt(tier=2, model="gemini-3.6-flash", error="HTTP 503"),
        )
    )

    response = post(client)

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["message"] == "every free tier failed"
    assert [one["model"] for one in detail["attempts"]] == [
        "gemini-3.7-flash",
        "gemini-3.6-flash",
    ]


def test_the_failed_tiers_of_a_successful_answer_reach_the_response(client, fake):
    fake.result = LLMResult(
        text=ANSWER,
        model="gemini-3.6-flash",
        tier=2,
        finish_reason="STOP",
        attempts=(Attempt(tier=1, model="gemini-3.7-flash", error="HTTP 503"),),
    )

    body = post(client).json()

    assert body["tier"] == 2
    assert body["attempts"] == [
        {"tier": 1, "model": "gemini-3.7-flash", "error": "HTTP 503"}
    ]


def test_an_artifact_too_large_to_outline_is_refused_before_the_model(client, fake):
    """A legal upload can still make the outline alone exceed the whole budget.

    Measured 2026-08-17: 875KB of Python is 8,334 parts, whose outline costs
    210,541 tokens of a 26,000 budget. select() then returns nothing and the
    prompt is 185,640 tokens of headers with no artifact text in it at all.
    Gemini's 1M context means it would be sent, spending a scarce request to
    ask a model about a list of filenames.
    """
    many_parts = b"def step(x):\n    return x * 2 + 1\n\n" * 25_000
    assert len(many_parts) < MAX_UPLOAD_BYTES, "must pass the upload size check"

    response = post(client, b=("many.py", many_parts, "text/x-python"))

    assert response.status_code == 413
    assert "too large to compare" in response.json()["detail"]
    assert fake.prompts == []


def test_non_ascii_content_survives_the_round_trip(client, fake):
    """Hit for real on 2026-08-17 outside the app, printing a U+2212 minus."""
    body = "ratio = 0.5  # −4.1 F1, α ≤ 0.05, تست"
    fake.result = LLMResult(
        text=f'B loses accuracy [B-0 "{body}"].', model="fake-model", tier=1
    )

    response = post(client, b=("b.py", body.encode("utf-8"), "text/x-python"))

    assert response.status_code == 200
    cited = response.json()["citations"]["resolved_list"]
    assert cited[0]["text"] == body


def test_the_endpoint_sends_the_report_instructions(client, fake):
    post(client)

    prompt = fake.prompts[0]
    assert REPORT.header in prompt
    assert REPORT.closing in prompt
    assert QUESTION in prompt


def test_the_real_sample_pair_flows_through_the_endpoint(client, fake):
    response = client.post(
        "/compare",
        files={
            "a": ("A_paper.md", (SAMPLES / "A_paper.md").read_bytes(), "text/markdown"),
            "b": (
                "B_train.py",
                (SAMPLES / "B_train.py").read_bytes(),
                "text/x-python",
            ),
        },
        data={"question": QUESTION},
    )

    assert response.status_code == 200
    body = response.json()
    expected_a = len(chunk_file(SAMPLES / "A_paper.md", side="A", artifact_id="a"))
    expected_b = len(chunk_file(SAMPLES / "B_train.py", side="B", artifact_id="b"))

    assert body["chunks"]["A"]["total"] == expected_a
    assert body["chunks"]["B"]["total"] == expected_b
    assert body["chunks"]["B"]["sent"] < expected_b

    prompt = fake.prompts[0]
    assert "A-0" in prompt
    assert "B-0" in prompt
    assert estimate_tokens(prompt) <= PROMPT_BUDGET

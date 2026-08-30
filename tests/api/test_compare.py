from __future__ import annotations

from labpilot.api import ApiConfig
from labpilot.ingest import chunk_file
from labpilot.llm import AllFreeTiersExhausted, Attempt, LLMResult
from labpilot.prompts import PROMPT_BUDGET, REPORT
from labpilot.tokens import estimate_tokens
from tests.api.conftest import ANSWER, QUESTION, SAMPLES, post, problem
from tests.unit.ingest.test_pdf import a_pdf_with_no_text_layer


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
    assert problem(response)["code"] == "unreadable_upload"
    assert "not UTF-8" in problem(response)["message"]


def test_an_upload_over_the_size_limit_is_rejected(client):
    huge = b"x = 1\n" * 900_000
    assert len(huge) > ApiConfig.MAX_UPLOAD_BYTES, "must exceed the real limit"

    response = post(client, b=("big.py", huge, "text/x-python"))

    assert response.status_code == 413
    assert problem(response)["code"] == "upload_too_large"
    assert str(ApiConfig.MAX_UPLOAD_BYTES) in problem(response)["message"]


def test_an_upload_under_the_size_limit_is_accepted(client):
    ordinary = b"x = 1\n" * 100_000
    assert len(ordinary) < ApiConfig.MAX_UPLOAD_BYTES

    assert post(client, b=("ordinary.py", ordinary, "text/x-python")).status_code == 200


def test_an_upload_without_a_file_extension_is_rejected(client):
    response = post(client, b=("train", b"x = 1\n", "text/plain"))

    assert response.status_code == 422
    assert problem(response)["code"] == "unnamed_upload"
    assert "extension" in problem(response)["message"]


def test_an_empty_upload_is_rejected(client):
    response = post(client, b=("empty.py", b"", "text/x-python"))

    assert response.status_code == 422
    assert problem(response)["code"] == "empty_artifact"


def test_a_blank_question_is_rejected(client):
    response = post(client, question="   ")

    assert response.status_code == 422
    assert problem(response)["code"] == "invalid_question"


def test_a_missing_field_is_reported_in_the_same_envelope(client):
    response = client.post(
        f"{ApiConfig.PREFIX}/compare",
        files={"a": ("a.md", b"# hi\n\ntext", "text/markdown")},
        data={"question": QUESTION},
    )

    assert response.status_code == 422
    assert problem(response)["code"] == "invalid_request"
    assert "b" in problem(response)["message"]


def test_a_rejected_upload_never_reaches_the_model(client, fake):
    post(client, b=("logo.png", b"\x89PNG\r\n\x1a\n", "image/png"))

    assert fake.prompts == []


def test_every_error_carries_a_request_id_in_body_and_header(client):
    response = post(client, question="   ")

    assert problem(response)["request_id"]
    assert response.headers["x-request-id"] == problem(response)["request_id"]


def test_all_tiers_exhausted_reports_which_tiers_failed(client, fake):
    fake.error = AllFreeTiersExhausted(
        (
            Attempt(tier=1, model="gemini-3.7-flash", error="HTTP 429"),
            Attempt(tier=2, model="gemini-3.6-flash", error="HTTP 503"),
        )
    )

    response = post(client)

    assert response.status_code == 503
    assert problem(response)["code"] == "generation_unavailable"
    assert [one["model"] for one in problem(response)["attempts"]] == [
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
    assert len(many_parts) < ApiConfig.MAX_UPLOAD_BYTES, "must pass the size check"

    response = post(client, b=("many.py", many_parts, "text/x-python"))

    assert response.status_code == 413
    assert problem(response)["code"] == "artifacts_too_large_to_compare"
    assert fake.prompts == []


def test_non_ascii_content_survives_the_round_trip(client, fake):
    """Hit for real on 2026-08-17 outside the app, printing a U+2212 minus."""
    body = "ratio = 0.5  # −4.1 F1, α ≤ 0.05, تست"
    fake.result = LLMResult(
        text=f'B loses accuracy [B-0 "{body}"].', model="fake-model", tier=1
    )

    response = post(client, b=("b.py", body.encode("utf-8"), "text/x-python"))

    assert response.status_code == 200
    assert response.json()["citations"]["resolved_list"][0]["text"] == body


def test_the_endpoint_sends_the_report_instructions(client, fake):
    post(client)

    prompt = fake.prompts[0]
    assert REPORT.header in prompt
    assert REPORT.closing in prompt
    assert QUESTION in prompt


def test_the_real_sample_pair_flows_through_the_endpoint(client, fake):
    response = client.post(
        f"{ApiConfig.PREFIX}/compare",
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


def test_a_file_the_door_no_longer_decodes_still_reaches_the_loader_intact(
    client, fake
):
    """The door stopped decoding, so a byte-order mark now reaches the
    chunker. It must not survive into the text, or every citation shifts."""
    body = "def add(x, y):\n    return x + y\n"
    marked = "\ufeff".encode("utf-8") + body.encode("utf-8")
    fake.result = LLMResult(
        text='B adds [B-0 "return x + y"].', model="fake-model", tier=1
    )

    response = post(client, b=("b.py", marked, "text/x-python"))

    assert response.status_code == 200
    cited = response.json()["citations"]["resolved_list"][0]
    assert cited["line"] == 2
    assert cited["text"] == "    return x + y"


def test_a_pdf_upload_is_read_as_a_document_not_refused_as_binary(client, fake):
    """Before the bytes refactor a PDF died at the door as 'not UTF-8 text'."""
    raw = (SAMPLES.parent / "pdf" / "two_column.pdf").read_bytes()
    fake.result = LLMResult(text="No citation.", model="fake-model", tier=1)

    response = post(client, a=("paper.pdf", raw, "application/pdf"))

    assert response.status_code == 200
    assert response.json()["chunks"]["A"]["total"] > 1


def test_a_scanned_pdf_is_a_422_that_says_why(client):
    response = post(
        client, a=("scan.pdf", a_pdf_with_no_text_layer(), "application/pdf")
    )

    assert response.status_code == 422
    assert problem(response)["code"] == "unreadable_upload"
    assert "scanned" in problem(response)["message"]


def test_a_credentials_file_is_refused_at_the_upload_door(client):
    """READABLE_SUFFIXES keeps .env out of a repository walk, but the API door
    only ever checked that a suffix EXISTS -- so prod.env used to upload fine
    and its contents would reach a model provider."""
    response = post(client, b=("prod.env", b"MISTRAL_API_KEY=sk-real\n", "text/plain"))

    assert response.status_code == 422
    assert problem(response)["code"] == "secret_upload"

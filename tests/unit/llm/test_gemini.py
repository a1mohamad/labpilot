import json

import pytest
import requests
import responses

from labpilot.llm import GeminiProvider, LLMError, LLMResult

BASE_URL = "https://provider.test/v1beta/models"
URL = f"{BASE_URL}/test-model:generateContent"


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "secret-key")
    return GeminiProvider(
        name="Test Gemini",
        tier=2,
        url=BASE_URL,
        model="test-model",
        api_key_env="TEST_API_KEY",
        context_window=8_000,
        max_output_tokens=4_000,
    )


def ok_body(parts=("hello",), finish_reason="STOP", model="test-model-001"):
    return {
        "modelVersion": model,
        "candidates": [
            {
                "content": {"parts": [{"text": part} for part in parts]},
                "finishReason": finish_reason,
            }
        ],
    }


@responses.activate
def test_complete_returns_result_on_success(provider):
    responses.post(URL, json=ok_body())

    result = provider.complete("why do these diverge?")

    assert isinstance(result, LLMResult)
    assert result.text == "hello"
    assert result.model == "test-model-001"
    assert result.tier == 2
    assert result.attempts == ()


@responses.activate
def test_complete_sends_expected_request(provider):
    responses.post(URL, json=ok_body())

    provider.complete("compare these", max_tokens=16)

    request = responses.calls[0].request
    body = json.loads(request.body)
    assert request.url == URL
    assert request.headers["x-goog-api-key"] == "secret-key"
    assert body["contents"] == [{"parts": [{"text": "compare these"}]}]
    assert body["generationConfig"]["maxOutputTokens"] == 16


@responses.activate
def test_complete_joins_every_part_of_the_answer(provider):
    responses.post(URL, json=ok_body(parts=("first ", "second")))

    assert provider.complete("hi").text == "first second"


@responses.activate
def test_complete_raises_llm_error_when_prompt_blocked(provider):
    responses.post(URL, json={"promptFeedback": {"blockReason": "SAFETY"}})

    with pytest.raises(LLMError, match="SAFETY"):
        provider.complete("hi")


@responses.activate
def test_complete_reports_finish_reason_on_empty_answer(provider):
    responses.post(URL, json=ok_body(parts=(), finish_reason="MAX_TOKENS"))

    with pytest.raises(LLMError, match="MAX_TOKENS"):
        provider.complete("hi")


@responses.activate
def test_complete_raises_llm_error_on_unexpected_shape(provider):
    responses.post(URL, json={"candidates": ["not a dict"]})

    with pytest.raises(LLMError, match="unexpected response shape"):
        provider.complete("hi")


@pytest.mark.parametrize("status", [401, 429, 500])
@responses.activate
def test_complete_raises_llm_error_on_bad_status(provider, status):
    responses.post(URL, status=status, json={"error": {"message": "nope"}})

    with pytest.raises(LLMError, match=str(status)):
        provider.complete("hi")


@responses.activate
def test_complete_raises_llm_error_on_network_failure(provider):
    responses.post(URL, body=requests.exceptions.ConnectTimeout("timed out"))

    with pytest.raises(LLMError) as exc_info:
        provider.complete("hi")

    assert isinstance(exc_info.value.__cause__, requests.exceptions.ConnectTimeout)


@responses.activate
def test_complete_raises_llm_error_on_non_json_body(provider):
    responses.post(URL, body="<html>gateway error</html>", content_type="text/html")

    with pytest.raises(LLMError, match="not JSON"):
        provider.complete("hi")


def test_complete_raises_llm_error_when_key_missing(provider, monkeypatch):
    monkeypatch.delenv("TEST_API_KEY")

    with pytest.raises(LLMError, match="TEST_API_KEY"):
        provider.complete("hi")


def test_complete_rejects_empty_prompt_as_caller_bug(provider):
    with pytest.raises(ValueError):
        provider.complete("   ")

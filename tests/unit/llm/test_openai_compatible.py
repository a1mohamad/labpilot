import json

import pytest
import requests
import responses

from labpilot.llm import LLMError, LLMResult, OpenAICompatibleProvider

URL = "https://provider.test/v1/chat/completions"


def build_provider(**extra) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name="Test Provider",
        tier=1,
        url=URL,
        model="test/model",
        api_key_env="TEST_API_KEY",
        context_window=8_000,
        max_output_tokens=4_000,
        **extra,
    )


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "secret-key")
    return build_provider()


def ok_body(content="hello", finish_reason="stop", model="test/model-v2"):
    return {
        "model": model,
        "choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
    }


@responses.activate
def test_complete_returns_result_on_success(provider):
    responses.post(URL, json=ok_body())

    result = provider.complete("why do these diverge?")

    assert isinstance(result, LLMResult)
    assert result.text == "hello"
    assert result.model == "test/model-v2"
    assert result.tier == 1
    assert result.attempts == ()


@responses.activate
def test_complete_sends_expected_request(provider):
    responses.post(URL, json=ok_body())

    provider.complete("compare these", max_tokens=16)

    request = responses.calls[0].request
    body = json.loads(request.body)
    assert request.headers["Authorization"] == "Bearer secret-key"
    assert body["model"] == "test/model"
    assert body["messages"] == [{"role": "user", "content": "compare these"}]
    assert body["max_tokens"] == 16


@responses.activate
def test_the_finish_reason_reaches_the_result(provider):
    responses.post(URL, json=ok_body(finish_reason="length"))

    assert provider.complete("hi").finish_reason == "length"


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


@responses.activate
def test_complete_raises_llm_error_on_unexpected_shape(provider):
    responses.post(URL, json={"model": "test/model"})

    with pytest.raises(LLMError, match="unexpected response shape"):
        provider.complete("hi")


@pytest.mark.parametrize("content", ["", "   ", None])
@responses.activate
def test_complete_raises_llm_error_on_empty_answer(provider, content):
    responses.post(URL, json=ok_body(content=content))

    with pytest.raises(LLMError, match="empty answer"):
        provider.complete("hi")


def test_complete_raises_llm_error_when_key_missing(provider, monkeypatch):
    monkeypatch.delenv("TEST_API_KEY")

    with pytest.raises(LLMError, match="TEST_API_KEY"):
        provider.complete("hi")


def test_complete_rejects_empty_prompt_as_caller_bug(provider):
    with pytest.raises(ValueError):
        provider.complete("   ")


ACCOUNT_URL = "https://provider.test/accounts/{account_id}/v1/chat/completions"


@pytest.fixture
def account_provider(monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "secret-key")
    monkeypatch.setenv("TEST_ACCOUNT_ID", "acc-123")
    return OpenAICompatibleProvider(
        name="Account Provider",
        tier=1,
        url=ACCOUNT_URL,
        model="test/model",
        api_key_env="TEST_API_KEY",
        account_env="TEST_ACCOUNT_ID",
        context_window=8_000,
        max_output_tokens=4_000,
    )


@responses.activate
def test_complete_posts_to_url_with_account_id_substituted(account_provider):
    resolved = "https://provider.test/accounts/acc-123/v1/chat/completions"
    responses.post(resolved, json=ok_body())

    account_provider.complete("hi")

    assert responses.calls[0].request.url == resolved


def test_complete_raises_llm_error_when_account_id_missing(
    account_provider, monkeypatch
):
    monkeypatch.delenv("TEST_ACCOUNT_ID")

    with pytest.raises(LLMError, match="TEST_ACCOUNT_ID"):
        account_provider.complete("hi")


@responses.activate
def test_complete_refuses_a_prompt_larger_than_the_context_window(provider):
    with pytest.raises(LLMError, match="context window"):
        provider.complete("x" * 100_000, max_tokens=512)

    assert len(responses.calls) == 0


@responses.activate
def test_complete_refuses_max_tokens_above_the_output_limit(provider):
    with pytest.raises(LLMError, match="output limit"):
        provider.complete("hi", max_tokens=9_000)

    assert len(responses.calls) == 0


def test_extra_body_is_merged_into_the_request():
    reasoning = {"reasoning": {"effort": "high"}}

    payload = build_provider(extra_body=reasoning)._payload("hello", 100)

    assert payload["reasoning"] == {"effort": "high"}
    assert payload["model"] == "test/model"


def test_nothing_extra_is_sent_when_extra_body_is_not_set():
    payload = build_provider()._payload("hello", 100)

    assert set(payload) == {"model", "messages", "max_tokens", "temperature"}

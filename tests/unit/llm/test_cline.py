import json

import pytest
import responses

from labpilot.llm import ClineProvider, LLMError, LLMResult

URL = "https://api.cline.test/api/v1/chat/completions"


def build_provider(**extra) -> ClineProvider:
    return ClineProvider(
        name="Test Cline",
        tier=1,
        url=URL,
        model="z-ai/glm-5.3-flash",
        api_key_env="CLINE_API_KEY",
        context_window=8_000,
        max_output_tokens=4_000,
        **extra,
    )


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("CLINE_API_KEY", "secret-key")
    return build_provider()


def wrapped(content="hello", finish_reason="stop", model="z-ai/glm-5.3-flash", **usage):
    """The shape Cline really returns, measured live 2026-09-13."""
    return {
        "data": {
            "model": model,
            "choices": [
                {
                    "message": {"content": content, "reasoning": "thinking out loud"},
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": 35,
                "completion_tokens": 1557,
                "completion_tokens_details": {"reasoning_tokens": 1170},
                "cost": 0.00078375,
                **usage,
            },
        },
        "success": True,
    }


@responses.activate
def test_the_answer_is_read_out_of_the_data_envelope(provider):
    responses.post(URL, json=wrapped(content="clipped at 1.5"))

    result = provider.complete("why do these diverge?")

    assert isinstance(result, LLMResult)
    assert result.text == "clipped at 1.5"
    assert result.model == "z-ai/glm-5.3-flash"
    assert result.finish_reason == "stop"


@responses.activate
def test_a_plain_openai_body_is_refused_rather_than_read(provider):
    """The envelope is the whole reason this class exists.

    If Cline ever flattened its response we must fail loudly, not silently
    parse half of it.
    """
    responses.post(
        URL,
        json={"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]},
    )

    with pytest.raises(LLMError, match="data envelope"):
        provider.complete("compare these")


@responses.activate
def test_a_data_field_that_is_not_an_object_is_refused(provider):
    responses.post(URL, json={"data": "nonsense", "success": True})

    with pytest.raises(LLMError, match="data envelope"):
        provider.complete("compare these")


@responses.activate
def test_an_empty_answer_inside_the_envelope_is_still_a_failure(provider):
    """Measured: glm-5.3-flash spends the whole budget thinking and returns
    content=None, which Cline reports as its own 500. When it arrives as a
    200 instead, an answer of nothing is not an answer."""
    responses.post(URL, json=wrapped(content=None))

    with pytest.raises(LLMError, match="empty answer"):
        provider.complete("compare these")


@responses.activate
def test_the_request_is_the_plain_openai_shape(provider):
    responses.post(URL, json=wrapped())

    provider.complete("compare these", max_tokens=16)

    sent = json.loads(responses.calls[0].request.body)
    assert sent["model"] == "z-ai/glm-5.3-flash"
    assert sent["messages"] == [{"role": "user", "content": "compare these"}]
    assert sent["max_tokens"] == 16
    assert sent["temperature"] == 0.0
    assert "data" not in sent


@responses.activate
def test_the_key_travels_as_a_bearer_token(provider):
    responses.post(URL, json=wrapped())

    provider.complete("compare these")

    assert responses.calls[0].request.headers["Authorization"] == "Bearer secret-key"


@responses.activate
def test_extra_body_reaches_the_wire(monkeypatch):
    """Without a reasoning field glm-5.3-flash failed 3 of 5 live calls."""
    monkeypatch.setenv("CLINE_API_KEY", "secret-key")
    provider = build_provider(extra_body={"reasoning": {"effort": "high"}})
    responses.post(URL, json=wrapped())

    provider.complete("compare these")

    sent = json.loads(responses.calls[0].request.body)
    assert sent["reasoning"] == {"effort": "high"}


@responses.activate
def test_the_log_line_carries_the_cost_we_must_watch(provider, caplog):
    """Cline charges zero credits for a free model but still reports what it
    would have cost. That number turning non-zero is how the promotion ending
    becomes visible, so it must reach the log."""
    responses.post(URL, json=wrapped())

    with caplog.at_level("INFO", logger="labpilot.llm.base"):
        provider.complete("compare these")

    assert "cost 0.00078375" in caplog.text
    assert "1170 reasoning tokens" in caplog.text

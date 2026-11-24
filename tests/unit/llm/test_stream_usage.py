"""A streamed answer reports its tokens, like a plain one."""

import json
import logging

import pytest
import responses

from labpilot.llm.openai_compatible import OpenAICompatibleProvider

URL = "https://usage.test/v1/chat/completions"


def tier(**kw):
    return OpenAICompatibleProvider(
        name="T",
        tier=1,
        url=URL,
        model="m",
        api_key_env="USAGE_KEY",
        context_window=10_000,
        max_output_tokens=5_000,
        **kw,
    )


@pytest.fixture
def a_stream(monkeypatch):
    monkeypatch.setenv("USAGE_KEY", "k")
    pieces = [
        {"choices": [{"delta": {"content": "hi"}, "finish_reason": "stop"}]},
        # the counts come LAST, in a piece with no choices
        {"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 34}},
    ]
    body = "".join(f"data: {json.dumps(p)}\n\n" for p in pieces) + "data: [DONE]\n\n"
    with responses.RequestsMock() as mock:
        mock.add(responses.POST, URL, body=body, content_type="text/event-stream")
        yield mock


def test_the_counts_of_a_streamed_answer_are_asked_for_and_logged(a_stream, caplog):
    with caplog.at_level(logging.INFO, logger="labpilot.llm.base"):
        assert tier().complete("q", max_tokens=100).text == "hi"

    sent = json.loads(a_stream.calls[0].request.body)
    assert sent["stream"] is True
    assert sent["stream_options"] == {"include_usage": True}
    assert "12 in / 34 out" in caplog.text


def test_a_tier_that_may_refuse_the_field_is_not_sent_it(a_stream):
    tier(stream_usage=False).complete("q", max_tokens=100)

    sent = json.loads(a_stream.calls[0].request.body)
    assert sent["stream"] is True
    assert "stream_options" not in sent


def test_a_call_that_is_not_streamed_never_carries_stream_options():
    plain = tier(stream=False)

    assert "stream_options" not in plain._payload("q", 100)

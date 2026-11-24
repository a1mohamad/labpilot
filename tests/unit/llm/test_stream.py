"""A streamed answer is joined back, and a tier that stops writing is dropped."""

import json
import threading
import time

import pytest
import requests
import responses

from labpilot.llm import _stream, chain
from labpilot.llm._failures import worth_a_second_try
from labpilot.llm._stream import (
    events,
    first_piece_limit,
    join_gemini,
    join_openai,
    open_stream,
)
from labpilot.llm.chain import LLMClient
from labpilot.llm.contracts import LLMResult
from labpilot.llm.errors import LLMError
from labpilot.llm.gemini import GeminiProvider
from labpilot.llm.openai_compatible import OpenAICompatibleProvider

URL = "https://provider.test/v1/chat/completions"


class FakeResponse:
    """The lines of a body, each after a pause in seconds."""

    def __init__(self, *lines):
        self.lines, self.closed = lines, threading.Event()

    def iter_lines(self):
        for pause, line in self.lines:
            time.sleep(pause)
            yield line

    def close(self):
        self.closed.set()


def data(piece):
    return b"data: " + json.dumps(piece, ensure_ascii=False).encode()


@pytest.fixture
def waits(monkeypatch):
    def set_them(first, idle):
        token = first_piece_limit.set(first)
        monkeypatch.setattr(_stream, "IDLE_SECONDS", idle)
        tokens.append(token)

    tokens = []
    yield set_them
    for token in tokens:
        first_piece_limit.reset(token)


def piece(content=None, finish=None, **delta):
    if content is not None:
        delta["content"] = content
    return {"choices": [{"delta": delta, "finish_reason": finish}]}


def test_pieces_are_read_until_done_and_the_body_is_closed():
    body = FakeResponse(
        (0, b""),
        (0, b": ping"),
        (0, b"event: message"),
        (0, data({"a": 1})),
        (0, b"data: not json"),
        (0, b"data: [DONE]"),
        (0, data({"a": 2})),
    )
    assert list(events(body, "T")) == [{"a": 1}]
    assert body.closed.wait(2)


def test_a_piece_is_utf8_whatever_the_header_says_and_is_not_cut_at_u2028():
    text = "naïve   “é”"
    response = requests.Response()
    response.encoding = "ISO-8859-1"
    response._content = data({"t": text}) + b"\n\n"
    response._content_consumed = True
    assert list(events(response, "T")) == [{"t": text}]


def test_no_first_piece_gives_the_tier_up_and_is_not_retried(waits):
    waits(0.1, 5)
    with pytest.raises(LLMError, match="no answer piece") as caught:
        list(events(FakeResponse((1, data({"a": 1}))), "T"))
    assert caught.value.retryable is False


def test_keep_alive_lines_do_not_count_as_pieces(waits):
    waits(0.2, 5)
    body = FakeResponse(*[(0.05, b": ping")] * 20, (0, data({"a": 1})))
    with pytest.raises(LLMError, match="no answer piece"):
        list(events(body, "T"))


def test_silence_in_the_middle_gives_the_tier_up(waits):
    waits(5, 0.1)
    body = FakeResponse((0, data({"a": 1})), (1, data({"a": 2})))
    with pytest.raises(LLMError, match="the answer stopped") as caught:
        list(events(body, "T"))
    assert caught.value.retryable is False


def test_the_middle_may_be_quiet_for_longer_than_the_first_wait(waits):
    waits(0.2, 5)
    body = FakeResponse((0, data({"a": 1})), (0.4, data({"a": 2})))
    assert list(events(body, "T")) == [{"a": 1}, {"a": 2}]


def test_the_wait_for_the_first_piece_counts_from_the_request(waits):
    waits(0.5, 5)
    body = FakeResponse((0.3, data({"a": 1})))
    with pytest.raises(LLMError, match="no answer piece"):
        list(events(body, "T", started=time.monotonic() - 0.4))


def test_a_broken_stream_is_our_error():
    class Broken(FakeResponse):
        def iter_lines(self):
            yield data({"a": 1})
            raise requests.exceptions.ChunkedEncodingError("cut")

    with pytest.raises(LLMError, match="stream broke") as caught:
        list(events(Broken(), "T"))
    assert worth_a_second_try(caught.value)


def test_headers_that_do_not_come_give_the_tier_up_and_close_the_late_answer(waits):
    waits(0.1, 5)
    late = FakeResponse()

    def post():
        time.sleep(0.3)
        return late

    with pytest.raises(LLMError, match="no answer piece") as caught:
        open_stream(post, "T")
    assert caught.value.retryable is False
    assert caught.value.slow  # so the tier rests
    assert late.closed.wait(2)


def test_a_request_error_comes_through_unchanged():
    def post():
        raise requests.exceptions.ConnectTimeout("no")

    with pytest.raises(requests.exceptions.ConnectTimeout):
        open_stream(post, "T")


def test_openai_text_pieces_make_one_body():
    body = join_openai(
        iter(
            [
                {**piece("", role="assistant"), "model": "m"},
                piece("Hel"),
                piece("lo", reasoning="hidden"),
                {**piece(finish="stop"), "usage": {"total_tokens": 3}},
                {"choices": []},
            ]
        )
    )
    assert body["choices"] == [
        {"message": {"content": "Hello"}, "finish_reason": "stop"}
    ]
    assert (body["model"], body["usage"]) == ("m", {"total_tokens": 3})


def call(index, name=None, arguments=None):
    return {"index": index, "function": {"name": name, "arguments": arguments}}


def test_openai_tool_call_pieces_are_joined_by_index():
    body = join_openai(
        iter(
            [
                piece(tool_calls=[call(0, "one", '{"a":')]),
                piece(tool_calls=[call(1, "two", "{")]),
                piece(tool_calls=[call(0, None, "1}")]),
                piece(tool_calls=[call(1, None, "}")]),
                piece(finish="tool_calls"),
            ]
        )
    )
    calls = body["choices"][0]["message"]["tool_calls"]
    assert [c["function"] for c in calls] == [
        {"name": "one", "arguments": '{"a":1}'},
        {"name": "two", "arguments": "{}"},
    ]


def test_an_error_after_half_an_answer_is_an_error_and_not_the_half():
    body = join_openai(
        iter([piece("half"), {**piece(finish="error"), "error": {"code": 503}}])
    )
    assert body == {"error": {"code": 503}}


@pytest.mark.parametrize(
    ("join", "half"),
    [
        (join_openai, piece("half")),
        (join_gemini, {"candidates": [{"content": {"parts": [{"text": "half"}]}}]}),
    ],
)
def test_a_stream_that_ends_before_the_answer_is_not_a_whole_answer(join, half):
    with pytest.raises(LLMError, match="ended before"):
        join(iter([half]))


def gemini(*parts, finish=None):
    candidate = {"content": {"parts": list(parts)}}
    if finish:
        candidate["finishReason"] = finish
    return {"candidates": [candidate]}


def test_gemini_text_is_joined_and_thoughts_are_left_out():
    body = join_gemini(
        iter(
            [
                gemini({"text": "thinking", "thought": True}),
                gemini({"text": "Hel"}),
                gemini({"text": "lo"}, finish="STOP"),
            ]
        )
    )
    assert body["candidates"] == [
        {"content": {"parts": [{"text": "Hello"}]}, "finishReason": "STOP"}
    ]


def test_a_gemini_call_keeps_its_arguments():
    part = {"functionCall": {"name": "f", "args": {"a": 1}}}
    body = join_gemini(iter([gemini(part), gemini(finish="STOP")]))
    assert body["candidates"][0]["content"]["parts"] == [part]


def test_a_blocked_gemini_prompt_is_passed_on_for_its_own_error():
    blocked = {"promptFeedback": {"blockReason": "SAFETY"}}
    assert join_gemini(iter([blocked])) == blocked


def test_a_gemini_error_in_the_middle_keeps_its_status():
    with pytest.raises(LLMError) as caught:
        join_gemini(iter([gemini({"text": "a"}), {"error": {"code": 503}}]))
    assert caught.value.status == 503


def provider(**kw):
    return OpenAICompatibleProvider(
        name="T", tier=1, url=URL, model="m", api_key_env="T_KEY",
        context_window=99_999, max_output_tokens=9_999, **kw,
    )  # fmt: skip


@responses.activate
def test_a_streamed_answer_goes_through_the_whole_provider(monkeypatch):
    monkeypatch.setenv("T_KEY", "k")
    lines = b"\n\n".join([data(piece("héllo")), data(piece(finish="stop"))])
    responses.post(URL, body=lines + b"\n\n", content_type="text/event-stream")

    result = provider().complete("hi")

    assert (result.text, result.finish_reason) == ("héllo", "stop")
    assert json.loads(responses.calls[0].request.body)["stream"] is True


@responses.activate
@pytest.mark.parametrize("first", [0.1, 2.0])
def test_the_wait_of_a_whole_call_covers_the_headers_and_the_pieces(
    monkeypatch, waits, first
):
    monkeypatch.setenv("T_KEY", "k")
    waits(first, 5)
    seen = {}

    def answer(request):
        time.sleep(0.5)
        return 200, {}, data(piece("ok", "stop")) + b"\n\n"

    def watched(response, name, *, started):
        seen["waited"] = time.monotonic() - started
        return events(response, name, started=started)

    monkeypatch.setattr("labpilot.llm.base.events", watched)
    responses.add_callback(
        responses.POST, URL, callback=answer, content_type="text/event-stream"
    )

    if first < 0.5:
        with pytest.raises(LLMError, match="no answer piece"):
            provider().complete("hi")
        assert not seen
    else:
        assert provider().complete("hi").text == "ok"
        assert seen["waited"] >= 0.45


@responses.activate
def test_a_provider_with_streaming_off_sends_a_plain_call(monkeypatch):
    monkeypatch.setenv("T_KEY", "k")
    whole = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
    responses.post(URL, json=whole)

    assert provider(stream=False).complete("hi").text == "ok"
    assert "stream" not in json.loads(responses.calls[0].request.body)


@pytest.mark.parametrize(("model", "asked"), [("gemini-x", True), ("gemma-x", False)])
def test_google_is_asked_for_thoughts_except_gemma(model, asked):
    tier = GeminiProvider(
        name="G", tier=1, url="u", model=model, api_key_env="T_KEY",
        context_window=9, max_output_tokens=9, thinking="MEDIUM",
    )  # fmt: skip
    plain = tier._payload("hi", 5)
    config = tier._stream_payload(plain)["generationConfig"]["thinkingConfig"]
    assert config.get("includeThoughts", False) is asked
    assert config["thinkingLevel"] == "MEDIUM"
    assert "includeThoughts" not in plain["generationConfig"]["thinkingConfig"]


class Failing:
    """Fails `seconds` (of a fake clock) after each call starts."""

    name, tier, api_key_env, pool = "F", 1, "F_KEY", "F_POOL"

    def __init__(self, clock, *seconds):
        self.clock, self.seconds, self.limits = clock, list(seconds), []

    def complete(self, prompt, *, max_tokens=1, tool=None):
        self.limits.append(first_piece_limit.get())
        if not self.seconds:
            return LLMResult(text="ok", model="m", tier=1, finish_reason="stop")
        self.clock[0] += self.seconds.pop(0)
        raise LLMError("busy", status=502)


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(chain.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(chain.time, "sleep", lambda s: None)
    return now


@pytest.mark.parametrize(
    ("failures", "calls"),
    [
        ((9,), 2),  # fast: asked again
        ((11,), 1),  # came back after 10 s
        ((9, 9), 2),  # only one retry
    ],
)
def test_only_a_failure_that_came_back_fast_is_asked_again(clock, failures, calls):
    tier = Failing(clock, *failures)
    client = LLMClient(chain=(tier,), call_stop=None)
    try:
        client.generate("hi")
    except Exception:  # the walk ended with no answer
        pass
    assert len(tier.limits) == calls


def test_every_try_waits_the_same_time_for_the_first_piece(clock):
    tier = Failing(clock, 1)
    LLMClient(chain=(tier,), call_stop=None).generate("hi")
    assert tier.limits == [10.0, 10.0]


def test_the_limits_chosen_by_the_measurement():
    assert (_stream.FIRST_PIECE_SECONDS, _stream.IDLE_SECONDS) == (10.0, 15.0)


def test_a_cancelled_stream_ends_at_once_and_closes_its_connection(waits):
    waits(5, 5)
    token = _stream.Cancel()
    reset = _stream.cancel_token.set(token)

    class Endless(FakeResponse):
        def iter_lines(self):
            yield data({"a": 1})
            time.sleep(3)

    response = Endless()
    try:
        pieces = events(response, "T")
        next(pieces)
        token.cancel()
        started = time.monotonic()
        with pytest.raises(LLMError, match="cancelled"):
            next(pieces)
    finally:
        _stream.cancel_token.reset(reset)
    assert time.monotonic() - started < 1
    assert response.closed.wait(2)


def test_a_request_cancelled_before_its_headers_ends_at_once(waits):
    waits(5, 5)
    token = _stream.Cancel()
    reset = _stream.cancel_token.set(token)
    token.cancel()
    try:
        with pytest.raises(LLMError, match="cancelled"):
            open_stream(lambda: time.sleep(1), "T")
    finally:
        _stream.cancel_token.reset(reset)

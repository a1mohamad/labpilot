"""Read a streamed answer, and give up on a tier that stopped writing.

A model that works sends its answer in pieces (server-sent events, one
`data: {...}` line for each piece). So a dead tier is found in seconds: no
piece in FIRST_PIECE_SECONDS after the request, or none for IDLE_SECONDS in
the middle, means the tier is not writing. A keep-alive line (`: ping`) is NOT
a piece, because a server can send them for ever while nothing is written.

The pieces are joined back into the body a non-streamed call returns, so the
readers of each wire shape (openai_compatible.py, gemini.py) do not change.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from collections.abc import Callable, Iterator
from contextvars import ContextVar

import requests

from labpilot._text import truncate
from labpilot.llm.errors import LLMError

# Measured 2026-11-23 (D129): of 151 working calls away from Google, on prompts of
# 1K to 30K tokens, 140 had started within 10 s and 149 never paused for
# 15 s. A piece of the THINKING counts too. Google was overloaded that evening,
# so both numbers are to be checked on it on a normal day.
FIRST_PIECE_SECONDS = 10.0
IDLE_SECONDS = 15.0
# No piece has said why the answer ended. A connection that closes early looks
# like a normal end, so half an answer must not be taken for a whole one.
UNFINISHED = "unknown"
# A ContextVar, so that a measurement can wait longer without another argument.
first_piece_limit: ContextVar[float] = ContextVar(
    "first_piece_limit", default=FIRST_PIECE_SECONDS
)


class Cancel:
    """Lets another thread end a call that is no longer wanted.

    A call that lost a race (chain.py) would otherwise write on to its end, and
    keep the one slot of an account that takes one call at a time.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._doors: list[queue.Queue[tuple[str, object]]] = []
        self.done = False

    def watch(self, door: queue.Queue[tuple[str, object]]) -> None:
        with self._lock:
            self._doors.append(door)
            if self.done:
                door.put(("cancel", None))

    def cancel(self) -> None:
        with self._lock:
            self.done = True
            for door in self._doors:
                door.put(("cancel", None))


cancel_token: ContextVar[Cancel | None] = ContextVar("cancel_token", default=None)


def open_stream(post: Callable[[], requests.Response], name: str) -> requests.Response:
    """Send the request, and give up when no headers came in time.

    requests has ONE read timeout, for the headers and for every gap in the
    body, and ours are different, so the wait for the headers is kept here. The
    abandoned request closes itself when its answer, or its own timeout, comes.
    """
    limit = first_piece_limit.get()
    box: queue.Queue[tuple[str, object]] = queue.Queue()
    lock = threading.Lock()
    given_up = False

    def send() -> None:
        try:
            response = post()
        except Exception as exc:  # carried to the caller below
            box.put(("error", exc))
            return
        with lock:
            if not given_up:
                box.put(("response", response))
                return
        response.close()

    token = cancel_token.get()
    if token is not None:
        token.watch(box)
    threading.Thread(target=send, daemon=True).start()
    try:
        kind, value = box.get(timeout=limit)
    except queue.Empty:
        with lock:
            given_up = True
        try:
            # It may have come between the timeout and the flag.
            kind, value = box.get_nowait()
        except queue.Empty:
            raise LLMError(
                f"{name}: no answer piece after {limit:.0f}s",
                retryable=False,
                slow=True,
            ) from None
    if kind == "cancel":
        with lock:
            given_up = True
        try:
            kind, value = box.get_nowait()
            if kind == "response":
                value.close()  # type: ignore[attr-defined]
        except queue.Empty:
            pass
        raise LLMError(f"{name}: cancelled", retryable=False)
    if kind == "error":
        raise value  # type: ignore[misc]
    return value  # type: ignore[return-value]


def _pump(response: requests.Response, pieces: queue.Queue[tuple[str, object]]) -> None:
    """Read the body in a thread of its own, so the reader can stop waiting."""
    try:
        # BYTES, decoded here as UTF-8. requests would decode a `text/...` body
        # that names no charset as Latin-1, and would also cut lines at U+2028.
        for raw in response.iter_lines():
            if not raw.startswith(b"data:"):
                continue  # a blank line, an event name, or a keep-alive
            data = raw[5:].strip()
            if data == b"[DONE]":
                break
            try:
                piece = json.loads(data.decode("utf-8"))
            except ValueError:
                continue
            if isinstance(piece, dict):
                pieces.put(("piece", piece))
        pieces.put(("end", None))
    except Exception as exc:  # carried to the reader, see events()
        pieces.put(("broke", exc))
    finally:
        response.close()


def _close(response: requests.Response) -> None:
    # In a thread: closing can wait for the reader that is blocked in a read.
    threading.Thread(target=response.close, daemon=True).start()


def events(
    response: requests.Response, name: str, *, started: float | None = None
) -> Iterator[dict]:
    """The JSON pieces of a stream, until `[DONE]` or the end of the body.

    `started` is when the request was sent, so the wait for the first piece
    counts the wait for the headers too.
    """
    begun = time.monotonic() if started is None else started
    first = first_piece_limit.get()
    pieces: queue.Queue[tuple[str, object]] = queue.Queue()
    token = cancel_token.get()
    if token is not None:
        token.watch(pieces)
    threading.Thread(target=_pump, args=(response, pieces), daemon=True).start()

    wait = max(0.0, begun + first - time.monotonic())
    silent = f"no answer piece after {first:.0f}s"
    while True:
        try:
            kind, value = pieces.get(timeout=wait)
        except queue.Empty:
            _close(response)
            raise LLMError(f"{name}: {silent}", retryable=False, slow=True) from None
        if kind == "cancel":
            _close(response)
            raise LLMError(f"{name}: cancelled", retryable=False)
        if kind == "end":
            return
        if kind == "broke":
            # A break that came fast is asked again, like any other fast failure.
            raise LLMError(f"{name}: the stream broke: {value}") from value  # type: ignore[misc]
        yield value  # type: ignore[misc]
        wait = IDLE_SECONDS
        silent = f"the answer stopped for {IDLE_SECONDS:.0f}s"


def join_openai(pieces: Iterator[dict]) -> dict:
    """The OpenAI chat body that the pieces add up to."""
    text: list[str] = []
    calls: dict[int, dict] = {}
    body: dict = {}
    finish = UNFINISHED
    for piece in pieces:
        if piece.get("error"):
            # Without `choices`, so _error_inside reads it as it reads a plain
            # body. A gateway can send half an answer and then an error.
            return {"error": piece["error"]}
        body["model"] = piece.get("model") or body.get("model")
        if piece.get("usage"):
            body["usage"] = piece["usage"]
        for choice in piece.get("choices") or []:
            delta = choice.get("delta") or {}
            if isinstance(delta.get("content"), str):
                text.append(delta["content"])
            for call in delta.get("tool_calls") or []:
                slot = calls.setdefault(
                    call.get("index", 0), {"function": {"name": "", "arguments": ""}}
                )
                function = call.get("function") or {}
                slot["function"]["name"] += function.get("name") or ""
                slot["function"]["arguments"] += function.get("arguments") or ""
            finish = choice.get("finish_reason") or finish
    message: dict = {"content": "".join(text)}
    if calls:
        message["tool_calls"] = [calls[i] for i in sorted(calls)]
    if finish == UNFINISHED:
        raise LLMError("the stream ended before the answer did")
    body["choices"] = [{"message": message, "finish_reason": finish}]
    return body


def join_gemini(pieces: Iterator[dict]) -> dict:
    """The Gemini body that the pieces add up to (thought parts left out)."""
    parts: list[dict] = []
    body: dict = {}
    finish = UNFINISHED
    for piece in pieces:
        if "error" in piece:
            # Google can answer 200, send some pieces and THEN fail (a 503 in the
            # middle, measured 2026-11-23). The status is kept, so the chain
            # treats it as the same 503 on a plain call.
            error = piece["error"]
            status = error.get("code") if isinstance(error, dict) else None
            raise LLMError(
                f"Gemini stream error: {truncate(str(error))}",
                status=status if isinstance(status, int) else None,
            )
        for key in ("modelVersion", "usageMetadata", "promptFeedback"):
            if key in piece:
                body[key] = piece[key]
        for candidate in piece.get("candidates") or []:
            for part in (candidate.get("content") or {}).get("parts") or []:
                if part.get("thought"):
                    continue
                if "text" in part and parts and "text" in parts[-1]:
                    parts[-1] = {"text": parts[-1]["text"] + part["text"]}
                else:
                    parts.append(dict(part))
            finish = candidate.get("finishReason") or finish
    if finish == UNFINISHED and not body.get("promptFeedback", {}).get("blockReason"):
        raise LLMError("the stream ended before the answer did")
    if finish != UNFINISHED:
        body["candidates"] = [{"content": {"parts": parts}, "finishReason": finish}]
    return body

from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import requests

from labpilot._text import truncate
from labpilot.llm._calls import json_fallback, read_object
from labpilot.llm._http import error_from_response
from labpilot.llm._rooms import with_margin
from labpilot.llm._stream import IDLE_SECONDS, events, first_piece_limit, open_stream
from labpilot.llm.contracts import LLMResult, Tool
from labpilot.llm.defaults import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT,
)
from labpilot.llm.errors import LLMError
from labpilot.tokens import estimate_tokens

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, kw_only=True)
class HTTPProvider(ABC):
    name: str
    tier: int
    url: str
    model: str
    api_key_env: str
    context_window: int
    max_output_tokens: int
    max_input_tokens: int | None = None
    quota_pool: str | None = None
    timeout: tuple[float, float] = DEFAULT_TIMEOUT
    temperature: float = DEFAULT_TEMPERATURE
    # Seconds the ACCOUNT must rest between two calls, across every model on it.
    # Zero for nearly everyone; LiteRouter enforces 7 and answers 403 otherwise.
    seconds_between_calls: float = 0.0
    # Seconds the ACCOUNT is quiet AFTER a call ends (LiteRouter: a 403 came 0 s
    # after a call that had ended, measured 2026-11-16).
    seconds_after_call: float = 0.0
    # How many calls of this ACCOUNT may be open at once (None = no limit).
    # LiteRouter and Requesty allow one; the rest allow as many as we send.
    max_concurrent: int | None = None
    # Requests a minute that this quota POOL takes (None = not limited, or not
    # known). The matching limit on input tokens is `max_input_tokens`. Both are
    # booked by the chain before the call, see _rooms.py.
    requests_per_minute: int | None = None
    # Ask for the answer in pieces, so a tier that stopped writing is found in
    # seconds (_stream.py). False for a provider whose stream we cannot read.
    stream: bool = True

    @property
    def pool(self) -> str:
        return self.quota_pool or self.api_key_env

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        tool: Tool | None = None,
    ) -> LLMResult:
        if not prompt.strip():
            raise ValueError("prompt must not be empty")

        if tool is not None:
            prompt = f"{prompt}\n\n{json_fallback(tool)}"

        self._check_fits(prompt, max_tokens)
        # A call that is refused locally sends nothing, so it must not use up
        # the account's turn. A missing key is the case that would hurt: every
        # tier on that gateway would rest 8 seconds before failing the same way.
        self._api_key()
        # The rest between calls, the calls open at once and the minute rooms are
        # kept by the chain BEFORE it calls (chain.py), because they decide
        # whether to call this tier at all or to go on to the next one.

        payload = self._payload(prompt, max_tokens, tool)
        endpoint = self._endpoint()
        timeout = self.timeout
        if self.stream:
            payload = self._stream_payload(payload)
            endpoint = self._stream_endpoint(endpoint)
            # requests' read timeout is the longest gap between two bytes. The
            # shorter waits (headers, first piece, silence) are in _stream.py.
            timeout = (self.timeout[0], max(first_piece_limit.get(), IDLE_SECONDS))
        headers = self._headers()

        def post() -> requests.Response:
            return requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=timeout,
                stream=self.stream,
            )

        started = time.monotonic()
        try:
            response = open_stream(post, self.name) if self.stream else post()
        except requests.exceptions.RequestException as exc:
            raise LLMError(f"{self.name}: request failed: {exc}") from exc

        if response.status_code != 200:
            raise error_from_response(response, self.name)

        streamed = self.stream and "text/event-stream" in response.headers.get(
            "content-type", ""
        )
        if streamed:
            body = self._join(events(response, self.name, started=started))
        else:
            try:
                body = response.json()
            except ValueError as exc:
                raise LLMError(
                    f"{self.name}: response was not JSON: {truncate(response.text)}"
                ) from exc

        if tool is not None:
            call = self._extract_call(body, tool)
            if call is not None:
                arguments, served_model, finish_reason = call
                return self._result(
                    json.dumps(arguments), served_model, finish_reason, body, arguments
                )
        text, served_model, finish_reason = self._extract_message(body)
        arguments = read_object(text, self.name) if tool is not None else None

        return self._result(text, served_model, finish_reason, body, arguments)

    def _result(
        self,
        text: str,
        served_model: str,
        finish_reason: str,
        body: dict,
        arguments: dict[str, object] | None,
    ) -> LLMResult:

        logger.info(
            "tier %d served by %s (finish_reason=%s, %d chars, %s)",
            self.tier,
            served_model,
            finish_reason,
            len(text),
            self._usage_summary(body),
        )

        return LLMResult(
            text=text,
            model=served_model,
            tier=self.tier,
            finish_reason=finish_reason,
            arguments=arguments,
        )

    def _check_fits(self, prompt: str, max_tokens: int) -> None:
        if max_tokens > self.max_output_tokens:
            raise LLMError(
                f"{self.name}: max_tokens {max_tokens} exceeds the output limit "
                f"{self.max_output_tokens}",
                retryable=False,
            )

        estimate = estimate_tokens(prompt)
        padded = with_margin(estimate)

        if self.max_input_tokens is not None and padded > self.max_input_tokens:
            raise LLMError(
                f"{self.name}: prompt needs ~{padded} input tokens but the "
                f"per-minute input limit is {self.max_input_tokens}",
                retryable=False,
            )

        required = padded + max_tokens

        if required > self.context_window:
            raise LLMError(
                f"{self.name}: prompt needs ~{required} tokens "
                f"(~{estimate} prompt + {max_tokens} output + margin) "
                f"but the context window is {self.context_window}",
                retryable=False,
            )

    def _api_key(self) -> str:
        key = os.environ.get(self.api_key_env, "").strip()
        if not key:
            raise LLMError(
                f"{self.name}: {self.api_key_env} is not set", retryable=False
            )
        return key

    @abstractmethod
    def _endpoint(self) -> str: ...

    def _stream_payload(self, payload: dict[str, object]) -> dict[str, object]:
        return {**payload, "stream": True}

    def _stream_endpoint(self, endpoint: str) -> str:
        return endpoint

    def _join(self, pieces) -> dict:
        raise NotImplementedError

    @abstractmethod
    def _headers(self) -> dict[str, str]: ...

    @abstractmethod
    def _payload(
        self, prompt: str, max_tokens: int, tool: Tool | None = None
    ) -> dict[str, object]: ...

    def _extract_call(
        self, body: dict, tool: Tool
    ) -> tuple[dict[str, object], str, str] | None:
        return None

    @abstractmethod
    def _extract_message(self, body: dict) -> tuple[str, str, str]: ...

    @abstractmethod
    def _usage_summary(self, body: dict) -> str: ...

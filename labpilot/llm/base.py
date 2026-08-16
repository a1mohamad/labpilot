from __future__ import annotations

import logging
import math
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

import requests

from labpilot.llm._http import error_from_response
from labpilot.llm._text import truncate
from labpilot.llm.contracts import LLMResult
from labpilot.llm.defaults import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT,
    SAFETY_MARGIN_RATIO,
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

    @property
    def pool(self) -> str:
        return self.quota_pool or self.api_key_env

    def complete(
        self, prompt: str, *, max_tokens: int = DEFAULT_MAX_TOKENS
    ) -> LLMResult:
        if not prompt.strip():
            raise ValueError("prompt must not be empty")

        self._check_fits(prompt, max_tokens)

        try:
            response = requests.post(
                self._endpoint(),
                headers=self._headers(),
                json=self._payload(prompt, max_tokens),
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise LLMError(f"{self.name}: request failed: {exc}") from exc

        if response.status_code != 200:
            raise error_from_response(response, self.name)

        try:
            body = response.json()
        except ValueError as exc:
            raise LLMError(
                f"{self.name}: response was not JSON: {truncate(response.text)}"
            ) from exc

        text, served_model, finish_reason = self._extract_message(body)

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
        )

    def _check_fits(self, prompt: str, max_tokens: int) -> None:
        if max_tokens > self.max_output_tokens:
            raise LLMError(
                f"{self.name}: max_tokens {max_tokens} exceeds the output limit "
                f"{self.max_output_tokens}"
            )

        estimate = estimate_tokens(prompt)
        padded = math.ceil(estimate * (1 + SAFETY_MARGIN_RATIO))

        if self.max_input_tokens is not None and padded > self.max_input_tokens:
            raise LLMError(
                f"{self.name}: prompt needs ~{padded} input tokens but the "
                f"per-minute input limit is {self.max_input_tokens}"
            )

        required = padded + max_tokens

        if required > self.context_window:
            raise LLMError(
                f"{self.name}: prompt needs ~{required} tokens "
                f"(~{estimate} prompt + {max_tokens} output + margin) "
                f"but the context window is {self.context_window}"
            )

    def _api_key(self) -> str:
        key = os.environ.get(self.api_key_env, "").strip()
        if not key:
            raise LLMError(f"{self.name}: {self.api_key_env} is not set")
        return key

    @abstractmethod
    def _endpoint(self) -> str: ...

    @abstractmethod
    def _headers(self) -> dict[str, str]: ...

    @abstractmethod
    def _payload(self, prompt: str, max_tokens: int) -> dict[str, object]: ...

    @abstractmethod
    def _extract_message(self, body: dict) -> tuple[str, str, str]: ...

    @abstractmethod
    def _usage_summary(self, body: dict) -> str: ...

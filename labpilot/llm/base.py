from __future__ import annotations

import logging
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
)
from labpilot.llm.errors import LLMError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, kw_only=True)
class HTTPProvider(ABC):
    name: str
    tier: int
    url: str
    model: str
    api_key_env: str
    timeout: tuple[float, float] = DEFAULT_TIMEOUT
    temperature: float = DEFAULT_TEMPERATURE

    def complete(
        self, prompt: str, *, max_tokens: int = DEFAULT_MAX_TOKENS
    ) -> LLMResult:
        if not prompt.strip():
            raise ValueError("prompt must not be empty")

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

        return LLMResult(text=text, model=served_model, tier=self.tier)

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

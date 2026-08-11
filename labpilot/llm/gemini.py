from __future__ import annotations

import logging
import os
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


def _extract_message(body: dict, source: str) -> tuple[str, str, str]:
    try:
        candidates = body.get("candidates") or []
        if not candidates:
            block_reason = (body.get("promptFeedback") or {}).get(
                "blockReason", "no candidates returned"
            )
            raise LLMError(f"{source}: prompt was blocked: {block_reason}")

        candidate = candidates[0]
        finish_reason = candidate.get("finishReason", "unknown")
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(part.get("text", "") for part in parts)

    except (AttributeError, KeyError, IndexError, TypeError) as exc:
        raise LLMError(
            f"{source}: unexpected response shape: {truncate(str(body))}"
        ) from exc
    text = text.strip()
    if not text:
        raise LLMError(f"{source}: returned an empty answer ({finish_reason})")

    return text, body.get("modelVersion") or source, finish_reason


@dataclass(frozen=True, slots=True, kw_only=True)
class GeminiProvider:
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

        text, served_model, finish_reason = _extract_message(body, self.name)
        usage = body.get("usageMetadata", {})

        logger.info(
            "tier %d served by %s (finish_reason=%s, %d chars, "
            "%s in / %s out / %s thought tokens)",
            self.tier,
            served_model,
            finish_reason,
            len(text),
            usage.get("promptTokenCount", "?"),
            usage.get("candidatesTokenCount", "?"),
            usage.get("thoughtsTokenCount", "?"),
        )

        return LLMResult(text=text, model=served_model, tier=self.tier)

    def _api_key(self) -> str:
        key = os.environ.get(self.api_key_env, "").strip()
        if not key:
            raise LLMError(f"{self.name}: {self.api_key_env} is not set")
        return key

    def _endpoint(self) -> str:
        return f"{self.url}/{self.model}:generateContent"

    def _headers(self) -> dict[str, str]:
        return {
            "x-goog-api-key": self._api_key(),
            "Content-Type": "application/json",
        }

    def _payload(self, prompt: str, max_tokens: int) -> dict[str, object]:
        return {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": self.temperature,
            },
        }

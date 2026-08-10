from __future__ import annotations

from dataclasses import dataclass
import logging
import os

import requests

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
        choice = body["choices"][0]
        text = choice["message"]["content"]
        finish_reason = choice.get("finish_reason", "unknown")

    except(KeyError, IndexError, TypeError) as exc:
        raise LLMError(
            f"{source}: unexpected response shape: {truncate(str(body))}"
        ) from exc

    text = (text or "").strip()
    if not text:
        raise LLMError(
            f"{source}: returned an empty answer"
        )

    return text, body.get("model") or source, finish_reason

@dataclass(frozen=True, slots=True, kw_only=True)
class OpenAICompatibleProvider:
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
                self.url,
                headers=self._headers(),
                json=self._payload(prompt, max_tokens),
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise LLMError(
                f"{self.name}: request failed: {exc}"
            ) from exc

        if response.status_code != 200:
            raise LLMError(
                f"{self.name}: HTTP {response.status_code}: {truncate(response.text)}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise LLMError(
                f"{self.name}: response was not JSON: {truncate(response.text)}"
            ) from exc

        text, served_model, finish_reason = _extract_message(body, self.name)
        usage = body.get("usage", {})

        logger.info(
            "tier %d served by %s (finish_reason=%s, %d chars, %s in / %s out tokens)",
            self.tier,
            served_model,
            finish_reason,
            len(text),
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
        )

        return LLMResult(text=text, model=served_model, tier=self.tier)

    def _api_key(self) -> str:
        key = os.environ.get(self.api_key_env, "").strip()
        if not key:
            raise LLMError(
                f"{self.name}: {self.api_key_env} is not set"
            )
        return key

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
        }

    def _payload(self, prompt: str, max_tokens: int) -> dict[str, object]:
        return {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": self.temperature,
        }
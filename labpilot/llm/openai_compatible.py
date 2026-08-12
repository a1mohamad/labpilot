from __future__ import annotations

import os
from dataclasses import dataclass

from labpilot.llm._text import truncate
from labpilot.llm.base import HTTPProvider
from labpilot.llm.errors import LLMError


@dataclass(frozen=True, slots=True, kw_only=True)
class OpenAICompatibleProvider(HTTPProvider):
    account_env: str | None = None

    def _endpoint(self) -> str:
        if self.account_env is None:
            return self.url

        account_id = os.environ.get(self.account_env, "").strip()
        if not account_id:
            raise LLMError(f"{self.name}: {self.account_env} is not set")
        return self.url.format(account_id=account_id)

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

    def _extract_message(self, body: dict) -> tuple[str, str, str]:
        try:
            choice = body["choices"][0]
            text = choice["message"]["content"]
            finish_reason = choice.get("finish_reason", "unknown")

        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(
                f"{self.name}: unexpected response shape: {truncate(str(body))}"
            ) from exc

        text = (text or "").strip()
        if not text:
            raise LLMError(f"{self.name}: returned an empty answer")

        return text, body.get("model") or self.name, finish_reason

    def _usage_summary(self, body: dict) -> str:
        usage = body.get("usage", {})
        return (
            f"{usage.get('prompt_tokens', '?')} in / "
            f"{usage.get('completion_tokens', '?')} out tokens"
        )

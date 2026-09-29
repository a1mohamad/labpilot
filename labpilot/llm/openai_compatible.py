from __future__ import annotations

import os
from dataclasses import dataclass

from labpilot._text import truncate
from labpilot.llm._http import rate_limit_ceiling, reset_at_epoch, retry_after_seconds
from labpilot.llm.base import HTTPProvider
from labpilot.llm.errors import LLMError

_FIRST_ERROR_STATUS = 400
_LAST_ERROR_STATUS = 599


def _status_of(code: object) -> int | None:
    try:
        value = int(code)
    except (TypeError, ValueError):
        return None
    return value if _FIRST_ERROR_STATUS <= value <= _LAST_ERROR_STATUS else None


def _error_inside(body: dict, source: str) -> LLMError | None:
    # A gateway that accepted the request and then failed upstream can answer
    # HTTP 200 with the failure in the BODY. Measured 2026-09-30, Nemotron 3
    # through Kilo, 2 calls in 6:
    #
    #   200 {"error": {"message": "Upstream error from Nvidia: Service
    #        temporarily overloaded", "code": 503, "metadata": {...}}}
    #
    # Read as a normal reply it has no `choices`, so it was reported as
    # "unexpected response shape" with the message cut off. Two things were
    # lost: the REASON, and the STATUS - a 503 is retried on the same tier by
    # the chain, but only an LLMError that carries status=503 can be.
    error = body.get("error")
    if body.get("choices") or not error:
        return None

    headers: dict[str, str] = {}
    code = None
    if isinstance(error, dict):
        message = error.get("message") or error.get("type") or "no message"
        code = _status_of(error.get("code"))
        metadata = error.get("metadata")
        raw = metadata.get("headers") if isinstance(metadata, dict) else None
        if isinstance(raw, dict):
            headers = {str(key): str(value) for key, value in raw.items()}
    else:
        message = error

    label = f" ({code})" if code else ""
    return LLMError(
        f"{source}: HTTP 200 carried an error{label}: {truncate(str(message))}",
        status=code,
        retry_after=retry_after_seconds(headers),
        reset_at=reset_at_epoch(headers),
        rate_limit=rate_limit_ceiling(headers),
    )


def _visible_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    return "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class OpenAICompatibleProvider(HTTPProvider):
    account_env: str | None = None
    extra_body: dict[str, object] | None = None

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
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": self.temperature,
        }
        if self.extra_body:
            payload.update(self.extra_body)

        return payload

    def _extract_message(self, body: dict) -> tuple[str, str, str]:
        hidden = _error_inside(body, self.name) if isinstance(body, dict) else None
        if hidden is not None:
            raise hidden

        try:
            choice = body["choices"][0]
            text = _visible_text(choice["message"]["content"])
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
        details = usage.get("completion_tokens_details") or {}
        return (
            f"{usage.get('prompt_tokens', '?')} in / "
            f"{usage.get('completion_tokens', '?')} out / "
            f"{details.get('reasoning_tokens', '?')} reasoning tokens"
        )

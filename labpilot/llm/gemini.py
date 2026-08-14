from __future__ import annotations

from dataclasses import dataclass

from labpilot.llm._text import truncate
from labpilot.llm.base import HTTPProvider
from labpilot.llm.errors import LLMError


@dataclass(frozen=True, slots=True, kw_only=True)
class GeminiProvider(HTTPProvider):
    thinking: str | None = None

    def _endpoint(self) -> str:
        return f"{self.url}/{self.model}:generateContent"

    def _headers(self) -> dict[str, str]:
        return {
            "x-goog-api-key": self._api_key(),
            "Content-Type": "application/json",
        }

    def _payload(self, prompt: str, max_tokens: int) -> dict[str, object]:
        config: dict[str, object] = {
            "maxOutputTokens": max_tokens,
            "temperature": self.temperature,
        }
        if self.thinking:
            config["thinkingConfig"] = {"thinkingLevel": self.thinking}

        return {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": config,
        }

    def _extract_message(self, body: dict) -> tuple[str, str, str]:
        try:
            candidates = body.get("candidates") or []
            if not candidates:
                block_reason = (body.get("promptFeedback") or {}).get(
                    "blockReason", "no candidates returned"
                )
                raise LLMError(f"{self.name}: prompt was blocked: {block_reason}")

            candidate = candidates[0]
            finish_reason = candidate.get("finishReason", "unknown")
            parts = (candidate.get("content") or {}).get("parts") or []
            text = "".join(part.get("text", "") for part in parts)

        except (AttributeError, KeyError, IndexError, TypeError) as exc:
            raise LLMError(
                f"{self.name}: unexpected response shape: {truncate(str(body))}"
            ) from exc

        text = text.strip()
        if not text:
            raise LLMError(f"{self.name}: returned an empty answer ({finish_reason})")

        return text, body.get("modelVersion") or self.name, finish_reason

    def _usage_summary(self, body: dict) -> str:
        usage = body.get("usageMetadata", {})
        return (
            f"{usage.get('promptTokenCount', '?')} in / "
            f"{usage.get('candidatesTokenCount', '?')} out / "
            f"{usage.get('thoughtsTokenCount', '?')} thought tokens"
        )

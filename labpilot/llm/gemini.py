from __future__ import annotations

from dataclasses import dataclass

from labpilot._text import truncate
from labpilot.llm._calls import read_arguments
from labpilot.llm.base import HTTPProvider
from labpilot.llm.contracts import Tool
from labpilot.llm.errors import LLMError


def _upper_types(schema: object) -> object:
    # Gemini's schema dialect is not JSON Schema: "string" is refused and
    # "STRING" is accepted (measured by scripts/probe_tools.py). Only the VALUE
    # of a "type" key changes, so a property that is itself called "type" stays.
    if isinstance(schema, dict):
        return {
            key: value.upper()
            if key == "type" and isinstance(value, str)
            else _upper_types(value)
            for key, value in schema.items()
        }
    if isinstance(schema, list):
        return [_upper_types(item) for item in schema]
    return schema


@dataclass(frozen=True, slots=True, kw_only=True)
class GeminiProvider(HTTPProvider):
    thinking: str | None = None
    generation_config: dict[str, object] | None = None

    def _endpoint(self) -> str:
        return f"{self.url}/{self.model}:generateContent"

    def _headers(self) -> dict[str, str]:
        return {
            "x-goog-api-key": self._api_key(),
            "Content-Type": "application/json",
        }

    def _payload(
        self, prompt: str, max_tokens: int, tool: Tool | None = None
    ) -> dict[str, object]:
        config: dict[str, object] = {
            "maxOutputTokens": max_tokens,
            "temperature": self.temperature,
        }
        if self.thinking:
            config["thinkingConfig"] = {"thinkingLevel": self.thinking}
        # The Gemini-shape twin of OpenAICompatibleProvider.extra_body, and it
        # exists for a measured reason: structured output. Asking gemma-4-31b
        # for a JSON array instead of free text took one 30-document ranking
        # from 45.5s to 14.4s and removed the parsing risk entirely, because
        # the model stops writing prose around its answer.
        #
        # Step 2 needs it for its own reasons - CLAUDE.md's claim extraction
        # says "output a fixed shape (JSON) so the next node parses instead of
        # guessing" - so this is a scheduled consumer, not speculation.
        if self.generation_config:
            config.update(self.generation_config)

        payload: dict[str, object] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": config,
        }
        if tool is not None:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": _upper_types(tool.parameters),
                        }
                    ]
                }
            ]

        return payload

    def _extract_call(
        self, body: dict, tool: Tool
    ) -> tuple[dict[str, object], str, str] | None:
        try:
            candidate = body["candidates"][0]
            parts = (candidate.get("content") or {}).get("parts") or []
            calls = [part["functionCall"] for part in parts if "functionCall" in part]
        except (AttributeError, IndexError, KeyError, TypeError):
            return None
        if not calls:
            return None

        if calls[0].get("name") != tool.name:
            raise LLMError(
                f"{self.name}: called {calls[0].get('name')!r}, not {tool.name!r}"
            )

        arguments = read_arguments(calls[0].get("args") or {}, self.name)

        return (
            arguments,
            body.get("modelVersion") or self.name,
            candidate.get("finishReason", "unknown"),
        )

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

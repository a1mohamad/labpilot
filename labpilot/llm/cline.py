from __future__ import annotations

from dataclasses import dataclass

from labpilot._text import truncate
from labpilot.llm.errors import LLMError
from labpilot.llm.openai_compatible import OpenAICompatibleProvider


@dataclass(frozen=True, slots=True, kw_only=True)
class ClineProvider(OpenAICompatibleProvider):
    """Cline speaks the OpenAI REQUEST shape and its own RESPONSE shape.

    Everything we send is standard: model, messages, max_tokens, temperature,
    and a Bearer key. Everything we read back is wrapped one level deeper::

        {"data": {"choices": [...], "usage": {...}}, "success": true}

    So only the two reading methods change. Measured live 2026-09-13 - the
    inherited `_extract_message` reads body["choices"] and raises
    "unexpected response shape" on every single call.
    """

    def _inner(self, body: dict) -> dict:
        """The envelope, or a loud error naming what we actually got."""
        if not isinstance(body, dict):
            raise LLMError(
                f"{self.name}: unexpected response shape: {truncate(str(body))}"
            )

        inner = body.get("data")
        if not isinstance(inner, dict):
            raise LLMError(
                f"{self.name}: response is missing the data envelope: "
                f"{truncate(str(body))}"
            )

        return inner

    def _extract_message(self, body: dict) -> tuple[str, str, str]:
        # Explicit rather than zero-argument super(): `slots=True` makes the
        # decorator build a NEW class, so the implicit __class__ cell points at
        # a class that is no longer in the MRO.
        return OpenAICompatibleProvider._extract_message(self, self._inner(body))

    def _usage_summary(self, body: dict) -> str:
        # Deliberately tolerant where _extract_message is strict: this only
        # builds a log line, and losing the log must never fail a good answer.
        inner = body.get("data") if isinstance(body.get("data"), dict) else body
        base = OpenAICompatibleProvider._usage_summary(self, inner)

        # `cost` is the number to watch. Cline records what a free model WOULD
        # have cost and charges zero credits for it, so the day the promotion
        # ends this stops being free and the log is where it shows first.
        cost = (inner.get("usage") or {}).get("cost")

        return f"{base} / cost {cost}"

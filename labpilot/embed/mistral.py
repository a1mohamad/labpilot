from __future__ import annotations

from dataclasses import dataclass

from labpilot.embed.base import HTTPEmbedder
from labpilot.embed.contracts import Task, Vector


@dataclass(frozen=True, slots=True, kw_only=True)
class MistralEmbedder(HTTPEmbedder):
    api_key_env: str = "MISTRAL_API_KEY"

    def _endpoint(self) -> str:
        return self.url

    def _headers(self) -> dict[str, str]:
        return self._bearer_headers()

    def _payload(self, texts: list[str], task: Task) -> dict[str, object]:
        return {"model": self.model, "input": texts}

    def _raw_vectors(self, body: dict) -> list[Vector]:
        ordered = sorted(body["data"], key=lambda item: item["index"])
        return [tuple(float(value) for value in item["embedding"]) for item in ordered]

    def _prompt_tokens(self, body: dict) -> int:
        usage = body.get("usage")
        return usage.get("prompt_tokens", 0) if isinstance(usage, dict) else 0

    def _served_model(self, body: dict) -> str:
        return str(body.get("model") or self.model)

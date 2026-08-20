from __future__ import annotations

from dataclasses import dataclass

from labpilot.embed.base import HTTPEmbedder
from labpilot.embed.contracts import Task, Vector
from labpilot.embed.errors import EmbeddingError


@dataclass(frozen=True, slots=True, kw_only=True)
class CloudflareEmbedder(HTTPEmbedder):
    api_key_env: str = "CLOUDFLARE_API_KEY"
    account_env: str | None = "CLOUDFLARE_ACCOUNT_ID"

    def _endpoint(self) -> str:
        return f"{self.url}/{self._account_id()}/ai/run/{self.model}"

    def _headers(self) -> dict[str, str]:
        return self._bearer_headers()

    def _payload(self, texts: list[str], task: Task) -> dict[str, object]:
        return {"text": texts}

    def _raw_vectors(self, body: dict) -> list[Vector]:
        if not body.get("success", True):
            raise EmbeddingError(
                f"{self.name}: the response reports failure: {body.get('errors')}"
            )

        result = body["result"]
        data = result["data"]
        rows = result["shape"][0]

        if rows != len(data):
            raise EmbeddingError(
                f"{self.name}: shape says {rows} vectors but data holds {len(data)}"
            )

        return [tuple(float(value) for value in row) for row in data]

    def _prompt_tokens(self, body: dict) -> int:
        usage = body["result"].get("usage")
        return usage.get("prompt_tokens", 0) if isinstance(usage, dict) else 0

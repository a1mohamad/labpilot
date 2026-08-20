from __future__ import annotations

from dataclasses import dataclass

from labpilot.embed.base import HTTPEmbedder
from labpilot.embed.contracts import Task, Vector

INPUT_TYPES: dict[Task, str] = {
    "query": "search_query",
    "document": "search_document",
}


@dataclass(frozen=True, slots=True, kw_only=True)
class CohereEmbedder(HTTPEmbedder):
    api_key_env: str = "COHERE_API_KEY"

    def _endpoint(self) -> str:
        return self.url

    def _headers(self) -> dict[str, str]:
        return self._bearer_headers()

    def _payload(self, texts: list[str], task: Task) -> dict[str, object]:
        return {
            "model": self.model,
            "texts": texts,
            "input_type": INPUT_TYPES[task],
            "embedding_types": ["float"],
        }

    def _raw_vectors(self, body: dict) -> list[Vector]:
        return [
            tuple(float(value) for value in row) for row in body["embeddings"]["float"]
        ]

    def _prompt_tokens(self, body: dict) -> int:
        billed = body["meta"]["billed_units"]
        return int(billed.get("input_tokens", 0))

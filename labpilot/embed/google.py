from __future__ import annotations

from dataclasses import dataclass

from labpilot.embed.base import HTTPEmbedder
from labpilot.embed.contracts import Pace, Task, Vector
from labpilot.embed.defaults import (
    GOOGLE_MAX_BATCH_SIZE,
    GOOGLE_TEXTS_PER_MINUTE,
    GOOGLE_TOKENS_PER_MINUTE,
)

TASK_TYPES: dict[Task, str] = {
    "query": "RETRIEVAL_QUERY",
    "document": "RETRIEVAL_DOCUMENT",
}


@dataclass(frozen=True, slots=True, kw_only=True)
class GoogleEmbedder(HTTPEmbedder):
    api_key_env: str = "GOOGLE_API_KEY"
    max_batch_size: int = GOOGLE_MAX_BATCH_SIZE
    # Google ENFORCES both, unlike Mistral - a second 40-text batch inside one
    # minute was refused. Every Google model shares the shape; each has its
    # own bucket, which `pool` keeps apart.
    pace: Pace | None = Pace(
        tokens_per_minute=GOOGLE_TOKENS_PER_MINUTE,
        texts_per_minute=GOOGLE_TEXTS_PER_MINUTE,
    )

    def _endpoint(self) -> str:
        return f"{self.url}/{self.model}:batchEmbedContents"

    def _headers(self) -> dict[str, str]:
        return {
            "x-goog-api-key": self._api_key(),
            "Content-Type": "application/json",
        }

    def _payload(self, texts: list[str], task: Task) -> dict[str, object]:
        # Each text needs its own request object. Passing several inputs to one
        # request returns ONE aggregated vector, verified live 2026-08-11.
        return {
            "requests": [
                {
                    "model": f"models/{self.model}",
                    "content": {"parts": [{"text": text}]},
                    "taskType": TASK_TYPES[task],
                }
                for text in texts
            ]
        }

    def _raw_vectors(self, body: dict) -> list[Vector]:
        return [
            tuple(float(value) for value in item["values"])
            for item in body["embeddings"]
        ]

    def _prompt_tokens(self, body: dict) -> int:
        # batchEmbedContents reports no usage block. Zero is the honest answer,
        # not a guess.
        return 0

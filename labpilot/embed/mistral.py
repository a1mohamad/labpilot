from __future__ import annotations

import logging
import math
import os
from collections.abc import Sequence
from dataclasses import dataclass

import requests

from labpilot._text import truncate
from labpilot.embed.contracts import EmbeddingBatch, Vector
from labpilot.embed.defaults import DEFAULT_TIMEOUT, MAX_BATCH_SIZE
from labpilot.embed.errors import EmbeddingError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, kw_only=True)
class MistralEmbedder:
    name: str
    url: str
    model: str
    dim: int
    api_key_env: str = "MISTRAL_API_KEY"
    timeout: tuple[float, float] = DEFAULT_TIMEOUT

    def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        self._check_texts(texts)
        headers = self._headers()

        try:
            response = requests.post(
                url=self.url,
                headers=headers,
                json={"model": self.model, "input": list(texts)},
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise EmbeddingError(f"{self.name}: request failed: {exc}") from exc

        if response.status_code != 200:
            raise EmbeddingError(
                f"{self.name}: HTTP {response.status_code}: {truncate(response.text)}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise EmbeddingError(
                f"{self.name}: response was not JSON: {truncate(response.text)}"
            ) from exc

        vectors = self._vectors(body, expected=len(texts))
        usage = body.get("usage")
        prompt_tokens = usage.get("prompt_tokens", 0) if isinstance(usage, dict) else 0

        logger.info(
            "%s embedded %d texts (%d dim, %d prompt tokens)",
            self.model,
            len(texts),
            self.dim,
            prompt_tokens,
        )

        return EmbeddingBatch(
            vectors=vectors,
            model=str(body.get("model") or self.model),
            dim=self.dim,
            prompt_tokens=prompt_tokens,
        )

    def _check_texts(self, texts=Sequence[str]) -> None:
        if not texts:
            raise ValueError("texts must not be empty")

        if len(texts) > MAX_BATCH_SIZE:
            raise ValueError(
                f"{len(texts)} texts is over the batch limit of {MAX_BATCH_SIZE}; "
                "the caller owns the loop"
            )

        blank = [position for position, text in enumerate(texts) if not text.strip()]
        if blank:
            raise ValueError(f"texts must not be blank, found at {blank[:3]}")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
        }

    def _api_key(self) -> str:
        key = os.environ.get(self.api_key_env, "").strip()
        if not key:
            raise EmbeddingError(f"{self.name}: {self.api_key_env} is not set")
        return key

    def _vectors(self, body: dict, *, expected: int) -> tuple[Vector, ...]:
        try:
            ordered = sorted(body["data"], key=lambda item: item["index"])
            raw = [
                tuple(float(value) for value in item["embedding"]) for item in ordered
            ]
        except (TypeError, ValueError, AttributeError, KeyError) as exc:
            raise EmbeddingError(
                f"{self.name}: unexpected response shape: {truncate(str(body))}"
            ) from exc

        if len(raw) != expected:
            raise EmbeddingError(
                f"{self.name}: asked for {expected} vectors but got {len(raw)}"
            )

        wrong = [len(vector) for vector in raw if len(vector) != self.dim]
        if wrong:
            raise EmbeddingError(
                f"{self.name}: expected {self.dim} dimensions, got {wrong[:3]}"
            )

        return tuple(self._unit(vector) for vector in raw)

    def _unit(self, vector: Vector) -> Vector:
        length = math.sqrt(sum(value * value for value in vector))
        if length == 0.0:
            raise EmbeddingError(f"{self.name}: a zero vector cannot be normalized")
        return tuple(value / length for value in vector)

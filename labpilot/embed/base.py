from __future__ import annotations

import logging
import math
import os
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

import requests

from labpilot._text import truncate
from labpilot.embed.contracts import EmbeddingBatch, Task, Vector
from labpilot.embed.defaults import DEFAULT_TIMEOUT, MAX_BATCH_SIZE
from labpilot.embed.errors import EmbeddingError
from labpilot.tokens import estimate_tokens

logger = logging.getLogger(__name__)

SHAPE_ERRORS = (KeyError, TypeError, ValueError, AttributeError, IndexError)


@dataclass(frozen=True, slots=True, kw_only=True)
class HTTPEmbedder(ABC):
    name: str
    url: str
    model: str
    dim: int
    api_key_env: str
    account_env: str | None = None
    max_input_tokens: int | None = None
    timeout: tuple[float, float] = DEFAULT_TIMEOUT

    def embed(self, texts: Sequence[str], *, task: Task = "document") -> EmbeddingBatch:
        self._check_texts(texts)

        headers = self._headers()
        endpoint = self._endpoint()

        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=self._payload(list(texts), task),
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

        try:
            raw = self._raw_vectors(body)
            prompt_tokens = self._prompt_tokens(body)
        except SHAPE_ERRORS as exc:
            raise EmbeddingError(
                f"{self.name}: unexpected response shape: {truncate(str(body))}"
            ) from exc

        vectors = self._validated(raw, expected=len(texts))

        logger.info(
            "%s embedded %d texts (%d dim, %d prompt tokens)",
            self.model,
            len(vectors),
            self.dim,
            prompt_tokens,
        )

        return EmbeddingBatch(
            vectors=vectors,
            model=self._served_model(body),
            dim=self.dim,
            prompt_tokens=prompt_tokens,
        )

    def _check_texts(self, texts: Sequence[str]) -> None:
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

        if self.max_input_tokens is None:
            return

        over = [
            (position, estimate_tokens(text))
            for position, text in enumerate(texts)
            if estimate_tokens(text) > self.max_input_tokens
        ]
        if over:
            raise EmbeddingError(
                f"{self.name}: {len(over)} text(s) exceed the {self.max_input_tokens} "
                f"token input limit and would be silently truncated: {over[:3]}"
            )

    def _validated(self, raw: list[Vector], *, expected: int) -> tuple[Vector, ...]:
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

    def _api_key(self) -> str:
        return self._required(self.api_key_env)

    def _account_id(self) -> str:
        if self.account_env is None:
            raise EmbeddingError(f"{self.name}: no account_env is configured")
        return self._required(self.account_env)

    def _required(self, name: str) -> str:
        value = os.environ.get(name, "").strip()
        if not value:
            raise EmbeddingError(f"{self.name}: {name} is not set")
        return value

    def _bearer_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
        }

    def _served_model(self, body: dict) -> str:
        return self.model

    @abstractmethod
    def _endpoint(self) -> str: ...

    @abstractmethod
    def _headers(self) -> dict[str, str]: ...

    @abstractmethod
    def _payload(self, texts: list[str], task: Task) -> dict[str, object]: ...

    @abstractmethod
    def _raw_vectors(self, body: dict) -> list[Vector]: ...

    @abstractmethod
    def _prompt_tokens(self, body: dict) -> int: ...

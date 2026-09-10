from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

import requests

from labpilot._text import truncate
from labpilot.rerank.contracts import Ranking
from labpilot.rerank.defaults import (
    DEFAULT_TIMEOUT,
    MAX_DOCUMENT_TOKENS,
    MAX_DOCUMENTS,
)
from labpilot.rerank.errors import RerankError
from labpilot.tokens import estimate_tokens

logger = logging.getLogger(__name__)

SHAPE_ERRORS = (KeyError, TypeError, ValueError, AttributeError, IndexError)


@dataclass(frozen=True, slots=True, kw_only=True)
class HTTPReranker(ABC):
    """The shared half of a cross-encoder call over HTTP.

    Written only after all three providers were probed live on 2026-09-11, so
    the seam is OBSERVED and not guessed - the same discipline that produced
    llm/base.py and embed/base.py. The five abstract methods are exactly the
    five places the three providers really disagreed:

        model in the URL (Cloudflare) vs in the body (Voyage, Cohere)
        contexts=[{"text": ...}] vs documents=[str]
        results at result.response vs data vs results
        id/score vs index/relevance_score
        neurons vs tokens vs search_units - three units, never comparable

    That last row is why usage is LOGGED and not returned. `LLMResult` only
    gained a field once every provider could fill it honestly; a single
    `usage` number here would have to pretend a neuron is a token.
    """

    name: str
    url: str
    model: str
    api_key_env: str
    account_env: str | None = None
    max_documents: int = MAX_DOCUMENTS
    max_document_tokens: int = MAX_DOCUMENT_TOKENS
    timeout: tuple[float, float] = DEFAULT_TIMEOUT

    def rank(
        self,
        query: str,
        documents: Sequence[str],
        *,
        top_n: int | None = None,
    ) -> Ranking:
        self._check_inputs(query, documents, top_n)

        try:
            response = requests.post(
                self._endpoint(),
                headers=self._headers(),
                json=self._payload(query, list(documents), top_n),
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise RerankError(f"{self.name}: request failed: {exc}") from exc

        if response.status_code != 200:
            raise RerankError(
                f"{self.name}: HTTP {response.status_code}: {truncate(response.text)}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise RerankError(
                f"{self.name}: response was not JSON: {truncate(response.text)}"
            ) from exc

        try:
            raw = self._raw_ranking(body)
            usage = self._usage_summary(body)
        except SHAPE_ERRORS as exc:
            raise RerankError(
                f"{self.name}: unexpected response shape: {truncate(str(body))}"
            ) from exc

        order, scores = self._validated(raw, sent=len(documents))

        logger.info(
            "%s ranked %d of %d documents (%s)",
            self.model,
            len(order),
            len(documents),
            usage,
        )

        return Ranking(order=order, scores=scores, model=self.model)

    def _check_inputs(
        self, query: str, documents: Sequence[str], top_n: int | None
    ) -> None:
        """Refuse locally what the providers refuse remotely, and one thing
        they do not refuse at all.

        Every branch below was measured on 2026-09-11. A blank query is a 400
        on all three; empty documents is a 400 on Voyage and Cohere and an
        HTTP 500 on Cloudflare - which would read as the provider's fault when
        it is ours. The oversized-document branch is the one no provider
        reports: Cohere simply splits and bills twice, silently.
        """
        if not query.strip():
            raise ValueError("the rerank query must not be blank")
        if not documents:
            raise ValueError("there are no documents to rank")
        if top_n is not None and top_n < 1:
            raise ValueError(f"top_n must be positive, got {top_n}")

        blank = [i for i, document in enumerate(documents) if not document.strip()]
        if blank:
            raise ValueError(f"documents must not be blank, found at {blank[:3]}")

        if len(documents) > self.max_documents:
            raise ValueError(
                f"{len(documents)} documents is over {self.name}'s limit of "
                f"{self.max_documents}; the caller owns the loop"
            )

        over = [
            (i, estimate_tokens(document))
            for i, document in enumerate(documents)
            if estimate_tokens(document) > self.max_document_tokens
        ]
        if over:
            raise RerankError(
                f"{self.name}: {len(over)} document(s) exceed the "
                f"{self.max_document_tokens} token limit and would be split and "
                f"billed as several documents: {over[:3]}"
            )

    def _validated(
        self, raw: list[tuple[int, float]], *, sent: int
    ) -> tuple[tuple[int, ...], tuple[float, ...]]:
        """A ranking that names a document we never sent is silent corruption.

        The position is what the caller uses to look a chunk back up, so an
        index off by one cites the wrong file and line with full confidence.
        Fewer results than documents is legal - that is top_n - but more than
        we sent, a duplicate, or anything out of range is not.
        """
        if len(raw) > sent:
            raise RerankError(
                f"{self.name}: sent {sent} documents but got {len(raw)} results"
            )

        positions = tuple(position for position, _ in raw)

        outside = [position for position in positions if not 0 <= position < sent]
        if outside:
            raise RerankError(
                f"{self.name}: ranked document(s) {outside[:3]} that were never "
                f"sent - only 0..{sent - 1} exist"
            )

        if len(set(positions)) != len(positions):
            raise RerankError(
                f"{self.name}: the same document was ranked twice: {positions}"
            )

        return positions, tuple(float(score) for _, score in raw)

    def _api_key(self) -> str:
        return self._required(self.api_key_env)

    def _account_id(self) -> str:
        if self.account_env is None:
            raise RerankError(f"{self.name}: no account_env is configured")
        return self._required(self.account_env)

    def _required(self, name: str) -> str:
        value = os.environ.get(name, "").strip()
        if not value:
            raise RerankError(f"{self.name}: {name} is not set")
        return value

    def _bearer_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
        }

    @abstractmethod
    def _endpoint(self) -> str: ...

    @abstractmethod
    def _headers(self) -> dict[str, str]: ...

    @abstractmethod
    def _payload(
        self, query: str, documents: list[str], top_n: int | None
    ) -> dict[str, object]: ...

    @abstractmethod
    def _raw_ranking(self, body: dict) -> list[tuple[int, float]]: ...

    @abstractmethod
    def _usage_summary(self, body: dict) -> str: ...

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from labpilot.rerank.base import HTTPReranker


@dataclass(frozen=True, slots=True, kw_only=True)
class DocumentsReranker(HTTPReranker):
    """A provider that takes `documents` and answers `index, relevance_score`.

    Cohere and Voyage have this shape and differ in two field names only.
    """

    # The request field that asks for the best N, and the answer field of the hits.
    TOP_FIELD: ClassVar[str]
    HITS_FIELD: ClassVar[str]

    def _payload(
        self, query: str, documents: list[str], top_n: int | None
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self.model,
            "query": query,
            "documents": documents,
        }
        if top_n is not None:
            payload[self.TOP_FIELD] = top_n
        return payload

    def _raw_ranking(self, body: dict) -> list[tuple[int, float]]:
        return [
            (int(hit["index"]), float(hit["relevance_score"]))
            for hit in body[self.HITS_FIELD]
        ]

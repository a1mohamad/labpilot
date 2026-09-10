from __future__ import annotations

from dataclasses import dataclass

from labpilot.rerank.base import HTTPReranker


@dataclass(frozen=True, slots=True, kw_only=True)
class CohereReranker(HTTPReranker):
    """Probed live 2026-09-11, and the probe cost 3 of 1,000 calls a MONTH.

    Two things it reported that no other provider does. `billed_units` came
    back as `search_units: 1` for three documents, which confirms per-CALL
    billing up to 100 documents. And the response headers carry the ceiling
    itself - `x-endpoint-monthly-call-limit: 1000` - beside a number CLAUDE.md
    never recorded, `x-trial-endpoint-call-limit: 10`.
    """

    api_key_env: str = "COHERE_API_KEY"

    def _endpoint(self) -> str:
        return self.url

    def _headers(self) -> dict[str, str]:
        return self._bearer_headers()

    def _payload(
        self, query: str, documents: list[str], top_n: int | None
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self.model,
            "query": query,
            "documents": documents,
        }
        if top_n is not None:
            payload["top_n"] = top_n
        return payload

    def _raw_ranking(self, body: dict) -> list[tuple[int, float]]:
        return [
            (int(hit["index"]), float(hit["relevance_score"]))
            for hit in body["results"]
        ]

    def _usage_summary(self, body: dict) -> str:
        billed = body["meta"]["billed_units"]
        return f"{billed.get('search_units', 0)} search units"

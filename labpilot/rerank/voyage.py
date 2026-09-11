from __future__ import annotations

from dataclasses import dataclass

from labpilot.rerank.base import HTTPReranker

# Voyage accepts up to 1,000 documents per call, but it bills by TOKEN, so a
# wider call is a proportionally larger bill - the opposite of Cohere, where
# width is free up to 100. The cap is declared anyway, because a limit that
# lives only in a comment is a limit nothing enforces.
MAX_DOCUMENTS = 1_000


@dataclass(frozen=True, slots=True, kw_only=True)
class VoyageReranker(HTTPReranker):
    """Probed live 2026-09-11 on a 200M one-time token grant.

    It is the strict one: an unknown field is a 400 naming the field, and a
    bad model name answers with the full list of models it does support. Both
    are the GOOD failure - Cloudflare accepts a typo with a 200 and changes
    nothing, which is the same mistake with no error attached.

    Its published token formula is the one our whole rerank budget rests on:

        tokens = (query tokens x documents) + sum of document tokens

    Measured on the probe: a ~7 token query against 3 short documents billed
    48 total tokens, which is what that formula predicts.
    """

    api_key_env: str = "VOYAGE_API_KEY"
    max_documents: int = MAX_DOCUMENTS

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
            payload["top_k"] = top_n
        return payload

    def _raw_ranking(self, body: dict) -> list[tuple[int, float]]:
        return [
            (int(hit["index"]), float(hit["relevance_score"])) for hit in body["data"]
        ]

    def _usage_summary(self, body: dict) -> str:
        return f"{body['usage']['total_tokens']} tokens"

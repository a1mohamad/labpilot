from __future__ import annotations

from dataclasses import dataclass

from labpilot.rerank.base import HTTPReranker
from labpilot.rerank.errors import RerankError


@dataclass(frozen=True, slots=True, kw_only=True)
class CloudflareReranker(HTTPReranker):
    """Probed live 2026-09-11, and the largest RENEWING budget in the project.

    Measured: 87 prompt tokens cost 0.024589 neurons, which is exactly the
    published 283 neurons per 1M input tokens. A real 50-document call is
    ~12,450 tokens, so ~3.52 neurons against 10,000 a DAY - about 2,840 calls
    daily, where Cohere gives 1,000 a month.

    Two traps it carries alone. `top_k` truncates the response and costs the
    SAME neurons, so it buys nothing but a smaller body - cost follows input,
    never output. And it reports failure inside a 200 with `success: false`,
    so the status code is not enough to tell whether the call worked.
    """

    api_key_env: str = "CLOUDFLARE_API_KEY"
    account_env: str | None = "CLOUDFLARE_ACCOUNT_ID"

    def _endpoint(self) -> str:
        return f"{self.url}/{self._account_id()}/ai/run/{self.model}"

    def _headers(self) -> dict[str, str]:
        return self._bearer_headers()

    def _payload(
        self, query: str, documents: list[str], top_n: int | None
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "query": query,
            "contexts": [{"text": document} for document in documents],
        }
        if top_n is not None:
            payload["top_k"] = top_n
        return payload

    def _raw_ranking(self, body: dict) -> list[tuple[int, float]]:
        if not body.get("success", True):
            raise RerankError(
                f"{self.name}: the response reports failure: {body.get('errors')}"
            )
        return [
            (int(hit["id"]), float(hit["score"])) for hit in body["result"]["response"]
        ]

    def _usage_summary(self, body: dict) -> str:
        usage = body["result"].get("usage")
        if not isinstance(usage, dict):
            return "usage not reported"
        return (
            f"{usage.get('neurons', 0):.4f} neurons, "
            f"{usage.get('total_tokens', 0)} tokens"
        )

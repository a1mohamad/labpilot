from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from labpilot.rerank.documents import DocumentsReranker


@dataclass(frozen=True, slots=True, kw_only=True)
class CohereReranker(DocumentsReranker):
    """Probed live 2026-09-11, and the probe cost 3 of 1,000 calls a MONTH.

    Two things it reported that no other provider does. `billed_units` came
    back as `search_units: 1` for three documents, which confirms per-CALL
    billing up to 100 documents. And the response headers carry the ceiling
    itself - `x-endpoint-monthly-call-limit: 1000` - beside a number CLAUDE.md
    never recorded, `x-trial-endpoint-call-limit: 10`.
    """

    TOP_FIELD: ClassVar[str] = "top_n"
    HITS_FIELD: ClassVar[str] = "results"

    api_key_env: str = "COHERE_API_KEY"

    def _usage_summary(self, body: dict) -> str:
        billed = body["meta"]["billed_units"]
        return f"{billed.get('search_units', 0)} search units"

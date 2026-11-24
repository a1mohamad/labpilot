from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from labpilot.rerank.documents import DocumentsReranker

# Voyage accepts up to 1,000 documents per call, but it bills by TOKEN, so a
# wider call is a proportionally larger bill - the opposite of Cohere, where
# width is free up to 100. The cap is declared anyway, because a limit that
# lives only in a comment is a limit nothing enforces.
# Voyage's PUBLISHED document limit is 1,000. That is the BILLED tier's number
# and it is the wrong limit twice over, because what binds a card-free account
# is TOKENS, not documents: 10,000 per minute, counting a call WHOLE.
#
# Measured 2026-09-11 on our own chunks, each after a clean 90-second wait:
#
#     50 documents  ~16,900 tokens   REFUSED
#     40 documents  ~13,100 tokens   REFUSED
#     30 documents   ~8,900 tokens   passed
#
# So 30 is the honest ceiling here, and modelling it as such is what lets the
# ask path send its full SEARCH_LIMIT window to the tiers that can take it -
# flash-lite is listwise and 50 documents is ~17,000 tokens against a 1M
# context - while Voyage gets 30 and ANSWERS, instead of burning one of its 3
# requests per minute on a refusal.
#
# Same lesson as quota_pool and Groq's context_window = 8_000: MODEL THE LIMIT
# THAT BINDS, not the one the vendor advertises.
MAX_DOCUMENTS = 30


@dataclass(frozen=True, slots=True, kw_only=True)
class VoyageReranker(DocumentsReranker):
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

    TOP_FIELD: ClassVar[str] = "top_k"
    HITS_FIELD: ClassVar[str] = "data"

    api_key_env: str = "VOYAGE_API_KEY"
    max_documents: int = MAX_DOCUMENTS

    def _usage_summary(self, body: dict) -> str:
        return f"{body['usage']['total_tokens']} tokens"

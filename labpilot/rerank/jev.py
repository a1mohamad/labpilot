from __future__ import annotations

from dataclasses import dataclass

from labpilot.rerank.base import HTTPReranker
from labpilot.rerank.contracts import Ranking


@dataclass(frozen=True, slots=True, kw_only=True)
class JevReranker(HTTPReranker):
    """TypeSafe Jev, a decision model, used as a reranker.

    Jev is not an LLM and has no ranking type at all. What it has is `noul` -
    a yes/no PROBABILITY - and one call answers a question per document in a
    single parallel pass. So a ranking is N nouls, sorted:

        s(q, d) in [0, 1]

    MEASURED 2026-09-19 on two corpora at a 30-document window, against
    vector alone:

                            quora (Python)        geo (Go)
        vector alone        MRR 0.608             MRR 0.526
        Jev                 MRR 0.770  r@1 0.647  MRR 0.712  r@1 0.644
        gemini-3.5-flash-lite   0.799      0.706      0.681      0.622

    It beats every other tier in this package on both corpora, and beats
    flash-lite on geo - the corpus with real headroom, where vector `r@50` is
    0.867 rather than saturated at 1.000. Latency 1.2-1.5s for 30 documents,
    which is flash-lite's speed and ~15x faster than either Gemma.

    IT IS LISTWISE, WHICH THE SHAPE DOES NOT SUGGEST. A noul per document
    looks pointwise, and a pointwise scorer may be cached per (query, chunk).
    Jev may not: every document shares one `state`, so a score is conditioned
    on its neighbours. Measured, the same chunk scored 0.62 among 2 documents
    and 0.85 among 10 - drift 2.3e-01 against an effect size of about 0.15.
    Nothing in production depends on that, because the chain asks for one
    ranking of one set; it is recorded so no future cache repeats slice 8 v2's
    per-pair mistake.

    IT IS BILLED, and it is the first paid tier in any chain in this project.
    $0.042 per million input tokens, output free - about $0.0006 for a
    30-document call over Go chunks. The balance does NOT report it for about
    a minute, which is long enough to look free: a first call left
    `total_usage` at 0 and sixty seconds later read exactly that call's cost.

    `alpha` in the endpoint is the provider's own warning. The route, the
    shape and the billing can all change without notice, and the chain
    falling through to the next tier is what that failure looks like.
    """

    api_key_env: str = "OPENROUTER_API_KEY"
    # 32,000 tokens on the OpenRouter route, against 64,000 on TypeSafe
    # direct. 50 Go chunks are ~23,700 tokens, so SEARCH_LIMIT fits - but
    # only just, and a corpus with larger chunks would not. Slice 8 measured
    # the same thing about Gemma: a tier's usable window is a property of the
    # CORPUS as well as the provider.
    max_documents: int = 50

    def _endpoint(self) -> str:
        return self.url

    def _headers(self) -> dict[str, str]:
        return self._bearer_headers()

    def _payload(
        self, query: str, documents: list[str], top_n: int | None
    ) -> dict[str, object]:
        """One `state` holding every document, one `noul` each.

        The keys are `d0..dN-1` so a position can be read back out of the
        answer without keeping any state on this frozen dataclass - which is
        also what lets `_raw_ranking` stay a pure function of the body.

        `top_n` is absent on purpose: Jev has no such parameter, so it is
        applied to the result instead. See `rank`.
        """
        return {
            "model": self.model,
            "state": {"question": query}
            | {f"d{i}": document for i, document in enumerate(documents)},
            "questions": {
                f"d{i}": {
                    "type": "noul",
                    "instructions": (
                        f"Does the code or text in `d{i}` answer `question`? "
                        f"Answer yes only if `d{i}` itself contains the "
                        f"answer, not merely the same topic."
                    ),
                }
                for i in range(len(documents))
            },
        }

    def _raw_ranking(self, body: dict) -> list[tuple[int, float]]:
        scored = [
            (int(key[1:]), float(answer["noul"]))
            for key, answer in body["answers"].items()
        ]
        return sorted(scored, key=lambda pair: (-pair[1], pair[0]))

    def _usage_summary(self, body: dict) -> str:
        usage = body.get("usage", {})
        tokens = usage.get("input_tokens", 0)
        return f"{tokens} input tokens, ${usage.get('cost', 0):.6f}"

    def rank(self, query: str, documents, *, top_n: int | None = None) -> Ranking:
        """The template call, then our own cut.

        Every other tier sends `top_n` and lets the provider truncate. Jev has
        no such field, so honouring it here keeps the contract identical
        across the chain - a caller must not have to know which tier answered.
        """
        ranking = super().rank(query, documents, top_n=top_n)
        if top_n is None or top_n >= len(ranking.order):
            return ranking
        return Ranking(
            order=ranking.order[:top_n],
            scores=ranking.scores[:top_n],
            model=ranking.model,
        )

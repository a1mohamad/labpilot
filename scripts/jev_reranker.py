"""TypeSafe Jev as a reranker, reached through a Netlify AI Gateway proxy.

WHY A PROXY, AND WHY THIS LIVES IN scripts/
===========================================
Netlify's AI Gateway injects TYPESAFE_API_KEY only into code running ON
Netlify, so a tiny pass-through function stands between us and Jev. That is
also what makes Jev reachable at all without a card: Netlify supplies the
credential, so no TypeSafe account and no waitlist are needed.

It sits in scripts/ for the same reason local_reranker.py does. It is a
MEASUREMENT instrument, not a tier. Nothing in labpilot/ may depend on a
second deployment target, and `Reranker` is a Protocol rather than a base
class, so this can still drive the production chain with no shared import.

WHAT IS BEING TESTED, AND WHY IT IS NOT OBVIOUS
===============================================
Jev has no ranking type. It has `noul` - a yes/no PROBABILITY - which is
exactly the shape a cross-encoder produces:

    s(q, d) in [0, 1]

Slice 6 proved our cross-encoders are pointwise, so a per-document probability
is a legitimate reranker. The open question is whether JEV's is pointwise,
because every document sits in one `state` and all the questions are answered
in a single parallel pass - so a document's score COULD move when its
neighbours change. score_rerank's verify_pointwise answers that rather than
assuming it, which is the only reason the per-pair cache is safe.

    JEV_PROXY_URL      https://<site>.netlify.app/api/jev
    JEV_PROXY_SECRET   the shared secret set in the Netlify UI
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import requests

from labpilot.rerank import Ranking, RerankError

# The alias, not a pinned version: TypeSafe moves `jev-latest` forward and a
# re-measurement should follow it. The pinned id `jev-1.13` exists if a number
# ever has to be reproduced exactly.
MODEL = "jev-latest"

# Connect, then read. Jev claims 70-500ms; 60s of read is generous enough that
# a timeout means something is wrong rather than merely slow.
TIMEOUT = (10.0, 60.0)


@dataclass(slots=True)
class JevReranker:
    """One call, one `noul` per document, sorted by probability."""

    name: str = "Jev (TypeSafe)"
    model: str = MODEL
    max_documents: int = 50
    # Filled per call so the run can report the provider's own latency apart
    # from our network round trip to Netlify and Netlify's to TypeSafe.
    timings: list[dict[str, float]] = field(default_factory=list)

    def rank(self, query: str, documents, *, top_n: int | None = None) -> Ranking:
        if not query.strip():
            raise ValueError("the rerank query must not be blank")
        documents = list(documents)
        if not documents:
            raise ValueError("there are no documents to rank")
        if top_n is not None and top_n < 1:
            raise ValueError(f"top_n must be positive, got {top_n}")
        if len(documents) > self.max_documents:
            raise RerankError(
                f"{self.name}: {len(documents)} documents exceeds the "
                f"{self.max_documents} this tier accepts"
            )

        url = os.environ.get("JEV_PROXY_URL")
        secret = os.environ.get("JEV_PROXY_SECRET")
        if not url or not secret:
            raise RerankError("JEV_PROXY_URL / JEV_PROXY_SECRET are not set")

        keys = [f"d{i}" for i in range(len(documents))]
        state = {"question": query} | dict(zip(keys, documents, strict=True))
        questions = {
            key: {
                "type": "noul",
                "instructions": (
                    f"Does the code or text in `{key}` answer `question`? "
                    f"Answer yes only if `{key}` itself contains the answer, "
                    f"not merely the same topic."
                ),
            }
            for key in keys
        }

        started = time.monotonic()
        try:
            response = requests.post(
                url,
                json={"model": self.model, "state": state, "questions": questions},
                headers={"x-jev-proxy-key": secret},
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise RerankError(f"{self.name}: could not reach the proxy: {exc}") from exc
        elapsed = time.monotonic() - started

        if response.status_code != 200:
            # The status is kept in the message because score_rerank decides
            # whether to retry by reading it - "429", "HTTP 500", "HTTP 503".
            raise RerankError(
                f"{self.name}: HTTP {response.status_code}: {response.text[:400]}"
            )

        try:
            answers = response.json()["answers"]
        except (ValueError, KeyError, TypeError) as exc:
            raise RerankError(
                f"{self.name}: unexpected response shape: {response.text[:400]}"
            ) from exc

        scores = []
        for key in keys:
            answer = answers.get(key)
            if not isinstance(answer, dict) or "noul" not in answer:
                raise RerankError(f"{self.name}: no noul returned for {key}")
            scores.append(float(answer["noul"]))

        self.timings.append(
            {
                "documents": len(documents),
                "round_trip": elapsed,
                "upstream": float(response.headers.get("x-jev-upstream-ms", 0)) / 1000,
            }
        )

        ordered = sorted(range(len(documents)), key=lambda i: (-scores[i], i))
        if top_n is not None:
            ordered = ordered[:top_n]
        return Ranking(
            order=tuple(ordered),
            scores=tuple(scores[i] for i in ordered),
            model=self.model,
        )


JEV_RERANK = JevReranker()

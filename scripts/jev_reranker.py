"""TypeSafe Jev as a reranker, reached through a Netlify AI Gateway proxy.

HOW IT IS REACHED, AND WHAT THAT COST TO FIND
=============================================
Through OpenRouter, on the key this project already has - no TypeSafe
account, no waitlist, and no Netlify proxy. Jev does NOT appear in
`GET /api/v1/models` (447 chat models, zero hits) because its modality is
`text->decisions`, and it is refused by `/chat/completions`. The refusal is
what named the route:

    "typesafe/jev-1.13 is a decisions model and cannot be used with the
     chat/completions endpoint. Use the /api/alpha/decisions endpoint"

IT IS BILLED, and the balance did not say so for a full minute. A first call
left `total_usage` at 0, which looks exactly like Cline's genuinely-free
tier; sixty seconds later it read 0.000014364 - to the digit, that call. So
the account counter is NOT a live instrument, and "the balance did not move"
means nothing until it has had a minute.

`alpha` in the path is a warning: the route, its shape and its billing can
change without notice.

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

    OPENROUTER_API_KEY   the key this project already uses for tiers 10/16/17
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
URL = "https://openrouter.ai/api/alpha/decisions"

# The PINNED id, not the `jev-latest` alias. A measurement that cannot be
# reproduced is a number, and an alias moves underneath one.
MODEL = "typesafe/jev-1.13"

# Connect, then read. Jev claims 70-500ms; 60s of read is generous enough that
# a timeout means something is wrong rather than merely slow.
TIMEOUT = (10.0, 60.0)


@dataclass(slots=True)
class JevReranker:
    """One call, one `noul` per document, sorted by probability."""

    name: str = "Jev (TypeSafe)"
    model: str = MODEL
    # 32,000 on the OpenRouter route, against 64,000 on TypeSafe direct. The
    # window a tier can really take is a property of the CORPUS as well as the
    # provider - slice 8 measured Gemma serving 50 Python chunks and refusing
    # 30 Go ones - so this is a ceiling, not a promise.
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

        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RerankError("OPENROUTER_API_KEY is not set")

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
                URL,
                json={"model": self.model, "state": state, "questions": questions},
                headers={"Authorization": f"Bearer {key}"},
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise RerankError(
                f"{self.name}: could not reach OpenRouter: {exc}"
            ) from exc
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

        usage = response.json().get("usage", {})
        self.timings.append(
            {
                "documents": len(documents),
                "round_trip": elapsed,
                "input_tokens": float(usage.get("input_tokens", 0)),
                "cost": float(usage.get("cost", 0.0)),
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

"""A generative model used as a listwise reranker.

WHY IT TAKES A CALLABLE AND NOT A PROVIDER
==========================================
This needs an LLM, and `llm/` is an ADAPTER just as `rerank/` is - so importing
it is exactly what test_architecture forbids, and the rule is right: two
adapters that know each other's types are welded together and neither can be
replaced.

`rerank/` already solved this shape once. It cannot see `SearchHit` either, so
it takes plain strings and lets the caller translate. The same answer works
here: take `complete(prompt, max_tokens) -> str` and let whoever owns both
layers supply it. Dependency injection, one function, no import, no coupling.

    from labpilot.llm import GEMINI_3_5_FLASH_LITE
    from labpilot.rerank import LLMReranker

    flash = LLMReranker(
        complete=lambda p, n: GEMINI_3_5_FLASH_LITE.complete(p, max_tokens=n).text,
        name="Gemini 3.5 Flash-Lite",
        model="gemini-3.5-flash-lite",
    )

WHY LISTWISE
============
    pointwise   one call per document, "score this 0-10"   -> N calls
    pairwise    "is A better than B?"                      -> N^2 calls
    listwise    one call, "put these in order"             -> 1 call

At 30 documents that is 1 call against 30. It is also the only shape a free
generation tier can afford, and it plays to what an LLM is good at: comparing
things it can see side by side.

MEASURED 2026-09-11, and it is why the LLM tiers lead chain 3. On quora at a
30-document window, against vector alone's MRR of 0.608:

    gemini-3.5-flash-lite   0.799      gemma-4-26b-a4b-it   0.732
    gemini-3.1-flash-lite   0.745      gemma-4-31b-it       0.732

All four beat every purpose-built cross-encoder measured.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from labpilot.rerank.contracts import Ranking
from labpilot.rerank.defaults import (
    MAX_DOCUMENT_TOKENS,
    MAX_DOCUMENTS,
    RERANK_MAX_TOKENS,
)
from labpilot.rerank.errors import RerankError

# Deliberately small. This project measured a 12,620-byte instruction scoring
# no better than a bare one, and a 1,997-byte rewrite beating both.
PROMPT = """Rank these code chunks by how well each one answers the question.

QUESTION: {query}

{documents}

Answer with ONLY the {count} numbers, best first, separated by commas.
No explanation, no bullet points, no repeating the question.
Format: 7, 2, 15, 1"""

NUMBER = re.compile(r"\d+")

# A run of at least two numbers separated by commas - "3, 1, 2, 4".
#
# THIS IS THE WHOLE PARSER, and the naive version was wrong in a way that
# looked like a bad model. Reading numbers left to right picks them out of the
# model's REASONING: gemma walks the chunks in order writing "Chunk [1] ...
# Chunk [2] ... Chunk [3]", and gives its answer last. A left-to-right scan
# therefore returns the identity order, and the model looks like it refused to
# rank while it was in fact ranking correctly. This project recorded gemma as
# UNUSABLE for a day on exactly that mistake.
SEQUENCE = re.compile(r"\d+(?:\s*,\s*\d+)+")


@dataclass(slots=True)
class LLMReranker:
    """Listwise reranking through any `complete(prompt, max_tokens) -> str`."""

    complete: Callable[[str, int], str]
    name: str
    model: str
    max_documents: int = MAX_DOCUMENTS
    max_document_tokens: int = MAX_DOCUMENT_TOKENS
    max_tokens: int = RERANK_MAX_TOKENS
    # How often the model returned no usable ranking at all. This is INVISIBLE
    # in MRR - a decline keeps the retrieval order, which scores exactly like
    # not reranking - so a model that abstains looks average rather than
    # broken. Measured: gemma-4-26b-a4b declines about 1 query in 17.
    declined: int = field(default=0, compare=False)

    def rank(
        self,
        query: str,
        documents: Sequence[str],
        *,
        top_n: int | None = None,
    ) -> Ranking:
        documents = list(documents)
        if not query.strip():
            raise ValueError("the rerank query must not be blank")
        if not documents:
            raise ValueError("there are no documents to rank")
        if top_n is not None and top_n < 1:
            raise ValueError(f"top_n must be positive, got {top_n}")
        if len(documents) > self.max_documents:
            raise ValueError(
                f"{len(documents)} documents is over {self.name}'s limit of "
                f"{self.max_documents}; the caller owns the loop"
            )

        # ONE-BASED labels. Measured: with [0]..[3] a model replied "3, 1, 0, 4",
        # reading the labels as zero-based and one-based in the same answer.
        # Training data counts from 1; the conversion belongs here.
        listing = "\n\n".join(f"[{i + 1}]\n{text}" for i, text in enumerate(documents))
        prompt = PROMPT.format(query=query, documents=listing, count=len(documents))

        try:
            reply = self.complete(prompt, self.max_tokens)
        except Exception as exc:
            # The caller's function wraps some other layer's error vocabulary -
            # LLMError today - which rerank/ deliberately cannot see. Wrapping
            # it here is what lets the chain treat a dead tier like any other.
            raise RerankError(f"{self.name}: {exc}") from exc

        order = self._parse(reply or "", len(documents))
        return Ranking(
            order=tuple(order if top_n is None else order[:top_n]),
            model=self.model,
        )

    def _parse(self, text: str, sent: int) -> list[int]:
        """Turn free text into a complete, legal ordering.

        A generative model will skip a number, repeat one, invent one that was
        never sent, or answer with nothing at all. All four are repaired rather
        than raised: throwing a whole ranking away over one typo is worse than
        putting the unmentioned documents back where retrieval had them.
        """
        runs = list(SEQUENCE.finditer(text))
        if runs:
            # Longest run, ties toward the LAST - a model that reasons first
            # puts its answer at the end, and one that answers immediately has
            # only one run anyway.
            best = max(runs, key=lambda m: (len(NUMBER.findall(m.group())), m.start()))
            source = best.group()
        else:
            source = text

        seen: list[int] = []
        for match in NUMBER.finditer(source):
            value = int(match.group()) - 1  # the labels are one-based
            if 0 <= value < sent and value not in seen:
                seen.append(value)

        if not seen:
            # An empty ranking is an ANSWER, not a crash: the model declined.
            # Retrieval's order stands, which is exactly what skip() means.
            self.declined += 1
            return list(range(sent))

        return seen + [i for i in range(sent) if i not in seen]

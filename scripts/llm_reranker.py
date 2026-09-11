"""LLM-as-reranker: tier 4 of chain 3, and a different mechanism entirely.

WHY THIS IS IN scripts/ AND NOT labpilot/rerank/ - AN ARCHITECTURE FINDING
=========================================================================
CLAUDE.md lists `ministral-3b-2512` as tier 4 of chain 3, so it looks like it
belongs in labpilot/rerank/ beside the cross-encoders. It cannot go there.

An LLM reranker needs labpilot/llm/ to make the call. Both `rerank` and `llm`
are ADAPTERS, and test_architecture's rule is that an adapter may import only
the shared layer - never another adapter. So tier 4 as specified is unbuildable
at the layer CLAUDE.md implies.

That is the layering rule doing its job, not an obstacle. When this ships it
belongs at the ENTRY or agent layer, which may import both - the same place the
Chunk -> ChunkRecord translation lives, and for the same reason. Recorded here
so slice 7 or 8 does not discover it by fighting a red build.

WHY LISTWISE
============
Three ways to use an LLM as a reranker:

    pointwise   one call per document, "score this 0-10"   -> N calls
    pairwise    "is A better than B?"                      -> N^2 calls
    listwise    one call, "put these in order"             -> 1 call

At 30 documents that is 30 calls against 1. Listwise also plays to what an LLM
is actually good at - comparing things it can see side by side - and it is the
only one that fits a free tier at all.

THE HYPOTHESIS IT TESTS
=======================
The cross-encoders failed hardest on `structure` (0.926 -> 0.392) and
`behaviour` (-0.258): queries about what code DOES. Those models are trained on
web prose. An LLM reads code natively, so it should be strongest exactly where
they were weakest. That is the reason to spend calls on this.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from labpilot.rerank import Ranking, RerankError

# Deliberately small. This project measured a 12,620-byte instruction scoring
# no better than a bare one, and a 1,997-byte rewrite beating both. A reranking
# instruction has one job and should say it once.
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
# model's REASONING: gemma-4-31b walks the chunks in order, writing "Chunk [1]
# ... Chunk [2] ... Chunk [3]", and only then gives its answer. A left-to-right
# scan therefore returns 1, 2, 3, 4 - the identity order - and the model looks
# like it refused to rank while it was in fact ranking correctly.
#
# Measured 2026-09-11: gemma reasoned to the right answer and ended with
# "3, 1, 2, 4", and this project recorded it as UNUSABLE for a day because
# only the first 90 characters of its reply were ever read.
SEQUENCE = re.compile(r"\d+(?:\s*,\s*\d+)+")


@dataclass(slots=True)
class LLMReranker:
    """Any llm/ provider, used as a listwise reranker."""

    provider: object
    name: str = ""
    model: str = ""
    max_documents: int = 50
    max_document_tokens: int = 510
    # Enough for 50 two-digit numbers and commas, plus room for a thinking
    # model to spend some of the budget before it answers.
    max_tokens: int = 4_096
    last_text: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        self.name = self.name or getattr(self.provider, "name", "llm reranker")
        self.model = self.model or getattr(self.provider, "model", "unknown")

    def rank(self, query: str, documents, *, top_n: int | None = None) -> Ranking:
        if not query.strip():
            raise ValueError("the rerank query must not be blank")
        documents = list(documents)
        if not documents:
            raise ValueError("there are no documents to rank")
        if top_n is not None and top_n < 1:
            raise ValueError(f"top_n must be positive, got {top_n}")

        # ONE-BASED labels. Measured 2026-09-11: with [0]..[3], ministral-3b
        # replied "3, 1, 0, 4" - using both 0 and 4 for a four-document set, so
        # it read the labels as zero-based and one-based in the same answer.
        # Training data counts from 1. The conversion belongs here, where it is
        # one line and cannot be forgotten, not in the model.
        listing = "\n\n".join(f"[{i + 1}]\n{text}" for i, text in enumerate(documents))
        prompt = PROMPT.format(query=query, documents=listing, count=len(documents))

        try:
            answer = self.provider.complete(prompt, max_tokens=self.max_tokens)
        except Exception as exc:  # llm/ raises LLMError, which rerank/ cannot see
            raise RerankError(f"{self.name}: {exc}") from exc

        self.last_text = answer.text
        order = self._parse(answer.text, len(documents))
        if top_n is not None:
            order = order[:top_n]
        return Ranking(order=tuple(order), model=self.model)

    def _parse(self, text: str, sent: int) -> list[int]:
        """Turn free text into a complete, legal ordering.

        A generative model will skip a number, repeat one, or invent one that
        was never sent - all three were expected and all three are handled
        here rather than raised, because the alternative is throwing away a
        whole ranking over one typo.

        Anything it failed to mention keeps its RETRIEVAL order at the back.
        That is the honest fallback: the model expressed no opinion about
        those, so they stay where search put them.
        """
        # Prefer an explicit comma-separated run, and among those prefer the
        # LONGEST, breaking ties toward the LAST - a model that reasons first
        # puts its answer at the end, and a model that answers immediately has
        # only one run anyway. Falling back to a bare left-to-right scan keeps
        # a reply like "4" or "3 then 1" usable.
        runs = list(SEQUENCE.finditer(text))
        if runs:
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
            raise RerankError(
                f"{self.name}: no usable document numbers in the reply: {text[:200]!r}"
            )

        missing = [i for i in range(sent) if i not in seen]
        return seen + missing

    @property
    def coverage(self) -> str:
        """How much of the last reply was actually a ranking - a quality signal
        that costs nothing and says whether the model did the job or waffled."""
        return self.last_text[:120].replace("\n", " ")

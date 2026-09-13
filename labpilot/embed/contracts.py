from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Vector = tuple[float, ...]

# Some providers embed a question and a passage differently, and say so on
# the wire: Cohere requires input_type, Google takes taskType. Providers
# without the distinction ignore it.
Task = Literal["query", "document"]


@dataclass(frozen=True, slots=True, kw_only=True)
class Rate:
    """What stops a model going faster - and providers do not agree on which.

    Three kinds of ceiling, all real, all measured on our own account:

        codestral-embed   50,000 tokens/minute   -> tokens bind
        mistral-embed     60 requests/minute     -> requests bind
        bge-base          10,000 neurons/DAY     -> a whole-day budget binds

    None means NOT KNOWN, never "unlimited". A model with nothing known takes
    infinite time and sorts last, because an unknown is not a promise.
    """

    tokens_per_minute: int | None = None
    requests_per_minute: int | None = None
    daily_token__budget: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Spec:
    """Everything the PROVIDER decides about a model, in one row.

    Our own choices - the display name, the URL, which key it uses - stay on
    the entry. This holds only what we do not control, so a provider changing
    something touches exactly one table.
    """

    dim: int
    rate: Rate
    max_input_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    vectors: tuple[Vector, ...]
    model: str
    dim: int
    prompt_tokens: int

    def __post_init__(self):
        if not self.vectors:
            raise ValueError("an embedding batch must hold at least one vector")

        wrong = [len(vector) for vector in self.vectors if len(vector) != self.dim]
        if wrong:
            raise ValueError(
                f"every vector must have {self.dim} dimensions, found {wrong[:3]}"
            )

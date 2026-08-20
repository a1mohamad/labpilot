from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Vector = tuple[float, ...]

# Some providers embed a question and a passage differently, and say so on
# the wire: Cohere requires input_type, Google takes taskType. Providers
# without the distinction ignore it.
Task = Literal["query", "document"]


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

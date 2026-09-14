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
    """The provider's PUBLISHED limits. Recorded, and only partly trusted.

    `tokens_per_minute` is deliberately NOT used to estimate time. Measured
    2026-09-14: codestral sustained 473,000-590,000 tokens/minute against a
    documented 50,000 - 10x out, with zero refusals - while Google enforced
    its 30,000 exactly. A number that is right for one provider and 10x wrong
    for another cannot predict anything. `measured_tokens_per_minute` on Spec
    does that job instead; this field stays so rates.learn() can notice when
    a header contradicts it.

    `requests_per_minute` IS used, because it is a hard ceiling no throughput
    can beat: Cohere allows 10 calls a minute, so 57 requests take 5.7 minutes
    however fast each one is.

    `daily_token_budget` is a third kind entirely - not a rate but a whole-day
    allowance. Cloudflare's 10,000 free neurons buy ~684,000 tokens, after
    which BGE cannot run at all until tomorrow.

    None means NOT KNOWN, never "unlimited".
    """

    tokens_per_minute: int | None = None
    requests_per_minute: int | None = None
    daily_token_budget: int | None = None


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
    # MEASURED sustained throughput, not a published quota. The two disagree
    # badly: codestral sustained 473-590k against a documented 50,000, while
    # Google enforced its 30,000 exactly. Measured 2026-09-14 over a Frankfurt
    # VPN exit, timeboxed pushes of 18-37 requests with varying batch sizes.
    # A SEED - runtime observation should replace it.
    measured_tokens_per_minute: int | None = None


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

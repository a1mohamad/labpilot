from __future__ import annotations

import logging
import time
from collections.abc import Iterator, Sequence
from typing import Protocol

from labpilot.embed.contracts import EmbeddingBatch, Pace, Task
from labpilot.embed.defaults import (
    PACE_HEADROOM,
    PACED_BATCHES_PER_MINUTE,
    RETRY_WAITS,
    RETRYABLE_STATUSES,
)
from labpilot.embed.errors import EmbeddingError
from labpilot.embed.pacing import Clock, Sleep, reserve
from labpilot.tokens import estimate_tokens

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    name: str
    max_batch_size: int
    pace: Pace | None

    @property
    def pool(self) -> str: ...

    def embed(
        self, texts: Sequence[str], *, task: Task = "document"
    ) -> EmbeddingBatch: ...


def looks_like_too_many_tokens(error: EmbeddingError) -> bool:
    # Measured 2026-09-05 on dask and fastapi: Mistral answers
    #   HTTP 400 code 3210 "Too many tokens overall, split into more batches."
    # Matching the word rather than one vendor's code keeps this true for the
    # other four providers, which have not been seen to say it yet.
    return "token" in str(error).lower()


def embed_batches(
    embedder: Embedder,
    texts: Sequence[str],
    *,
    task: Task = "document",
    size: int | None = None,
    clock: Clock = time.monotonic,
    sleep: Sleep = time.sleep,
) -> Iterator[EmbeddingBatch]:
    """Embed any number of texts, one request per yielded batch.

    The size starts at the embedder's own `max_batch_size`. MAX_BATCH_SIZE
    is derived from Mistral's per-MINUTE token limit, but providers
    also cap a single request, and `estimate_tokens` is `chars / 3` - which
    under-counts far enough to cross that cap on real repositories. Measured:
    a batch we estimated at 46,162 tokens was refused, while one Mistral had
    already accepted measured 59,466 real tokens.

    So the size is not a constant to get right, it is a starting guess to be
    corrected. On a refusal that names tokens the batch is halved and re-sent;
    every other failure is raised at once, because retrying a bad key smaller
    only wastes requests.

    On a PACED provider (Google) each request first waits for room in the
    pool's minute, and batches are cut by tokens so two fit a minute. A 429
    or 503 is waited out and the SAME batch sent again - never halved.

    Yields per request rather than returning everything, so a caller can write
    each batch away instead of holding every vector in memory.
    """
    if size is not None and size < 1:
        raise ValueError(f"size must be positive, got {size}")
    # CLAMP, never refuse: a caller asking for more than the provider takes gets
    # what the provider takes. Refusing would make every caller learn every
    # provider's limit, and the one caller that did not is the bug.
    limit = embedder.max_batch_size
    size = limit if size is None else min(size, limit)

    pace = embedder.pace
    costs = [estimate_tokens(text) for text in texts]
    per_batch = _tokens_per_batch(pace)

    start = 0
    while start < len(texts):
        step = _step(costs, start, size, per_batch)
        waits = iter(RETRY_WAITS)
        while True:
            if pace is not None:
                reserve(
                    embedder.pool,
                    pace,
                    tokens=sum(costs[start : start + step]),
                    texts=step,
                    clock=clock,
                    sleep=sleep,
                )
            try:
                batch = embedder.embed(texts[start : start + step], task=task)
            except EmbeddingError as exc:
                if exc.status in RETRYABLE_STATUSES:
                    # a WAIT, never a size: send the SAME batch again
                    wait = next(waits, None)
                    if wait is None:
                        raise EmbeddingError(
                            f"{exc} - still refused after waiting "
                            f"{sum(RETRY_WAITS):.0f}s. On Google this is almost "
                            "always the DAILY text budget, which resets tomorrow",
                            status=exc.status,
                            retry_after=exc.retry_after,
                        ) from exc
                    pause = max(wait, exc.retry_after or 0.0)
                    logger.warning(
                        "%s answered HTTP %s; waiting %.0fs, then the same batch",
                        embedder.name,
                        exc.status,
                        pause,
                    )
                    sleep(pause)
                    continue
                if step == 1 or not looks_like_too_many_tokens(exc):
                    raise
                # Remember the smaller size. Going back to the full size for
                # the next batch would earn the same refusal again, and each
                # one costs a request.
                step = size = max(1, step // 2)
                continue
            break

        yield batch
        start += step


def _tokens_per_batch(pace: Pace | None) -> int | None:
    if pace is None or not pace.tokens_per_minute:
        return None
    return int(pace.tokens_per_minute * PACE_HEADROOM / PACED_BATCHES_PER_MINUTE)


def _step(costs: list[int], start: int, size: int, per_batch: int | None) -> int:
    """How many texts from `start` go in the next request.

    At most `size`, and on a paced provider at most `per_batch` estimated
    tokens - so two batches fit the minute instead of one. Never zero: a single
    text larger than the budget still goes, alone.
    """
    end = min(len(costs), start + size)
    if per_batch is None:
        return end - start
    step, spent = 0, 0
    for cost in costs[start:end]:
        if step and spent + cost > per_batch:
            break
        step, spent = step + 1, spent + cost
    return step

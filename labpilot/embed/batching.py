from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Protocol

from labpilot.embed.contracts import EmbeddingBatch, Task
from labpilot.embed.defaults import MAX_BATCH_SIZE
from labpilot.embed.errors import EmbeddingError


class Embedder(Protocol):
    name: str

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
    size: int = MAX_BATCH_SIZE,
) -> Iterator[EmbeddingBatch]:
    """Embed any number of texts, one request per yielded batch.

    MAX_BATCH_SIZE is derived from the per-MINUTE token limit, but providers
    also cap a single request, and `estimate_tokens` is `chars / 3` - which
    under-counts far enough to cross that cap on real repositories. Measured:
    a batch we estimated at 46,162 tokens was refused, while one Mistral had
    already accepted measured 59,466 real tokens.

    So the size is not a constant to get right, it is a starting guess to be
    corrected. On a refusal that names tokens the batch is halved and re-sent;
    every other failure is raised at once, because retrying a bad key smaller
    only wastes requests.

    Yields per request rather than returning everything, so a caller can write
    each batch away instead of holding every vector in memory.
    """
    if size < 1:
        raise ValueError(f"size must be positive, got {size}")

    start = 0
    while start < len(texts):
        step = min(size, len(texts) - start)
        while True:
            try:
                yield embedder.embed(texts[start : start + step], task=task)
                start += step
                break
            except EmbeddingError as exc:
                if step == 1 or not looks_like_too_many_tokens(exc):
                    raise
                # Remember the smaller size. Going back to the full size for
                # the next batch would earn the same refusal again, and each
                # one costs a request.
                step = size = max(1, step // 2)

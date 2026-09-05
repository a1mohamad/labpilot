from __future__ import annotations

import pytest

from labpilot.embed import EmbeddingError, embed_batches
from labpilot.embed.contracts import EmbeddingBatch

DIM = 3
TOO_MANY = "Mistral Embed: HTTP 400: Too many tokens overall, split into more batches."


class Fake:
    """Refuses any request larger than `ceiling`, the way a provider does."""

    name = "Fake"

    def __init__(self, ceiling: int = 10_000, error: str = TOO_MANY):
        self.ceiling, self.error, self.sizes = ceiling, error, []

    def embed(self, texts, *, task="document"):
        self.sizes.append(len(texts))
        if len(texts) > self.ceiling:
            raise EmbeddingError(self.error)
        return EmbeddingBatch(
            vectors=tuple((float(i), 0.0, 0.0) for i, _ in enumerate(texts)),
            model="fake",
            dim=DIM,
            prompt_tokens=len(texts),
        )


def vectors(batches):
    return [v for batch in batches for v in batch.vectors]


def test_texts_that_fit_are_sent_in_one_request():
    fake = Fake()
    assert len(vectors(embed_batches(fake, ["a", "b", "c"], size=96))) == 3
    assert fake.sizes == [3]


def test_more_texts_than_the_batch_size_are_split():
    fake = Fake()
    assert len(vectors(embed_batches(fake, ["x"] * 10, size=4))) == 10
    assert fake.sizes == [4, 4, 2]


def test_a_refusal_about_tokens_halves_the_batch_and_retries():
    # the real defect: a batch our chars/3 estimate thought was fine is refused
    fake = Fake(ceiling=3)
    assert len(vectors(embed_batches(fake, ["x"] * 8, size=8))) == 8
    assert fake.sizes[0] == 8, "the first attempt must use the full size"
    assert fake.sizes[-1] <= fake.ceiling, "it must settle on an accepted size"


def test_the_smaller_size_is_remembered_for_the_batches_after_it():
    # going back to the full size would earn the same refusal again, and every
    # refusal costs a request
    fake = Fake(ceiling=3)
    list(embed_batches(fake, ["x"] * 8, size=8))

    assert fake.sizes.count(8) == 1, f"the full size was retried: {fake.sizes}"
    settled = fake.sizes[fake.sizes.index(min(fake.sizes)) :]
    assert all(n <= fake.ceiling for n in settled), fake.sizes


def test_every_text_still_gets_a_vector_after_a_split():
    fake = Fake(ceiling=2)
    assert len(vectors(embed_batches(fake, ["x"] * 7, size=8))) == 7


def test_a_failure_that_is_not_about_size_is_raised_at_once():
    # halving a bad API key only wastes requests
    fake = Fake(ceiling=0, error="Fake: HTTP 401: unauthorized")
    with pytest.raises(EmbeddingError, match="unauthorized"):
        list(embed_batches(fake, ["x"] * 8, size=8))
    assert fake.sizes == [8], "it must not retry smaller"


def test_a_single_text_that_is_refused_cannot_be_split_further():
    fake = Fake(ceiling=0)
    with pytest.raises(EmbeddingError, match="Too many tokens"):
        list(embed_batches(fake, ["x"], size=1))


@pytest.mark.parametrize("size", [0, -1])
def test_a_size_that_can_never_send_anything_is_a_caller_bug(size):
    with pytest.raises(ValueError, match="size"):
        list(embed_batches(Fake(), ["x"], size=size))

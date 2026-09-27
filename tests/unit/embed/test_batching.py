from __future__ import annotations

import pytest

from labpilot.embed import EmbeddingError, embed_batches, pacing
from labpilot.embed.contracts import EmbeddingBatch, Pace

DIM = 3
TOO_MANY = "Mistral Embed: HTTP 400: Too many tokens overall, split into more batches."


class Fake:
    """Refuses any request larger than `ceiling`, the way a provider does."""

    name = "Fake"
    max_batch_size = 96
    pace = None

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


def test_with_no_size_the_embedders_own_batch_size_is_used():
    fake = Fake()
    fake.max_batch_size = 4
    list(embed_batches(fake, ["x"] * 10))
    assert fake.sizes == [4, 4, 2]


def test_a_size_above_the_embedders_limit_is_clamped_not_refused():
    # the Google defect: a caller asking for 96 must get the 40 Google takes
    fake = Fake()
    fake.max_batch_size = 4
    list(embed_batches(fake, ["x"] * 10, size=96))
    assert fake.sizes == [4, 4, 2]


class Scripted:
    """Plays the script in order - an error is raised, None answers - then answers."""

    name = "Scripted"
    max_batch_size = 96
    pace = None
    pool = "SCRIPTED:model"

    def __init__(self, errors=()):
        self.errors, self.sizes = list(errors), []

    def embed(self, texts, *, task="document"):
        self.sizes.append(len(texts))
        if self.errors and (error := self.errors.pop(0)) is not None:
            raise error
        return EmbeddingBatch(
            vectors=tuple((1.0, 0.0, 0.0) for _ in texts),
            model="scripted",
            dim=DIM,
            prompt_tokens=0,
        )


class Sleeps(list):
    def __call__(self, seconds):
        self.append(seconds)


def refused(status=429, retry_after=None):
    # the message NAMES tokens on purpose: a 429 is still a wait, not a size
    return EmbeddingError(
        f"Fake: HTTP {status}: tokens per minute exceeded",
        status=status,
        retry_after=retry_after,
    )


@pytest.mark.parametrize("status", [429, 503])
def test_a_busy_refusal_is_waited_out_and_the_same_batch_sent_again(status):
    fake, sleeps = Scripted([refused(status)]), Sleeps()
    assert len(vectors(embed_batches(fake, ["x"] * 8, sleep=sleeps))) == 8
    assert fake.sizes == [8, 8], "a 429 must never halve the batch"
    assert sleeps == [20.0]


def test_a_longer_retry_after_is_honoured():
    fake, sleeps = Scripted([refused(retry_after=45.0)]), Sleeps()
    list(embed_batches(fake, ["x"] * 8, sleep=sleeps))
    assert sleeps == [45.0]


def test_a_refusal_that_outlasts_every_wait_names_the_daily_budget():
    fake, sleeps = Scripted([refused()] * 3), Sleeps()
    with pytest.raises(EmbeddingError, match="DAILY") as caught:
        list(embed_batches(fake, ["x"] * 8, sleep=sleeps))
    assert caught.value.status == 429
    assert fake.sizes == [8, 8, 8]
    assert sleeps == [20.0, 60.0]


def test_the_waits_start_again_for_every_batch():
    # one busy minute early in an ingest must not use up the retries of the
    # batches after it - the second refusal must wait 20s again, not 60s
    fake, sleeps = Scripted([refused(), None, refused(), None]), Sleeps()
    fake.max_batch_size = 4
    assert len(vectors(embed_batches(fake, ["x"] * 8, sleep=sleeps))) == 8
    assert sleeps == [20.0, 20.0]


def test_a_paced_provider_cuts_batches_so_two_fit_a_minute():
    # 1,000 a minute, 0.9 headroom, two a minute -> at most 450 per batch
    pacing.forget()
    fake = Scripted()
    fake.pace = Pace(tokens_per_minute=1_000)
    now = [0.0]

    def sleep(seconds):
        now[0] += seconds

    texts = ["x" * 90] * 40  # 30 estimated tokens each -> 15 per batch
    list(embed_batches(fake, texts, clock=lambda: now[0], sleep=sleep))
    pacing.forget()
    assert fake.sizes == [15, 15, 10]

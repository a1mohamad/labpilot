from __future__ import annotations

import math

import pytest

from labpilot.embed import MIGRATION, SPECS, by_speed, rates
from labpilot.embed.contracts import Rate
from labpilot.embed.mistral import MistralEmbedder

# Measured over this whole repository 2026-09-13: 5,386 chunks, 1,839,759
# estimated tokens. NOT the 192 CLAUDE.md carried from B_train.py - one file
# is not a population.
MEAN = 341.6


@pytest.fixture(autouse=True)
def clean():
    rates.forget()
    yield
    rates.forget()


def corpus(chunks: int) -> dict[str, int]:
    return {"tokens": int(chunks * MEAN), "chunks": chunks}


def fake(model: str, rate: Rate, measured: int | None = None) -> MistralEmbedder:
    return MistralEmbedder(
        name=model,
        url="https://x",
        model=model,
        dim=8,
        rate=rate,
        measured_tokens_per_minute=measured,
    )


def named(order) -> list[str]:
    return [embedder.model for embedder in order]


def test_the_binding_limit_is_the_one_that_decides():
    """Cohere is fast on the WIRE and slow on CALLS, and the calls win.

    Measured 2026-09-14: 641,000 tokens/minute in a burst, but it accepts only
    10 requests a minute. A 5,386-chunk corpus is 57 requests, so it takes 5.7
    minutes no matter how fast each call is. Throughput alone would say 2.9
    and be wrong - which is exactly the mistake the old quota formula made in
    the other direction.
    """
    big = corpus(5_386)
    cohere = next(e for e in MIGRATION if e.model == "embed-v4.0")
    codestral = next(e for e in MIGRATION if e.model == "codestral-embed")

    assert cohere.embedding_minutes(**big) > 5  # 57 requests / 10 per minute
    assert codestral.embedding_minutes(**big) < 5  # throughput binds, ~3.3


def test_a_model_that_cannot_finish_today_takes_infinite_time():
    """BGE's ceiling is a DAILY BUDGET, not a rate - a third kind of limit.

    Measured 2026-09-13: 96 chunks cost 261.68 neurons, so the free 10,000 a
    day buy only ~684,000 tokens. Expressing "cannot finish today" as infinite
    time sorts it out of the walk without a second mechanism.
    """
    bge = next(e for e in MIGRATION if e.model == "@cf/baai/bge-base-en-v1.5")

    assert bge.embedding_minutes(**corpus(1_000)) < 2
    assert bge.embedding_minutes(**corpus(5_386)) == math.inf


def test_a_model_nobody_has_timed_takes_infinite_time():
    """No provider reports throughput, so an untimed model is a blank, not a
    fast one. An unknown is not a promise."""
    assert (
        fake("mystery", Rate(requests_per_minute=60)).embedding_minutes(**corpus(100))
        == math.inf
    )


def test_the_published_quota_is_not_used_to_estimate_time():
    """The whole reason measured_tokens_per_minute exists.

    codestral's documented quota is 50,000/min, which would make this corpus
    37 minutes. Measured, it sustains ~550,000 and takes about 3. If the
    estimator ever falls back to the quota, this goes red.
    """
    codestral = next(e for e in MIGRATION if e.model == "codestral-embed")

    assert codestral.rate.tokens_per_minute == 50_000  # premise
    assert codestral.embedding_minutes(**corpus(5_386)) < 10


def test_by_speed_keeps_every_model():
    """The reason there is ONE list and not two pools.

    A two-pool version was proposed first and was wrong: a fast pool of two
    models, both exhausted, and nowhere left to go. Dropping a model here -
    for being slow, over budget, or untimed - rebuilds that dead end.
    """
    for chunks in (1, 1_000, 5_386, 100_000):
        order = by_speed(**corpus(chunks))

        assert sorted(named(order)) == sorted(named(MIGRATION)), chunks


def test_models_of_equal_speed_keep_the_strength_order():
    """Ties break by STRENGTH, bought with a stable sort.

    All four Google entries carry identical rates, so nothing about speed can
    separate them. They must come back in MIGRATION's order - embedding-2
    before 001, key 1 before key 2 - or the tie is broken by luck.
    """
    google = [e for e in MIGRATION if e.model.startswith("gemini-")]
    assert len({e.measured_tokens_per_minute for e in google}) == 1  # premise

    order = [e for e in by_speed(**corpus(5_386)) if e.model.startswith("gemini-")]

    assert order == google


def test_a_faster_model_really_does_sort_earlier():
    slow = fake("slow", Rate(requests_per_minute=60), measured=1_000)
    fast = fake("fast", Rate(requests_per_minute=60), measured=1_000_000)

    order = by_speed(**corpus(100), candidates=(slow, fast))

    assert named(order) == ["fast", "slow"]


def test_a_reported_request_ceiling_beats_the_declared_seed():
    """The one thing a header really tells us, and the only live lookup left.

    No provider reports throughput, so `measured_tokens_per_minute` has
    nothing to learn from. The REQUEST limit is different - Mistral sends
    x-ratelimit-limit-req-minute on every 200.
    """
    embedder = fake("m", Rate(requests_per_minute=60), measured=10_000_000)
    before = embedder.embedding_minutes(**corpus(5_386))

    rates.learn("m", {"x-ratelimit-limit-req-minute": "6"})

    assert embedder.embedding_minutes(**corpus(5_386)) == pytest.approx(before * 10)


def test_a_negative_corpus_is_a_callers_bug():
    """A caller's bug and a provider's failure are different exceptions."""
    embedder = fake("m", Rate(requests_per_minute=60), measured=100_000)

    with pytest.raises(ValueError, match="must not be negative"):
        embedder.embedding_minutes(tokens=-1, chunks=10)

    with pytest.raises(ValueError, match="must not be negative"):
        embedder.embedding_minutes(tokens=10, chunks=-1)


def test_every_model_in_the_migration_declares_its_facts():
    """SPECS is the one table, so a model missing from it has no facts at all.

    An entry built by hand instead of through _spec() would import fine and
    then report inf for ever - slow, silent, and indistinguishable from a
    genuinely slow model.
    """
    missing = sorted({e.model for e in MIGRATION} - set(SPECS))

    assert not missing, missing


def test_every_embedder_carries_its_measured_rate_from_the_table():
    """The table is useless if _spec() forgets to pass the field along.

    Omit that one line and every value sits in SPECS, never reaches a model,
    and every model reports inf. Nothing crashes.
    """
    for embedder in MIGRATION:
        assert (
            embedder.measured_tokens_per_minute
            == SPECS[embedder.model].measured_tokens_per_minute
        ), embedder.model

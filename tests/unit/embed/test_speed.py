from __future__ import annotations

import math

import pytest

from labpilot.embed import MIGRATION, SPECS, by_speed, rates
from labpilot.embed.contracts import Rate
from labpilot.embed.mistral import MistralEmbedder

# Measured over this whole repository on 2026-09-13: 5,386 chunks,
# 1,839,759 estimated tokens. NOT the 192 that CLAUDE.md carried from
# B_train.py - one file is not a population.
MEAN = 341.6


@pytest.fixture(autouse=True)
def clean():
    rates.forget()
    yield
    rates.forget()


def corpus(chunks: int) -> dict[str, int]:
    return {"tokens": int(chunks * MEAN), "chunks": chunks}


def fake(model: str, rate: Rate) -> MistralEmbedder:
    return MistralEmbedder(name=model, url="https://x", model=model, dim=8, rate=rate)


def named(order) -> list[str]:
    return [embedder.model for embedder in order]


def test_the_binding_limit_is_the_one_that_decides():
    """Two real models, one corpus, two different ceilings doing the work.

    codestral and mistral-embed BOTH allow 60 requests a minute, so a design
    that looked only at requests would call them equally fast. They are not:
    codestral's 50K tokens/minute binds long before its request budget does.
    Model the limit that binds, not the one the vendor advertises.
    """
    big = corpus(5_386)
    codestral = next(e for e in MIGRATION if e.model == "codestral-embed")
    mistral = next(e for e in MIGRATION if e.model == "mistral-embed")

    assert codestral.rate.requests_per_minute == mistral.rate.requests_per_minute
    assert codestral.minutes(**big) > 30  # tokens bind: ~36.8 min
    assert mistral.minutes(**big) < 2  # requests bind: ~0.9 min


def test_a_model_that_cannot_finish_today_takes_infinite_time():
    """BGE's ceiling is a DAILY BUDGET, not a rate - a third kind of limit.

    Measured 2026-09-13: 96 chunks cost 261.68 neurons, so the free 10,000
    neurons a day buy only ~684,000 tokens. Expressing "cannot finish today"
    as infinite time is what sorts it out of the walk without a second
    mechanism.
    """
    bge = next(e for e in MIGRATION if e.model == "@cf/baai/bge-base-en-v1.5")

    assert bge.minutes(**corpus(1_000)) < 2
    assert bge.minutes(**corpus(5_386)) == math.inf


def test_a_model_with_nothing_known_takes_infinite_time():
    """An unknown is not a promise, so it sorts last rather than first."""
    assert fake("mystery", Rate()).minutes(**corpus(100)) == math.inf


def test_by_speed_keeps_every_model():
    """The reason there is ONE list and not two pools.

    A two-pool version was proposed first and was wrong: a fast pool of two
    models, both exhausted, and nowhere left to go. Dropping a model here -
    for being slow, or over its daily budget, or unmeasured - would rebuild
    that dead end, and the walk would fail instead of degrading.
    """
    for chunks in (1, 1_000, 5_386, 100_000):
        order = by_speed(**corpus(chunks))

        assert sorted(named(order)) == sorted(named(MIGRATION)), chunks


def test_models_of_equal_speed_keep_the_strength_order():
    """Ties break by STRENGTH, and that is bought with a stable sort.

    All four Google entries carry identical rates, so nothing about speed can
    separate them. They must come back in MIGRATION's order - embedding-2
    before 001, key 1 before key 2 - or the tie is being broken by luck.
    """
    google = [e for e in MIGRATION if e.model.startswith("gemini-")]
    assert len({(e.rate) for e in google}) == 1  # premise: the rates really tie

    order = [e for e in by_speed(**corpus(5_386)) if e.model.startswith("gemini-")]

    assert order == google


def test_a_faster_model_really_does_sort_earlier():
    slow = fake("slow", Rate(tokens_per_minute=1_000))
    fast = fake("fast", Rate(tokens_per_minute=1_000_000))

    order = by_speed(**corpus(100), candidates=(slow, fast))

    assert named(order) == ["fast", "slow"]


def test_a_learned_limit_beats_the_declared_seed():
    """Observation wins, which is what makes the seed a seed."""
    embedder = fake("m", Rate(requests_per_minute=60))
    before = embedder.minutes(**corpus(5_386))

    rates.learn("m", {"x-ratelimit-limit-req-minute": "6"})

    assert embedder.minutes(**corpus(5_386)) == pytest.approx(before * 10)


def test_a_negative_corpus_is_a_callers_bug():
    """A caller's bug and a provider's failure are different exceptions."""
    embedder = fake("m", Rate(tokens_per_minute=100))

    with pytest.raises(ValueError, match="must not be negative"):
        embedder.minutes(tokens=-1, chunks=10)

    with pytest.raises(ValueError, match="must not be negative"):
        embedder.minutes(tokens=10, chunks=-1)


def test_every_model_in_the_migration_declares_its_facts():
    """SPECS is the one table, so a model missing from it has no facts at all.

    An entry built by hand instead of through _spec() would import fine and
    then sort last for ever, because minutes() would have nothing to work
    with - slow, silent, and indistinguishable from a genuinely slow model.
    """
    missing = sorted({e.model for e in MIGRATION} - set(SPECS))

    assert not missing, missing

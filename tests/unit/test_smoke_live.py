"""The rules the weekly smoke run applies to a live failure.

They sit under unit/ and not smoke/ on purpose: they call no provider, so they
must run on every push, and anything unmarked in smoke/ is refused by the suite
rule that keeps quota-spending tests behind --run-smoke.

Why the rules are worth testing at all: this helper decides what turns the run
red. A bug in it does not fail loudly - it hides failures (a retry that eats a
real 403) or invents them (a busy provider reported dead), and four Mondays of
an always-red run showed how little a red run tells you once it is noisy.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from labpilot.embed import EmbeddingError
from labpilot.llm import CHAIN, KNOWN_DEAD, LLMError
from labpilot.rerank import RerankError
from tests.smoke import live


@pytest.fixture
def waits(monkeypatch):
    """Every sleep the helper asks for, recorded instead of waited out."""
    slept: list[float] = []
    monkeypatch.setattr(live.time, "sleep", slept.append)
    return slept


def scripted(*outcomes):
    """A call that raises or returns each outcome in turn, and counts itself."""
    calls = []

    def call():
        outcome = outcomes[min(len(calls), len(outcomes) - 1)]
        calls.append(outcome)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    call.calls = calls
    return call


def llm(status, **kw):
    return LLMError(f"Tier HTTP {status}", status=status, **kw)


@pytest.mark.parametrize("status", [503, 500, 502])
def test_a_transient_status_is_retried_and_the_answer_comes_back(status, waits):
    call = scripted(llm(status), "answer")

    assert live.call_live(call, name="tier") == "answer"
    assert len(call.calls) == 2
    assert waits == [10.0]


def test_a_tier_that_stays_down_is_a_real_failure_after_every_retry(waits):
    call = scripted(llm(503))

    with pytest.raises(LLMError, match="503"):
        live.call_live(call, name="tier")

    assert len(call.calls) == 3
    assert waits == [10.0, 20.0]


@pytest.mark.parametrize("status", [400, 403, 404])
def test_a_verdict_from_the_provider_is_never_retried(status, waits):
    """A 403 is an account problem and a 404 is a route that is gone. Waiting
    changes neither, and retrying would hide how long it has been broken."""
    call = scripted(llm(status))

    with pytest.raises(LLMError):
        live.call_live(call, name="tier")

    assert len(call.calls) == 1
    assert waits == []


def test_a_missing_key_fails_at_once_instead_of_being_retried(waits):
    """No status AND no network cause. This is exactly what the missing Voyage
    secret looked like, and 16 of them in one run must not cost 30s each."""
    call = scripted(LLMError("Tier: KILO_API_KEY is not set"))

    with pytest.raises(LLMError, match="is not set"):
        live.call_live(call, name="tier")

    assert len(call.calls) == 1
    assert waits == []


def test_a_dropped_connection_is_transient(waits):
    fault = requests.exceptions.ConnectionError("Connection reset by peer")
    wrapped = LLMError("Tier: request failed")
    wrapped.__cause__ = fault

    call = scripted(wrapped, "answer")

    assert live.call_live(call, name="tier") == "answer"
    assert len(call.calls) == 2


def test_a_rate_limit_that_never_clears_is_a_spent_quota_not_a_failure(waits):
    """Mistral, four Mondays running. The tier is fine and the account is
    empty, so it is reported with the provider's own words and not as red."""
    call = scripted(llm(429))

    with pytest.raises(pytest.xfail.Exception, match="still rate limited"):
        live.call_live(call, name="Mistral Medium")

    assert len(call.calls) == 3


def test_a_429_that_resets_tomorrow_is_recognised_at_once(waits):
    """The chain's own test, reused: over a minute to reset means the POOL is
    spent, so there is nothing to wait for."""
    call = scripted(llm(429, retry_after=86_400.0))

    with pytest.raises(pytest.xfail.Exception, match="quota is spent"):
        live.call_live(call, name="Gemini 3.5 Flash")

    assert len(call.calls) == 1
    assert waits == []


def test_a_short_retry_after_is_honoured_when_it_is_longer_than_our_wait(waits):
    call = scripted(llm(429, retry_after=30.0), "answer")

    assert live.call_live(call, name="tier") == "answer"
    assert waits == [30.0]


def test_the_embedder_and_reranker_errors_follow_the_same_rules(waits):
    embed = scripted(EmbeddingError("busy", status=503), "vectors")
    assert live.call_live(embed, name="embedder") == "vectors"

    rank = scripted(RerankError("busy", status=503), "order")
    assert live.call_live(rank, name="reranker") == "order"

    dead = scripted(EmbeddingError("denied", status=403))
    with pytest.raises(EmbeddingError):
        live.call_live(dead, name="embedder")
    assert len(dead.calls) == 1


def test_a_reranker_wrapping_a_spent_llm_pool_is_a_spent_quota(waits):
    """LLMReranker wraps the LLM layer's error, so the pool test has to look
    through the chain of causes or a spent Gemini bucket reads as a failure."""
    wrapper = RerankError("Gemini 3.5 Flash-Lite: 429", status=429)
    wrapper.__cause__ = llm(429, retry_after=86_400.0)

    with pytest.raises(pytest.xfail.Exception, match="quota is spent"):
        live.call_live(scripted(wrapper), name="Gemini 3.5 Flash-Lite")


def test_a_bug_in_the_test_itself_is_not_retried(waits):
    """Only the three provider error types are ours to interpret.

    The fault has a network cause on purpose. A bare ValueError has no status
    and no cause, so it would fail at once under ANY handler and the test could
    never tell a narrow `except` from a broad one.
    """
    bug = ValueError("bad fixture")
    bug.__cause__ = requests.exceptions.ConnectionError("reset")
    call = scripted(bug)

    with pytest.raises(ValueError):
        live.call_live(call, name="tier")

    assert len(call.calls) == 1
    assert waits == []


def test_a_known_dead_route_is_xfailed_from_the_registry_and_no_other_tier_is():
    """The smoke run once kept its own `{"GLM-5.2"}` while the registry named
    four dead routes, so three of them failed every Monday. The list is the
    registry's; this pins that the smoke run really reads it."""
    assert KNOWN_DEAD, "premise: something is dead, or this proves nothing"
    assert set(KNOWN_DEAD) <= {p.name for p in CHAIN}

    for provider in CHAIN:
        case = live.tier_case(provider)
        marked = any(mark.name == "xfail" for mark in case.marks)

        assert marked == (provider.name in KNOWN_DEAD), provider.name


SMOKE = Path(__file__).resolve().parents[1] / "smoke"


@pytest.mark.parametrize(
    "name", ["test_every_tier.py", "test_rerankers.py", "test_embedders.py"]
)
def test_every_live_smoke_file_really_goes_through_the_helper(name):
    """Tested in isolation is not the same as connected.

    Importing these files runs load_dotenv, which unit tests must not do, so
    the wiring is read as text. This project has shipped a component that
    worked and was never called three times: the rerank chain, fusion, and the
    skip gate. A helper nobody calls would leave the run exactly as red as it
    was, and nothing else here would say so.
    """
    source = (SMOKE / name).read_text(encoding="utf-8")

    assert "call_live(" in source, f"{name} makes live calls without call_live"


def test_the_tier_smoke_file_marks_dead_routes_through_the_registry_helper():
    source = (SMOKE / "test_every_tier.py").read_text(encoding="utf-8")

    assert "tier_case(" in source
    assert "KNOWN_DEAD =" not in source, "a private dead-tier list is back"

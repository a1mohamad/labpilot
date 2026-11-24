from types import SimpleNamespace

import pytest

from labpilot.api.chains import for_task
from labpilot.llm import CHAIN, LLMClient, LLMError, routes
from labpilot.prompts import GATE_MAX_TOKENS, SUMMARY_MAX_TOKENS


def names(chain):
    return [provider.name for provider in chain]


def test_a_client_gets_a_copy_that_walks_the_route_of_the_task():
    client = LLMClient(chain=CHAIN, total_budget=5.0)

    led = for_task(client, "claims")

    assert names(led.chain) == names(routes.resolve("claims", CHAIN))
    assert led.call_stop == routes.ROUTES["claims"].stop
    assert led.hedge_after == routes.ROUTES["claims"].hedge
    assert led.total_budget == routes.ROUTES["claims"].budget
    assert client.chain == CHAIN  # the caller's client is not changed


def test_every_task_has_a_route_that_resolves_to_live_tiers():
    for task in routes.ROUTES:
        assert for_task(LLMClient(chain=CHAIN), task).chain, task


def test_a_stand_in_without_a_chain_is_used_as_it_is():
    assert for_task("a stand-in", "claims") == "a stand-in"


def test_a_client_with_its_own_short_chain_keeps_it_and_takes_the_stop():
    # A test with three fake tiers: none is named in a route, so the walk is the
    # client's own, and only the hang stop of the task is added.
    fake = SimpleNamespace(name="fake", model="m")
    client = LLMClient(chain=(fake,))

    led = for_task(client, "audit")

    assert led.chain == (fake,)
    assert led.call_stop == routes.ROUTES["audit"].stop


# ---- the summary and the gate: small jobs that must fit a room --------------


def test_the_summary_route_can_take_a_whole_summary_on_its_last_gemma_tier():
    chain = for_task(LLMClient(chain=CHAIN), "summary").chain
    gemma = [p for p in chain if p.name.startswith("Gemma 4 26B")]

    assert gemma
    for provider in gemma:
        provider._check_fits("x" * 36_000, SUMMARY_MAX_TOKENS)


def test_the_groq_qwen_is_refused_for_free_on_a_summary_but_takes_a_gate_prompt():
    groq = next(
        p
        for p in for_task(LLMClient(chain=CHAIN), "gate").chain
        if p.name == "Qwen3.8 27B (Groq)"
    )

    with pytest.raises(LLMError):
        groq._check_fits("x" * 36_000, SUMMARY_MAX_TOKENS)
    groq._check_fits("x" * 3_000, GATE_MAX_TOKENS)

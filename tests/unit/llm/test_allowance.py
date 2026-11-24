"""A free allowance is left alone before its last part is spent (Token Harbor)."""

from datetime import UTC, datetime, timedelta

import pytest
import responses

from labpilot.llm import KNOWN_DEAD, LLMClient, _health
from labpilot.llm._allowance import UNKNOWN_REST, allowance_key
from labpilot.llm.contracts import LLMResult
from labpilot.llm.errors import AllFreeTiersExhausted
from labpilot.llm.openai_compatible import OpenAICompatibleProvider
from labpilot.llm.registry import CHAIN

URL = "https://metered.test/v1/chat/completions"


@pytest.fixture
def tier(monkeypatch):
    monkeypatch.setenv("METERED_KEY", "k")
    return OpenAICompatibleProvider(
        name="Metered",
        tier=1,
        url=URL,
        model="m",
        api_key_env="METERED_KEY",
        context_window=10_000,
        max_output_tokens=5_000,
        allowance_header="x-used",
        allowance_reset_header="x-resets",
    )


class Other:
    name, tier, api_key_env, pool = "other", 2, "OTHER", "OTHER"

    def complete(self, prompt, *, max_tokens=1, tool=None):
        return LLMResult(text="other", model="other", tier=2)


def reply(used, resets=None, status=200):
    headers = {"x-used": used} | ({"x-resets": resets} if resets else {})
    body = {"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]}
    responses.add(responses.POST, URL, json=body, headers=headers, status=status)


def in_two_days():
    return (datetime.now(UTC) + timedelta(days=2)).isoformat()


@responses.activate
def test_over_90_percent_the_next_call_skips_the_tier(tier):
    reply("91", in_two_days())
    client = LLMClient(chain=(tier, Other()))

    # The answer that brought the header is a good answer and is kept.
    assert client.generate("a").text == "hi"
    later = client.generate("b")

    assert later.text == "other"
    assert "allowance" in later.attempts[0].error
    assert len(responses.calls) == 1


@responses.activate
@pytest.mark.parametrize("used", ["3", "90", "", "n/a"])
def test_up_to_90_percent_or_no_number_the_tier_is_asked_again(tier, used):
    reply(used, in_two_days())
    client = LLMClient(chain=(tier, Other()))

    assert [client.generate(p).text for p in "ab"] == ["hi", "hi"]


@responses.activate
def test_a_nearly_used_allowance_is_not_the_last_resort_either(tier):
    reply("95", in_two_days())
    client = LLMClient(chain=(tier,))
    client.generate("a")

    with pytest.raises(AllFreeTiersExhausted):
        client.generate("b")
    assert len(responses.calls) == 1


@responses.activate
@pytest.mark.parametrize("resets", [None, "soon", "2020-01-01T00:00:00+00:00"])
def test_without_a_usable_reset_time_it_rests_an_hour(tier, resets):
    reply("95", resets)
    LLMClient(chain=(tier,)).generate("a")

    left = _health.left(allowance_key(tier.pool))
    assert UNKNOWN_REST - 5 < left <= UNKNOWN_REST


@responses.activate
def test_a_refused_call_teaches_the_allowance_too(tier):
    reply("99", in_two_days(), status=400)
    LLMClient(chain=(tier, Other())).generate("a")

    assert _health.left(allowance_key(tier.pool)) > 3600


def test_every_token_harbor_tier_is_metered():
    harbor = [p for p in CHAIN if p.api_key_env == "TOKEN_HARBOR_API_KEY"]

    assert [p for p in harbor if p.name not in KNOWN_DEAD]
    for provider in harbor:
        assert provider.allowance_header == "x-th-free-used-pct"
        assert provider.allowance_reset_header == "x-th-free-resets"

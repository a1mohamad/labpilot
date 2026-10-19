import pytest

from labpilot.llm.chain import LLMClient
from labpilot.llm.contracts import LLMResult
from labpilot.llm.defaults import DEFAULT_MAX_REJECTED_ANSWERS
from labpilot.llm.errors import AllFreeTiersExhausted


class FakeProvider:
    def __init__(self, tier, answer, *, key=None):
        self.name = f"Tier {tier}"
        self.tier = tier
        self.api_key_env = key or f"KEY_{tier}"
        self.answer = answer
        self.calls = 0

    @property
    def pool(self):
        return self.api_key_env

    def complete(self, prompt, *, max_tokens=1024, tool=None):
        self.calls += 1
        return LLMResult(text=self.answer, model=self.name, tier=self.tier)


def judge(result):
    return "it says bad" if result.text == "bad" else None


def test_a_rejected_answer_hands_over_to_the_next_tier():
    first, second = FakeProvider(1, "bad"), FakeProvider(2, "good")

    result = LLMClient(chain=(first, second)).generate("go", problem_with=judge)

    assert result.text == "good"
    assert result.tier == 2
    assert [attempt.error for attempt in result.attempts] == [
        "answer rejected: it says bad"
    ]


def test_the_hook_sees_the_answer_of_each_tier():
    seen = []

    def spy(result):
        seen.append(result.text)
        return "no" if result.text == "bad" else None

    chain = (FakeProvider(1, "bad"), FakeProvider(2, "good"))

    LLMClient(chain=chain).generate("go", problem_with=spy)

    assert seen == ["bad", "good"]


def test_an_accepted_answer_stops_the_walk():
    first, second = FakeProvider(1, "good"), FakeProvider(2, "good")

    LLMClient(chain=(first, second)).generate("go", problem_with=judge)

    assert second.calls == 0


def test_without_a_hook_every_answer_is_accepted():
    result = LLMClient(chain=(FakeProvider(1, "bad"),)).generate("go")

    assert result.text == "bad"


def test_a_rejected_tier_is_not_asked_again():
    only = FakeProvider(1, "bad")

    with pytest.raises(AllFreeTiersExhausted):
        LLMClient(chain=(only,)).generate("go", problem_with=judge)

    assert only.calls == 1


def test_a_rejected_answer_does_not_retire_the_quota_pool():
    first = FakeProvider(1, "bad", key="SAME_POOL")
    second = FakeProvider(2, "good", key="SAME_POOL")

    result = LLMClient(chain=(first, second)).generate("go", problem_with=judge)

    assert result.text == "good"
    assert second.calls == 1


def test_the_walk_stops_after_the_limit():
    chain = tuple(FakeProvider(tier, "bad") for tier in range(1, 5))

    with pytest.raises(AllFreeTiersExhausted) as raised:
        LLMClient(chain=chain, max_rejected_answers=2).generate(
            "go", problem_with=judge
        )

    assert [provider.calls for provider in chain] == [1, 1, 0, 0]
    assert len(raised.value.attempts) == 2


def test_the_default_limit_is_three():
    chain = tuple(FakeProvider(tier, "bad") for tier in range(1, 6))

    with pytest.raises(AllFreeTiersExhausted):
        LLMClient(chain=chain).generate("go", problem_with=judge)

    assert DEFAULT_MAX_REJECTED_ANSWERS == 3
    assert [provider.calls for provider in chain] == [1, 1, 1, 0, 0]


def test_a_hook_that_crashes_is_a_bug_and_is_not_swallowed():
    def broken(result):
        raise ValueError("bug in the hook")

    with pytest.raises(ValueError, match="bug in the hook"):
        LLMClient(chain=(FakeProvider(1, "good"),)).generate("go", problem_with=broken)

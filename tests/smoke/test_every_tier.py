import pytest
from dotenv import load_dotenv

from labpilot.llm import CHAIN

load_dotenv()

REASONING_FLOOR = 8192
KNOWN_DEAD = {"GLM-5.2"}


def _case(provider):
    marks = (
        [pytest.mark.xfail(reason="no free allocation on this account", strict=False)]
        if provider.name in KNOWN_DEAD
        else []
    )
    return pytest.param(provider, marks=marks, id=provider.name)


@pytest.mark.smoke
@pytest.mark.parametrize("provider", [_case(p) for p in CHAIN])
def test_every_tier_answers_a_real_prompt(provider):
    budget = min(
        REASONING_FLOOR, provider.max_output_tokens, provider.context_window // 2
    )
    result = provider.complete(
        "Reply with one short sentence: you are online.", max_tokens=budget
    )

    assert result.text
    assert result.tier == provider.tier
    assert result.model

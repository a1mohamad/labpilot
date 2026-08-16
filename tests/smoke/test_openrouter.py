import pytest
from dotenv import load_dotenv

from labpilot.llm import NEMOTRON_3_ULTRA, NORTH_MINI_CODE

load_dotenv()

REASONING_FLOOR = 2048


@pytest.mark.smoke
@pytest.mark.parametrize(
    "provider",
    [NEMOTRON_3_ULTRA, NORTH_MINI_CODE],
    ids=lambda provider: provider.name,
)
def test_openrouter_tier_answers_a_real_prompt(provider):
    result = provider.complete(
        "Reply with one short sentence: you are online.", max_tokens=REASONING_FLOOR
    )

    assert result.text
    assert result.tier == provider.tier
    assert result.model

import pytest
from dotenv import load_dotenv

from labpilot.llm import DEVSTRAL_2, GLM_5_2, MAGISTRAL_SMALL, MISTRAL_MEDIUM

load_dotenv()

REASONING_FLOOR = 8192


@pytest.mark.smoke
@pytest.mark.parametrize(
    "provider",
    [GLM_5_2, MISTRAL_MEDIUM, MAGISTRAL_SMALL, DEVSTRAL_2],
    ids=lambda provider: provider.name,
)
def test_mistral_tier_answers_a_real_prompt(provider):
    result = provider.complete(
        "Reply with one short sentence: you are online.", max_tokens=REASONING_FLOOR
    )

    assert result.text
    assert result.model

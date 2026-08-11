import pytest
from dotenv import load_dotenv

from labpilot.llm import DEVSTRAL_2, GLM_5_2

load_dotenv()


@pytest.mark.smoke
@pytest.mark.parametrize(
    "provider",
    [GLM_5_2, DEVSTRAL_2],
    ids=lambda provider: provider.name,
)
def test_mistral_tier_answers_a_real_prompt(provider):
    result = provider.complete(
        "Reply with one short sentence: you are online.", max_tokens=64
    )

    assert result.text
    assert result.model

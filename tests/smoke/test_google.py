import pytest
from dotenv import load_dotenv

from labpilot.llm import GEMINI_3_5_FLASH, GEMINI_3_6_FLASH

load_dotenv()


@pytest.mark.smoke
@pytest.mark.parametrize(
    "provider",
    [GEMINI_3_6_FLASH, GEMINI_3_5_FLASH],
    ids=lambda provider: provider.name,
)
def test_gemini_tier_answers_a_real_prompt(provider):
    result = provider.complete(
        "Reply with one short sentence: you are online.", max_tokens=512
    )

    assert result.text
    assert "gemini" in result.model.lower()

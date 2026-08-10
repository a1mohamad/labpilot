import pytest
from dotenv import load_dotenv

from labpilot.llm import NEMOTRON_3_ULTRA

load_dotenv()


@pytest.mark.smoke
def test_tier1_answers_a_real_prompt():
    result = NEMOTRON_3_ULTRA.complete(
        "Reply with one short sentence: you are online.", max_tokens=64
    )

    assert result.text
    assert result.tier == 1
    assert "nemotron" in result.model.lower()
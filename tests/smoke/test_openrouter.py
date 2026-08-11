import pytest
from dotenv import load_dotenv

from labpilot.llm import NEMOTRON_3_ULTRA, NORTH_MINI_CODE

load_dotenv()


@pytest.mark.smoke
def test_tier4_answers_a_real_prompt():
    result = NEMOTRON_3_ULTRA.complete(
        "Reply with one short sentence: you are online.", max_tokens=64
    )

    assert result.text
    assert result.tier == 4
    assert "nemotron" in result.model.lower()


@pytest.mark.smoke
def test_tier6_answers_a_real_prompt():
    result = NORTH_MINI_CODE.complete(
        "Reply with one short sentence: you are online.", max_tokens=64
    )

    assert result.text
    assert result.tier == 6
    assert "cohere" in result.model.lower()

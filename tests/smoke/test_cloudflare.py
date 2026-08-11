import pytest
from dotenv import load_dotenv

from labpilot.llm import GPT_OSS_120B

load_dotenv()


@pytest.mark.smoke
def test_tier7_answers_a_real_prompt():
    result = GPT_OSS_120B.complete(
        "Reply with one short sentence: you are online.", max_tokens=800
    )

    assert result.text
    assert result.tier == 7
    assert "gpt-oss" in result.model.lower()

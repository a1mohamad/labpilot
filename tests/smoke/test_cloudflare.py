import pytest
from dotenv import load_dotenv

from labpilot.llm import GPT_OSS_120B

load_dotenv()

REASONING_FLOOR = 2048


@pytest.mark.smoke
def test_cloudflare_tier_answers_a_real_prompt():
    result = GPT_OSS_120B.complete(
        "Reply with one short sentence: you are online.", max_tokens=REASONING_FLOOR
    )

    assert result.text
    assert result.tier == GPT_OSS_120B.tier
    assert "gpt-oss" in result.model.lower()

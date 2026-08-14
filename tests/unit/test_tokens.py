import pytest

from labpilot.tokens import estimate_tokens


@pytest.mark.parametrize(("text", "expected"), [("", 0), ("abc", 1), ("abcd", 2)])
def test_estimate_tokens_rounds_up(text, expected):
    assert estimate_tokens(text) == expected

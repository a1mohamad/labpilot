from __future__ import annotations

import pytest

from labpilot.llm._text import estimate_tokens, truncate


@pytest.mark.parametrize(("text", "expected"), [("", 0), ("abc", 1), ("abcd", 2)])
def test_estimate_tokens_rounds_up(text, expected):
    assert estimate_tokens(text) == expected


def test_truncate_leaves_short_text_alone():
    assert truncate("short", limit=10) == "short"


def test_truncate_marks_text_it_cut():
    assert truncate("abcdefghij", limit=4) == "abcd…"

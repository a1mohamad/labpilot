from __future__ import annotations

from labpilot._text import truncate


def test_truncate_leaves_short_text_alone():
    assert truncate("short", limit=10) == "short"


def test_truncate_marks_text_it_cut():
    assert truncate("abcdefghij", limit=4) == "abcd…"

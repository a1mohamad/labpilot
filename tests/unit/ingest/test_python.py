from __future__ import annotations

from labpilot.ingest._python import split_python

SOURCE = """import os

CONSTANT = 1


def small(a):
    return a + 1


@decorator
def decorated(b):
    return b


class Holder:
    def method(self):
        return 2
"""

BIG_CLASS = "class Big:\n" + "\n".join(
    f"    def method_{i}(self):\n        return {i}  # {'x' * 100}\n" for i in range(20)
)


def _labels(text: str) -> list[str]:
    return [piece.label for piece in split_python(text)]


def test_each_top_level_definition_is_its_own_piece():
    assert _labels(SOURCE) == ["", "def small", "def decorated", "class Holder"]


def test_a_decorator_stays_with_its_function():
    piece = next(p for p in split_python(SOURCE) if p.label == "def decorated")
    assert piece.text.startswith("@decorator")


def test_a_small_class_is_not_split_into_methods():
    assert "class Holder · def method" not in _labels(SOURCE)


def test_an_oversized_class_splits_per_method():
    labels = _labels(BIG_CLASS)
    assert "class Big · def method_0" in labels
    assert "class Big · def method_19" in labels


def test_module_level_code_becomes_a_piece_with_no_label():
    first = split_python(SOURCE)[0]
    assert first.label == ""
    assert "import os" in first.text


def test_line_numbers_point_at_the_text():
    lines = SOURCE.splitlines()
    for piece in split_python(SOURCE):
        assert piece.text == "\n".join(lines[piece.start_line - 1 : piece.end_line])


def test_an_unparseable_file_falls_back_instead_of_raising():
    pieces = split_python("def broken(:\n    this is not python")
    assert pieces
    assert all(piece.label == "" for piece in pieces)


def test_an_empty_file_yields_no_pieces():
    assert split_python("") == []

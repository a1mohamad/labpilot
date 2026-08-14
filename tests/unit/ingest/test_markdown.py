from __future__ import annotations

from labpilot.ingest._markdown import split_markdown

FENCE = "`" * 3

DOC = f"""preamble line

# Title

title body

## 4.1 Setup

setup body

{FENCE}python
# this is a comment, not a header
x = 1
{FENCE}

tail of setup
"""


def _labels(text: str) -> list[str]:
    return [piece.label for piece in split_markdown(text)]


def test_text_before_the_first_header_becomes_its_own_piece():
    first = split_markdown(DOC)[0]
    assert first.label == ""
    assert first.text == "preamble line"


def test_labels_are_the_header_text_without_the_hashes():
    assert _labels(DOC) == ["", "Title", "4.1 Setup"]


def test_a_hash_inside_a_code_fence_is_not_a_header():
    assert "this is a comment, not a header" not in _labels(DOC)


def test_the_header_line_stays_inside_its_section():
    assert split_markdown(DOC)[1].text.startswith("# Title")


def test_line_numbers_point_at_the_text():
    lines = DOC.splitlines()
    for piece in split_markdown(DOC):
        assert piece.text == "\n".join(lines[piece.start_line - 1 : piece.end_line])


def test_a_file_with_no_headers_is_one_piece():
    pieces = split_markdown("just prose\n\nmore prose")
    assert len(pieces) == 1
    assert pieces[0].label == ""


def test_an_empty_file_yields_no_pieces():
    assert split_markdown("") == []

from __future__ import annotations

import pytest

from labpilot.ingest._plain import load_text
from labpilot.ingest.errors import LoaderError, NotUtf8Text


def test_utf8_bytes_become_the_same_text():
    body = "lr = 3e-4  # α ≤ 0.05, تست\n"

    assert load_text(body.encode("utf-8")) == body


def test_bytes_that_are_not_utf8_are_refused_never_returned_mangled():
    with pytest.raises(NotUtf8Text):
        load_text(b"# caf\xe9 in latin-1\nx = 2\n")


def test_the_refusal_carries_the_byte_that_failed():
    with pytest.raises(NotUtf8Text, match="0xe9"):
        load_text(b"# caf\xe9\n")


def test_the_refusal_is_a_loader_error_so_existing_callers_still_catch_it():
    assert issubclass(NotUtf8Text, LoaderError)


def test_a_byte_order_mark_is_stripped():
    assert load_text("\ufeff".encode("utf-8") + b"import os\n") == "import os\n"

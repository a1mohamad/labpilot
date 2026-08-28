from __future__ import annotations

import json

import pytest

from labpilot.ingest._notebook import load_notebook, split_notebook
from labpilot.ingest.errors import LoaderError


def notebook(*cells: dict) -> str:
    return json.dumps({"cells": list(cells), "nbformat": 4, "nbformat_minor": 5})


def code(source, outputs=None, execution_count=1) -> dict:
    return {
        "cell_type": "code",
        "source": source,
        "outputs": outputs or [],
        "execution_count": execution_count,
        "metadata": {},
    }


def markdown(source) -> dict:
    return {"cell_type": "markdown", "source": source, "metadata": {}}


def stream(text) -> dict:
    return {"output_type": "stream", "name": "stdout", "text": text}


def test_a_code_cell_keeps_its_source():
    text = load_notebook(notebook(code(["x = 1\n", "y = 2\n"])))

    assert "x = 1\ny = 2" in text


def test_lines_are_joined_without_doubling_the_newlines():
    text = load_notebook(notebook(code(["a = 1\n", "b = 2\n"])))

    assert "a = 1\n\nb = 2" not in text


def test_a_markdown_cell_is_kept():
    text = load_notebook(notebook(markdown(["## Training\n", "We use lr 3e-4.\n"])))

    assert "## Training" in text
    assert "We use lr 3e-4." in text


def test_printed_output_is_kept_because_the_run_numbers_live_there():
    text = load_notebook(
        notebook(code(["train()\n"], [stream(["epoch 1 f1 0.8226\n"])]))
    )

    assert "epoch 1 f1 0.8226" in text


def test_an_execute_result_keeps_its_text_but_an_image_is_dropped():
    payload = "iVBORw0KGgoAAAANSUhEUg" * 100
    cell = code(
        ["plot()\n"],
        [
            {
                "output_type": "display_data",
                "data": {"image/png": payload, "text/plain": "<Figure size 640x480>"},
                "metadata": {},
            }
        ],
    )

    text = load_notebook(notebook(cell))

    assert "<Figure size 640x480>" in text
    assert payload not in text
    assert "iVBORw0KGgo" not in text


def test_an_image_only_output_leaves_no_trace():
    cell = code(
        ["plot()\n"], [{"output_type": "display_data", "data": {"image/png": "AAAA"}}]
    )

    text = load_notebook(notebook(cell))

    assert "AAAA" not in text
    assert "# --- output ---" not in text


def test_a_failed_cell_reports_its_error():
    cell = code(
        ["model(x)\n"],
        [{"output_type": "error", "ename": "ValueError", "evalue": "shape mismatch"}],
    )

    text = load_notebook(notebook(cell))

    assert "ValueError: shape mismatch" in text


def test_a_cell_that_never_ran_is_marked_as_such():
    text = load_notebook(notebook(code(["x = 1\n"], execution_count=None)))

    assert "not run" in text


def test_cell_numbers_follow_the_notebook_even_when_a_cell_is_empty():
    text = load_notebook(
        notebook(code(["first\n"]), code([]), markdown(["## Third\n"]))
    )

    assert "# %% cell 1 [code]" in text
    assert "# %% cell 3 [markdown]" in text
    assert "cell 2" not in text


@pytest.mark.parametrize(
    "raw",
    ["", "not json at all", "[1, 2, 3]", '{"nbformat": 4}', '{"cells": "nope"}'],
)
def test_something_that_is_not_a_notebook_is_refused_never_returned_raw(raw):
    with pytest.raises(LoaderError):
        load_notebook(raw)


def loaded(*cells: dict) -> str:
    return load_notebook(notebook(*cells))


def test_every_cell_becomes_exactly_one_piece():
    text = loaded(code(["a = 1\n"]), markdown(["## Two\n"]), code(["b = 2\n"]))

    pieces = split_notebook(text)

    assert [piece.label for piece in pieces] == [
        "cell 1 code",
        "cell 2 markdown",
        "cell 3 code",
    ]


def test_a_cell_keeps_its_marker_and_its_body_together():
    pieces = split_notebook(loaded(code(["a = 1\n"], [stream(["done\n"])])))

    assert pieces[0].text.startswith("# %% cell 1 [code]")
    assert "a = 1" in pieces[0].text
    assert "done" in pieces[0].text


def test_line_numbers_point_at_the_real_lines():
    text = loaded(code(["a = 1\n"]), code(["b = 2\n"]))
    lines = text.splitlines()

    for piece in split_notebook(text):
        assert "\n".join(lines[piece.start_line - 1 : piece.end_line]) == piece.text


def test_no_cell_is_lost_and_none_is_split_in_two():
    cells = [code([f"x = {n}\n"]) for n in range(12)]

    pieces = split_notebook(loaded(*cells))

    assert len(pieces) == 12
    for n in range(12):
        assert f"x = {n}" in pieces[n].text


def test_text_with_no_markers_yields_one_piece_not_zero():
    pieces = split_notebook("just some text\nwith two lines")

    assert len(pieces) == 1
    assert pieces[0].label == ""


def test_an_empty_notebook_yields_no_pieces():
    assert split_notebook(load_notebook(notebook())) == []

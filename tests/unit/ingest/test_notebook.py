from __future__ import annotations

import json

import pytest

from labpilot.ingest._notebook import load_notebook
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

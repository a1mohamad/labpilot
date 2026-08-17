from labpilot.ingest import Chunk
from labpilot.prompts import FULL, find_citations, resolve
from labpilot.prompts.citations import unescape

BODY = "def fit():\n    loss.backward()\n    step()"


def _chunks(text: str = BODY, start_line: int = 100) -> tuple[Chunk, ...]:
    return (
        Chunk(
            text=text,
            source="train.py",
            start_line=start_line,
            end_line=start_line + text.count("\n"),
            side="B",
            artifact_id="a",
            chunk_index=0,
        ),
    )


def test_a_quote_resolves_to_its_real_line_and_our_own_text():
    found = resolve("B-0", "loss.backward()", _chunks())

    assert found.source == "train.py"
    assert found.line == 101
    assert found.text == "    loss.backward()"
    assert found.unique


def test_an_id_that_does_not_exist_is_rejected():
    assert resolve("B-9", "loss.backward()", _chunks()) is None


def test_a_quote_that_is_not_in_the_part_is_rejected():
    assert resolve("B-0", "optimizer.zero_grad()", _chunks()) is None


def test_an_empty_quote_is_rejected():
    assert resolve("B-0", "   ", _chunks()) is None


def test_a_quote_inside_a_longer_line_still_resolves():
    chunks = _chunks("a = 1\nloss.backward()  # step here")

    found = resolve("B-0", "loss.backward()", chunks)

    assert found.line == 101
    assert found.text == "loss.backward()  # step here"


def test_a_line_that_appears_twice_is_marked_not_unique():
    chunks = _chunks("return None\nx = 1\nreturn None")

    found = resolve("B-0", "return None", chunks)

    assert found.line == 100
    assert not found.unique


def test_citations_are_pulled_out_of_an_answer():
    answer = 'D1 the step is missing [B-17 "loss.backward()"] and [A-3 "print("x")"]'

    assert find_citations(answer) == [
        ("B-17", "loss.backward()"),
        ("A-3", 'print("x")'),
    ]


def test_several_citations_inside_one_bracket_are_all_found():
    answer = '[B-2 "class SystemConfig:", B-3 "class PathConfig:"]'

    assert find_citations(answer) == [
        ("B-2", "class SystemConfig:"),
        ("B-3", "class PathConfig:"),
    ]


def test_a_quote_that_spans_a_wrapped_line_still_resolves():
    chunks = _chunks("On the Quora benchmark the model\nreaches 0.878 accuracy.")

    found = resolve("B-0", "the model reaches 0.878 accuracy.", chunks)

    assert found.line == 100


def test_our_own_example_citation_can_be_parsed():
    assert find_citations(FULL.header) == [("B-17", "count = count + 1")]


def test_a_quote_escaped_for_a_markdown_table_still_resolves():
    chunks = _chunks('        SCHEDULER_TYPE = "ReduceLROnPlateau"')
    found = resolve("B-0", '        SCHEDULER_TYPE = \\"ReduceLROnPlateau\\"', chunks)

    assert found is not None
    assert found.text == '        SCHEDULER_TYPE = "ReduceLROnPlateau"'


def test_an_escaped_pipe_inside_a_quoted_row_still_resolves():
    chunks = _chunks("| acc 0.8649 | P 0.7869 | F1 0.8262 |")

    assert resolve("B-0", r"\| acc 0.8649 \| P 0.7869 \| F1 0.8262 \|", chunks)


def test_a_backslash_that_is_part_of_the_code_is_not_removed():
    assert (
        unescape(r'text = re.sub(r"\n", " ", text)')
        == r'text = re.sub(r"\n", " ", text)'
    )


def test_unescaping_never_rescues_a_quote_that_is_simply_wrong():
    chunks = _chunks("        LEARNING_RATE = 3e-4")

    assert resolve("B-0", "        LEARNING_RATE = 1e-3", chunks) is None

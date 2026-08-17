import re

from labpilot.prompts import COMPARE, CORE, FULL, PRIOR_HEADING, REPORT, SCAN

EVERY = (FULL, CORE, REPORT, SCAN, COMPARE)
LEAN = (REPORT, SCAN, COMPARE)
LEGACY = (FULL, CORE)

# Reported collapse in instruction adherence begins around 2KB, and our own
# 6.5-13KB templates scored no better than a bare prompt. This guards against
# regrowth, not against the last hundred bytes.
COLLAPSE_BYTES = 2200

BANNED = (
    "python",
    "pytorch",
    "tensorflow",
    "keras",
    "numpy",
    "pandas",
    "javascript",
    "rust",
    "notebook",
    "repository",
    "commit",
    "epoch",
    "hyperparameter",
    "neural",
    "tensor",
    "gradient",
    "dataset",
    "function",
    "class",
    "variable",
)


def _numbers(text: str) -> set[int]:
    return {int(found) for found in re.findall(r"§(\d+)", text)}


def _whole(instructions) -> str:
    return f"{instructions.header}\n{instructions.closing}"


def test_the_instructions_name_no_language_and_no_field():
    for instructions in EVERY:
        text = _whole(instructions).lower()
        found = [word for word in BANNED if re.search(rf"\b{word}\b", text)]
        assert not found, f"{instructions.name} contains {found}"


def test_the_closing_names_the_same_sections_as_the_header():
    for instructions in EVERY:
        assert _numbers(instructions.closing) == _numbers(instructions.header)


def test_every_working_template_stays_under_the_collapse_size():
    for instructions in LEAN:
        size = len(_whole(instructions).encode())
        assert size < COLLAPSE_BYTES, f"{instructions.name} is {size} bytes"


def test_the_kept_baselines_are_the_ones_over_the_collapse_size():
    for instructions in LEGACY:
        assert len(_whole(instructions).encode()) > COLLAPSE_BYTES, instructions.name


def test_every_template_asks_for_the_one_citation_shape_we_can_resolve():
    for instructions in EVERY:
        whole = _whole(instructions)
        assert 'B-17 "' in whole, instructions.name
        assert "Never write a line number" in whole, instructions.name


def test_the_working_templates_ask_only_for_what_can_move_a_result():
    for instructions in LEAN:
        whole = _whole(instructions)
        assert "could change the numbers" in whole, instructions.name
        assert "dead, cosmetic, or unable to move a result" in whole, instructions.name


def test_the_working_templates_allow_comparing_two_numbers_from_one_side():
    for instructions in LEAN:
        assert "same run are always fair to compare" in _whole(instructions)


def test_report_and_compare_keep_all_fourteen_sections():
    for instructions in (REPORT, COMPARE):
        assert _numbers(instructions.header) == set(range(14)), instructions.name


def test_report_and_compare_keep_the_gate_that_can_stop_the_report():
    for instructions in (REPORT, COMPARE):
        header = instructions.header
        assert "CORRESPONDENCE" in header, instructions.name
        assert "If NONE, stop here" in header, instructions.name


def test_report_reads_b_before_it_compares():
    assert "Read B on its own first" in REPORT.header
    assert "already been read on its own" in COMPARE.header


def test_scan_never_mentions_a_second_side():
    whole = _whole(SCAN)
    assert "side A" not in whole
    assert not re.search(r"\bA-\d", whole)
    assert "nothing to compare it against" in whole


def test_scan_asks_for_problems_and_for_the_arithmetic_between_numbers():
    header = SCAN.header
    assert "NUMBERS IT REPORTS" in header
    assert "PROBLEMS" in header
    assert "Subtract them" in header


def test_compare_carries_forward_what_the_scan_pass_found():
    assert PRIOR_HEADING in COMPARE.header
    assert "carry over every problem" in COMPARE.header

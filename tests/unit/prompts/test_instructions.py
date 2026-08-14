import re

from labpilot.prompts import CORE, FULL

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


def test_the_instructions_name_no_language_and_no_field():
    for instructions in (FULL, CORE):
        text = f"{instructions.header}\n{instructions.closing}".lower()
        found = [word for word in BANNED if re.search(rf"\b{word}\b", text)]
        assert not found, f"{instructions.name} contains {found}"


def test_full_asks_for_every_section_from_0_to_13():
    assert _numbers(FULL.header) == set(range(14))


def test_core_asks_for_fewer_sections_than_full():
    assert len(_numbers(CORE.header)) < len(_numbers(FULL.header))


def test_both_templates_walk_both_part_lists():
    for instructions in (FULL, CORE):
        text = instructions.header.lower()
        assert "side a's part list" in text, instructions.name
        assert "side b's part list" in text, instructions.name


def test_both_templates_demand_a_line_for_every_id():
    for instructions in (FULL, CORE):
        whole = f"{instructions.header}\n{instructions.closing}".lower()
        assert "every id" in whole, instructions.name
        assert "do not skip an id" in whole, instructions.name


def test_both_templates_forbid_rejoining_two_values_they_could_not_compare():
    for instructions in (FULL, CORE):
        text = instructions.header.lower()
        assert "never appear in the same sentence" in text, instructions.name
        assert "do not subtract them" in text, instructions.name


def test_core_scans_b_alone_before_it_compares_the_two_sides():
    header = CORE.header
    assert header.index("PROBLEMS IN B ALONE") < header.index("§5  DIFFERENCES")


def test_core_collects_every_walk_line_into_the_difference_table():
    assert "must appear here as a row" in CORE.header


def test_the_closing_names_the_same_sections_as_the_header():
    for instructions in (FULL, CORE):
        assert _numbers(instructions.closing) == _numbers(instructions.header)

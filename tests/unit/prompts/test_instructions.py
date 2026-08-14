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


def test_core_asks_for_far_fewer_sections_than_full():
    assert len(_numbers(CORE.header)) * 2 <= len(_numbers(FULL.header))


def test_the_closing_names_the_same_sections_as_the_header():
    for instructions in (FULL, CORE):
        assert _numbers(instructions.closing) == _numbers(instructions.header)

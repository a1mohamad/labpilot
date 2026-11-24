import re

from labpilot import prompts
from labpilot.prompts import CHAT, ONE_FILE, REFERENCE, TWO_FILES
from labpilot.prompts.instructions import Instructions

EVERY = (CHAT, ONE_FILE, REFERENCE, TWO_FILES)

BANNED = (
    "python",
    "pytorch",
    "tensorflow",
    "keras",
    "numpy",
    "pandas",
    "javascript",
    "rust",
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


def _whole(instructions) -> str:
    return f"{instructions.header}\n{instructions.closing}"


def test_the_instructions_name_no_language_and_no_field():
    for instructions in EVERY:
        text = _whole(instructions).lower()
        found = [word for word in BANNED if re.search(rf"\b{word}\b", text)]
        assert not found, f"{instructions.name} contains {found}"


def test_no_instruction_has_a_line_that_starts_with_a_stray_plus():
    # A "+" glued to the first word of a line is a diff marker that was typed
    # into the text, and the model reads it. Found in CLAIMS on 2026-10-24.
    stray = []
    for name, value in vars(prompts).items():
        if name.startswith("_"):
            continue
        if isinstance(value, Instructions):
            text = f"{value.header}\n{value.closing}"
        elif isinstance(value, str):
            text = value
        else:
            continue
        stray += [
            f"{name}: {line[:40]}"
            for line in text.splitlines()
            if re.match(r"\+\S", line)
        ]

    assert stray == []

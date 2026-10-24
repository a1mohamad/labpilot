import re
from collections.abc import Sequence

# A header names its unit: "[train.py · class Trainer · def fit · lines 1-9]".
_DEFINED = re.compile(r"(?:^|·)\s*def ([A-Za-z_]\w*)")
# A part can also hold whole methods its header does not name (a small class
# is one part): "    def pos_class_weight(self, device):". 2026-10-24: this one
# was missed, because only the headers were read.
_DEF_LINE = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(", re.M)
# Names a framework calls by itself, so "never named" says nothing about them:
# PyTorch calls forward() through model(x), unittest calls setUp. Names that
# start with test_ or on_ (pytest tests, framework callbacks) are left out too.
FRAMEWORK_HOOKS = frozenset(
    {
        "forward",
        "backward",
        "extra_repr",
        "training_step",
        "validation_step",
        "test_step",
        "predict_step",
        "configure_optimizers",
        "setUp",
        "tearDown",
        "setUpClass",
        "tearDownClass",
    }
)


def _called_by_a_framework(name: str) -> bool:
    return name in FRAMEWORK_HOOKS or name.startswith(("test_", "on_"))


def unused_definitions(parts: Sequence[tuple[str, str]]) -> dict[str, str]:
    """The functions a file defines and never names anywhere else.

    `parts` are (header, text) pairs of ONE file or artifact, in any order.
    The names come from the headers, which only the Python splitter labels, so
    other languages get none. A name counts as used when it appears anywhere
    outside its own `def` line, so a call, a reference or a decorator all
    count. Dunder methods are left out, because the language calls them.

    The result maps each unused name to the header of the part that defines it.
    "Never named again" is a fact about the text: a framework may still call a
    method by its name (a hook), so the reader of this fact decides.
    """
    defined: dict[str, str] = {}
    for header, text in parts:
        for name in (*_DEFINED.findall(header), *_DEF_LINE.findall(text)):
            if name.startswith("__") and name.endswith("__"):
                continue
            if _called_by_a_framework(name):
                continue
            defined.setdefault(name, header)

    unused: dict[str, str] = {}
    for name, header in defined.items():
        word = re.compile(rf"\b{re.escape(name)}\b")
        own_line = re.compile(rf"^\s*(?:async\s+)?def\s+{re.escape(name)}\b")
        named = any(
            word.search(line) and not own_line.match(line)
            for _, text in parts
            for line in text.splitlines()
        )
        if not named:
            unused[name] = header
    return unused


# A setting written as a constant: "CLIP_NORM = 1.5", "    LR: float = 3e-4".
_CONSTANT_SET = re.compile(r"^\s*([A-Z][A-Z0-9_]+)\s*(?::[^=\n]*)?=(?!=)", re.M)
_CONSTANT_NAMED = re.compile(r"\b([A-Z][A-Z0-9_]+)\b")


def constant_definitions(parts: Sequence[tuple[str, str]]) -> dict[str, str]:
    """Where each constant of a file is SET: name -> the key of its part.

    `parts` are (key, text) pairs. The first part that sets a name wins, so
    an overlapping copy of the same line in the next part changes nothing.
    """
    found: dict[str, str] = {}
    for key, text in parts:
        for name in _CONSTANT_SET.findall(text):
            found.setdefault(name, key)
    return found


def constants_named(text: str) -> list[str]:
    """The constants a text names, in order, each once."""
    return list(dict.fromkeys(_CONSTANT_NAMED.findall(text)))

import re
from collections.abc import Sequence

# A header names its unit: "[train.py · class Trainer · def fit · lines 1-9]".
_DEFINED = re.compile(r"(?:^|·)\s*def ([A-Za-z_]\w*)")


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
    for header, _ in parts:
        for name in _DEFINED.findall(header):
            if not (name.startswith("__") and name.endswith("__")):
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

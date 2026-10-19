from __future__ import annotations

import re

# How many characters of its own text a part may bring to the map: enough for a
# signature and the first line of its docstring, or for the first sentence of a
# section. The caller asks the store for exactly this many, and this module
# needs the SAME number to tell a text that was cut from one that was whole, so
# the number lives here and the caller passes it on - a second copy in store/
# could drift away from it with nothing failing.
OPENING_CHARS = 300

# The longest signature or first sentence the map will show for one row.
_ROW_CHARS = 110

# What the Python splitter writes for a function or a class. Anything else (a
# section title, a page, a cell) is read as prose.
_DEFINITION = re.compile(r"^(def|class) (\S+)$")
_DOCSTRING = re.compile(r"""^[rRuU]?("{3}|'{3})(.*)$""")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s")
# Lines that are not a sentence: headings, tables, code fences, rules, tags.
_NOT_PROSE = ("#", "|", "```", "<", "---", "===")
# A display formula between two "$$" (or one that the opening cut in half) is
# not a sentence. A line that starts with ONE "$" is prose with a formula in
# it, and stays.
_DISPLAY_MATH = re.compile(r"\$\$.*?(?:\$\$|\Z)", re.DOTALL)


def describe(name: str, opening: str) -> tuple[str, str]:
    """(signature, note) for a unit, from the first characters of its text.

    Both are empty when nothing can be read with confidence: an unknown name
    kind, no opening, or an opening that does not contain what the name says.
    A wrong hint is worse than none, so every path that is unsure returns "".
    """
    if not opening.strip():
        return "", ""
    truncated = len(opening) >= OPENING_CHARS
    definition = _DEFINITION.match(name)
    if definition:
        kind, ident = definition.groups()
        return _definition(kind, ident, opening, truncated)
    return "", _section(name, opening, truncated)


def _definition(
    kind: str, ident: str, opening: str, truncated: bool
) -> tuple[str, str]:
    """The def or class line, with its decorators, and one line of its docstring.

    The line is searched for BY NAME, not assumed to be first: the chunker can
    merge a tiny function into its neighbour, and then the text starts with
    someone else's code while the label names this one.
    """
    lines = opening.splitlines()
    head = re.compile(rf"^\s*(?:async\s+)?{kind}\s+{re.escape(ident)}\b")
    start = next((i for i, line in enumerate(lines) if head.match(line)), None)
    if start is None:
        return "", ""

    decorators = [line.strip() for line in lines[:start] if line.strip()[:1] == "@"]
    signature, end = lines[start].strip(), start
    # A long signature continues on the next lines until its brackets close.
    while signature.count("(") > signature.count(")") and end + 1 < len(lines):
        end += 1
        signature += " " + lines[end].strip()
    unfinished = signature.count("(") > signature.count(")")
    signature = " ".join(" ".join([*decorators, signature]).split())
    # A signature written over several lines leaves "( self," and ", )" behind.
    signature = signature.replace("( ", "(").replace(", )", ")").replace(" )", ")")
    signature = _short(signature.removesuffix(":"), cut=unfinished)

    return signature, _docstring(lines[end + 1 :], truncated)


def _docstring(lines: list[str], truncated: bool) -> str:
    """The first line of the docstring, only if it is whole."""
    rest = [line.strip() for line in lines if line.strip()]
    found = _DOCSTRING.match(rest[0]) if rest else None
    if not found:
        return ""

    quote, text = found.groups()
    position = 0
    if not text.strip():  # the quotes stand alone and the words start below
        if len(rest) < 2:
            return ""
        position, text = 1, rest[1]

    # The line is whole when its closing quotes are on it, when a line follows
    # it, or when the opening was not cut at all.
    whole = quote in text or position + 1 < len(rest) or not truncated
    text = text.split(quote)[0].strip()
    return _short(text.replace('"', "'"), cut=not whole) if text else ""


def _section(name: str, opening: str, truncated: bool) -> str:
    """The first sentence under a Markdown heading whose text is `name`.

    Only a heading that MATCHES the name is trusted. A notebook cell, a PDF page
    and a code comment can all start with "#" or with text, and a first line
    like "import torch" is not what the unit is about.
    """
    lines = opening.splitlines()
    heading = next((i for i, line in enumerate(lines) if _heading(line) == name), None)
    if heading is None:
        return ""

    paragraph: list[str] = []
    closed = False
    below = _DISPLAY_MATH.sub("", "\n".join(lines[heading + 1 :]))
    for line in below.splitlines():
        text = line.strip()
        if text and not text.startswith(_NOT_PROSE):
            paragraph.append(text)
            continue
        if paragraph:
            closed = True
            break

    prose = " ".join(paragraph).strip("*_> ")
    if not prose:
        return ""
    end = _SENTENCE_END.search(prose)
    sentence = prose[: end.start()] if end else prose
    whole = end is not None or closed or not truncated
    return _short(sentence.replace('"', "'"), cut=not whole)


def _heading(line: str) -> str:
    text = line.strip()
    if not text.startswith("#"):
        return ""
    return text.lstrip("#").strip()


def _short(text: str, *, cut: bool = False) -> str:
    """The text, or its first words and "…" when it is too long or was cut.

    A cut text may end in the middle of a word, so the last word is dropped
    rather than shown half-written.
    """
    if len(text) > _ROW_CHARS:
        text, cut = text[:_ROW_CHARS], True
    if not cut:
        return text
    words = text.rpartition(" ")[0] or text
    return f"{words.rstrip(' ,')} …"

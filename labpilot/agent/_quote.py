import re
from collections.abc import Sequence

_SPACES = re.compile(r"\s+")
_MARKS = re.compile(r"[\\$*]")


def _plain(text: str) -> str:
    # A model does not copy letter by letter. It may leave out the backslash of an
    # escaped table pipe, the dollar signs of a formula or the stars of bold text,
    # and it writes one space where the source has a line break. None of these is
    # a wrong quote, so both sides are cleaned in the same way before they meet.
    return _SPACES.sub(" ", _MARKS.sub("", text)).strip().casefold()


def has_quote(part: str, quote: str) -> bool:
    wanted = _plain(quote)
    return bool(wanted) and wanted in _plain(part)


MIN_PIECE_CHARS = 9


def place_quote(part: int, quote: str, texts: Sequence[str]) -> tuple[int, str] | None:
    """Where the quote really is: (part, quote), or None when it is in no part.

    A model often names the wrong part of the same call, or joins two lines
    with "..." (measured: 15 of 19 such quotes were placed again). So: the named
    part first, then any part, then the first piece of the quote, the same way.
    """
    order = [part, *(i for i in range(len(texts)) if i != part)]
    pieces = [
        piece.strip()
        for piece in quote.replace("...", "\n").splitlines()
        if len(piece.strip()) >= MIN_PIECE_CHARS
    ]

    for wanted in (quote, *pieces[:1]):
        for i in order:
            if has_quote(texts[i], wanted):
                return i, wanted.strip()
    return None

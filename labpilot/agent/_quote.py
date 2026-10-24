import re

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

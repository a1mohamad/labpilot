import logging
from collections.abc import Callable, Sequence
from typing import TypeVar

logger = logging.getLogger(__name__)

Found = TypeVar("Found")


def or_nothing(
    find: Callable[[], Sequence[Found]], error: type[Exception], what: str
) -> list[Found]:
    """What `find` found, or an empty list when it fails with `error`.

    Every finder is a safety net: when one fails, the answer goes on without it.
    Any other error is a bug of ours and is not caught.
    """
    try:
        return list(find())
    except error as exc:
        logger.warning("no %s, the answer goes on: %s", what, exc)
        return []

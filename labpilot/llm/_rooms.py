from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from labpilot.llm.defaults import (
    ROOM_HEADROOM,
    ROOM_WINDOW_SECONDS,
    SAFETY_MARGIN_RATIO,
)


@dataclass
class _Room:
    lock: threading.Lock = field(default_factory=threading.Lock)
    # (when it was booked, input tokens) for every call inside the last minute
    booked: deque[tuple[float, int]] = field(default_factory=deque)


# ONE room for each quota pool, shared by every call and every thread. A room
# kept inside one call would forget what the other parallel calls just spent.
_ROOMS: dict[str, _Room] = {}
_GUARD = threading.Lock()


def with_margin(estimate: int) -> int:
    """An estimate of input tokens, plus the safety margin of the length check."""
    return math.ceil(estimate * (1 + SAFETY_MARGIN_RATIO))


def book(
    pool: str,
    *,
    tokens: int,
    token_limit: int | None,
    request_limit: int | None,
) -> float:
    """Book one call in the room of `pool`, if it fits now.

    Returns 0.0 when the call is booked. Otherwise it books NOTHING and returns
    the seconds until the oldest booked call leaves the minute, which is the
    soonest the room can have space (it may still not be enough).

    A call is booked when it is RESERVED, before it is sent, and it stays booked
    even if it fails: a call that ends in a 500 still used the room (measured on
    Google, 2026-10-22). That over-counts, which is the safe direction.
    """

    if token_limit is None and request_limit is None:
        return 0.0

    with _GUARD:
        room = _ROOMS.setdefault(pool, _Room())

    token_cap = _cap(token_limit)
    request_cap = _cap(request_limit)

    with room.lock:
        now = time.monotonic()
        while room.booked and now - room.booked[0][0] >= ROOM_WINDOW_SECONDS:
            room.booked.popleft()

        used = sum(entry[1] for entry in room.booked)
        fits = (token_cap is None or used + tokens <= token_cap) and (
            request_cap is None or len(room.booked) + 1 <= request_cap
        )
        # An EMPTY room always admits: a prompt larger than the whole cap would
        # otherwise wait for ever. The per-call length check refuses the ones
        # that can never pass, before they reach this point.
        if fits or not room.booked:
            room.booked.append((now, tokens))
            return 0.0

        return max(0.0, room.booked[0][0] + ROOM_WINDOW_SECONDS - now)


def _cap(limit: int | None) -> int | None:
    return None if limit is None else max(1, int(limit * ROOM_HEADROOM))


def _forget() -> None:
    """Tests only - module state that leaks between tests is a shared fixture."""
    with _GUARD:
        _ROOMS.clear()

"""What the last calls taught us about each tier, shared by every call.

Without it each call learns alone that a quota is spent or a model is overloaded,
so one question asks the same dead tier again and again. A tier (or its quota
pool) that failed RESTS: calls skip it at once until the rest is over. Each
failure in a row doubles the rest, and one good answer ends it. A resting tier is
still the last resort of a call that has nothing else left.
"""

from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_until: dict[str, float] = {}
_strikes: dict[str, int] = {}

# First rest in seconds, and the longest, for each kind of failure.
QUOTA = (60.0, 3600.0)  # 429: a minute, then longer and longer
GONE = (600.0, 3600.0)  # 401, 402, 404, "not on this plan"
OVERLOADED = (10.0, 30.0)  # 503
SLOW = (20.0, 60.0)  # silent, stopped in the middle, or cut
FAILED = (10.0, 120.0)  # anything else


def rest(key: str, kind: tuple[float, float], asked: float | None = None) -> None:
    """`key` failed: rest it. `asked` is what the provider itself asked for."""
    first, longest = kind
    with _lock:
        strikes = _strikes.get(key, 0)
        # Calls that fail together are one failure: several run at the same time,
        # and one bad second must not count as five in a row.
        if _until.get(key, 0.0) > time.monotonic():
            strikes = max(strikes - 1, 0)
        else:
            _strikes[key] = strikes + 1
        seconds = min(first * 2**strikes, longest)
        # A provider that names its own time (a daily reset) is believed, for at
        # most a day: one wrong number must not retire a tier for ever.
        if asked is not None:
            seconds = max(seconds, min(asked, 86_400.0))
        _until[key] = max(_until.get(key, 0.0), time.monotonic() + seconds)


def left(key: str) -> float:
    """Seconds until `key` may be asked again (0 = now)."""
    with _lock:
        return max(0.0, _until.get(key, 0.0) - time.monotonic())


def good(key: str) -> None:
    """`key` answered: its rest and its strikes are over."""
    with _lock:
        _until.pop(key, None)
        _strikes.pop(key, None)


def forget() -> None:
    """Tests only - module state that leaks between tests is a shared fixture."""
    with _lock:
        _until.clear()
        _strikes.clear()

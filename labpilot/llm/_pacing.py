from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_next_free: dict[str, float] = {}
_open_calls: dict[str, int] = {}


def enter(
    account: str, *, concurrent: int | None, gap: float, max_wait: float
) -> tuple[str | None, float]:
    """Ask to start one call on `account` NOW, or learn why not.

    Returns (reason, sleep). A reason means "do not call this tier": nothing was
    taken and the walk goes to the next tier at once. No reason means the call is
    admitted: its place is taken, and `sleep` is the short rest (at most
    `max_wait`) to sleep first. Two rules, both measured on LiteRouter:

    - `concurrent`: how many calls of the ACCOUNT may be open at once. A second
      call while the first runs is answered 403 "Too many concurrent requests".
    - `gap`: seconds between the START of two calls of the ACCOUNT. A call sent
      too soon is answered 403 "7 seconds between messages", on any model.

    The place is RESERVED under the lock, so two parallel calls never both see
    "free". The old code slept for the rest and then called; a parallel step then
    queued behind one slow account while other providers were free, so now a rest
    longer than `max_wait` is a reason to skip, not a reason to wait.
    """
    with _lock:
        if concurrent is not None and _open_calls.get(account, 0) >= concurrent:
            return (
                f"{account}: {concurrent} call open, only {concurrent} at a time",
                0.0,
            )

        now = time.monotonic()
        start = max(now, _next_free.get(account, 0.0))
        rest = start - now
        if rest > max_wait:
            return f"{account}: must rest {rest:.1f}s between calls", 0.0

        if gap > 0:
            _next_free[account] = start + gap
        if concurrent is not None:
            _open_calls[account] = _open_calls.get(account, 0) + 1
        return None, rest


def leave(account: str, *, concurrent: int | None, quiet: float) -> None:
    """A call on `account` ended (it answered, or it failed): free its place.

    `quiet` keeps the account closed for that long AFTER the call, because
    LiteRouter refused a call that started 0 s after another one ended.
    """
    with _lock:
        if concurrent is not None:
            _open_calls[account] = max(0, _open_calls.get(account, 0) - 1)
        if quiet > 0:
            now = time.monotonic()
            _next_free[account] = max(_next_free.get(account, 0.0), now + quiet)


def forget() -> None:
    """Tests only - module state that leaks between tests is a shared fixture."""
    with _lock:
        _next_free.clear()
        _open_calls.clear()

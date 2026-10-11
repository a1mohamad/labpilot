from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_next_free: dict[str, float] = {}


def wait_for_turn(account: str, gap: float) -> None:
    """Block until `gap` seconds have passed since the last call on `account`.

    LiteRouter answers HTTP 403 "Rate limit exceeded for your tier (7 seconds
    between messages)" to a message sent too soon after the previous one - on
    ANY model, so the limit belongs to the account. Measured 2026-10-11: four
    different models called back to back, the first 200 and the other three
    refused, and the same three answered when spaced 8 seconds apart.

    The slot is RESERVED under the lock and the sleep happens outside it, so
    two threads asking at once get two different slots instead of both seeing
    "free". The graph will run nodes in parallel, which makes that the normal
    case rather than a rare one.
    """
    if gap <= 0:
        return

    with _lock:
        now = time.monotonic()
        start = max(now, _next_free.get(account, 0.0))
        _next_free[account] = start + gap

    delay = start - now
    if delay > 0:
        time.sleep(delay)

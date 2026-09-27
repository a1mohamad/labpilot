from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from labpilot.embed.contracts import Pace
from labpilot.embed.defaults import PACE_HEADROOM, PACE_WINDOW_SECONDS

Clock = Callable[[], float]
Sleep = Callable[[float], None]


@dataclass
class _Window:
    lock: threading.Lock = field(default_factory=threading.Lock)
    # (when it left, estimated tokens, texts) for every request in the window
    sent: deque[tuple[float, int, int]] = field(default_factory=deque)


# ONE window per quota POOL, shared across calls. A per-call window would
# forget that ingesting side A spent the minute, and side B's first batch - a
# separate embed_batches call seconds later - would be refused.
_WINDOWS: dict[str, _Window] = {}
_GUARD = threading.Lock()


def reserve(
    pool: str,
    pace: Pace,
    *,
    tokens: int,
    texts: int,
    clock: Clock = time.monotonic,
    sleep: Sleep = time.sleep,
) -> float:
    """Wait until this request fits the pool's minute, then book it.

    Returns the seconds waited. A request is booked when it is RESERVED, and a
    refused one stays booked: that over-counts, which is the safe direction.
    """
    with _GUARD:
        window = _WINDOWS.setdefault(pool, _Window())

    token_cap = _cap(pace.tokens_per_minute)
    text_cap = _cap(pace.texts_per_minute)

    waited = 0.0
    with window.lock:
        while True:
            now = clock()
            while window.sent and now - window.sent[0][0] >= PACE_WINDOW_SECONDS:
                window.sent.popleft()

            used_tokens = sum(entry[1] for entry in window.sent)
            used_texts = sum(entry[2] for entry in window.sent)
            fits = (token_cap is None or used_tokens + tokens <= token_cap) and (
                text_cap is None or used_texts + texts <= text_cap
            )
            # An EMPTY window always admits: a request larger than the whole
            # minute would otherwise wait forever. The batch cap exists so that
            # never happens - see test_every_embedder.
            if fits or not window.sent:
                window.sent.append((now, tokens, texts))
                return waited

            pause = window.sent[0][0] + PACE_WINDOW_SECONDS - now
            sleep(pause)
            waited += pause


def _cap(limit: int | None) -> int | None:
    return None if limit is None else int(limit * PACE_HEADROOM)


def forget() -> None:
    """Tests only - module state that leaks between tests is a shared fixture."""
    with _GUARD:
        _WINDOWS.clear()

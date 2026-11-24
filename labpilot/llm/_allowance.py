"""Stop using a free allowance a little before it is spent.

Token Harbor sends the used part of its weekly allowance with every reply
(`x-th-free-used-pct: 3`). Over ALLOWANCE_LIMIT percent the whole pool rests, so
the last part is kept for a person who needs it and no call meets the refusal.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol

from labpilot.llm import _health

logger = logging.getLogger(__name__)

ALLOWANCE_LIMIT = 90.0
# How long to rest when the reply does not say when the allowance starts again.
UNKNOWN_REST = 3600.0


class _Metered(Protocol):
    allowance_header: str | None
    allowance_reset_header: str | None

    @property
    def pool(self) -> str: ...


def allowance_key(pool: str) -> str:
    """The rest of an allowance has a key of its own: the good answer that brought
    the header would otherwise end the rest of the pool (_health.good)."""
    return f"{pool}:allowance"


def _seconds_until(text: str | None) -> float:
    try:
        when = datetime.fromisoformat((text or "").strip())
    except ValueError:
        return UNKNOWN_REST
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    seconds = (when - datetime.now(UTC)).total_seconds()
    return seconds if seconds > 0 else UNKNOWN_REST


def note_allowance(provider: _Metered, headers: Mapping[str, str]) -> None:
    if provider.allowance_header is None:
        return
    try:
        used = float(headers.get(provider.allowance_header, ""))
    except ValueError:
        return
    if used <= ALLOWANCE_LIMIT:
        return
    reset = headers.get(provider.allowance_reset_header or "")
    seconds = _seconds_until(reset)
    logger.warning("%s: %.0f%% of its allowance is used", provider.pool, used)
    _health.rest(allowance_key(provider.pool), _health.QUOTA, seconds)

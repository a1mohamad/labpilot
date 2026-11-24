from __future__ import annotations

import email.utils
import re
import time
from collections.abc import Mapping

import requests

from labpilot._text import truncate
from labpilot.llm.errors import LLMError

_MILLISECOND_EPOCH = 1e11
_PLAUSIBLE_EPOCH = 1e9
_LIMIT_PREFIX = "x-ratelimit-limit-"


# A 429 that says so in its BODY only (Google, Cloudflare, Token Harbor, Bazaarlink
# send no header for it): the quota of the day is spent, so the pool rests for long.
_DAILY = re.compile(r"per\s?day|daily|allowance", re.IGNORECASE)
DAILY_REST = 3600.0


def daily_rest(status: int | None, body: str, asked: float | None) -> float | None:
    """What a 429 asks for, or a long rest when its body says the day is spent."""
    if status == 429 and _DAILY.search(body):
        return max(asked or 0.0, DAILY_REST)
    return asked


def error_from_response(response: requests.Response, source: str) -> LLMError:
    return LLMError(
        f"{source} HTTP {response.status_code}: {truncate(response.text)}",
        status=response.status_code,
        retry_after=daily_rest(
            response.status_code,
            response.text,
            retry_after_seconds(response.headers),
        ),
        reset_at=reset_at_epoch(response.headers),
        rate_limit=rate_limit_ceiling(response.headers),
    )


def retry_after_seconds(headers: Mapping[str, str]) -> float | None:
    raw = headers.get("Retry-After")
    if raw is None:
        return None

    try:
        return max(0.0, float(raw.strip()))
    except ValueError:
        pass

    try:
        when = email.utils.parsedate_to_datetime(raw)
    except (ValueError, TypeError):
        return None

    return max(0.0, when.timestamp() - time.time())


def reset_at_epoch(headers: Mapping[str, str]) -> float | None:
    raw = headers.get("X-RateLimit-Reset")

    if raw is None:
        return None

    try:
        value = float(raw.strip())
    except ValueError:
        return None

    if value > _MILLISECOND_EPOCH:
        value /= 1000.0
    if value < _PLAUSIBLE_EPOCH:
        return time.time() + value

    return value


def rate_limit_ceiling(headers: Mapping[str, str]) -> float | None:
    ceilings = []

    for name, raw in headers.items():
        if not name.lower().startswith(_LIMIT_PREFIX):
            continue
        try:
            ceilings.append(float(raw.strip()))
        except ValueError:
            continue

    if not ceilings:
        return None

    return min(ceilings)

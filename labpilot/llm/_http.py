from __future__ import annotations

import email.utils
import time
from collections.abc import Mapping

import requests

from labpilot.llm._text import truncate
from labpilot.llm.errors import LLMError

_MILISECOND_EPOCH = 1e11
_PLAUSIBLE_EPOCH = 1e9


def error_from_response(response: requests.Response, source: str) -> LLMError:
    return LLMError(
        f"{source} HTTP {response.status_code}: {truncate(response.text)}",
        status_code=response.status_code,
        retry_after=retry_after_seconds(response.headers),
        reset_at=reset_at_epoch(response.headers),
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

    if value > _MILISECOND_EPOCH:
        value /= 1000.0
    if value < _PLAUSIBLE_EPOCH:
        return time.time() + value

    return value

from __future__ import annotations

import logging
import time
from typing import Protocol

from labpilot.llm.contracts import LLMResult
from labpilot.llm.errors import LLMError

logger = logging.getLogger(__name__)


class Provider(Protocol):
    name: str
    tier: int
    api_key_env: str

    def complete(self, prompt: str, *, max_tokens: int = ...) -> LLMResult: ...


def delay_for(error: LLMError, attempt: int, *, base: float) -> float:
    if error.retry_after is not None:
        return error.retry_after
    if error.reset_at is not None:
        return max(0.0, error.reset_at - time.time())

    return base * 2**attempt

from __future__ import annotations

import functools
import logging
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from typing import Any, TypeVar

logger = logging.getLogger("labpilot.timing")

current_step: ContextVar[str] = ContextVar("labpilot_current_step", default="")

Result = TypeVar("Result")


def timed(name: str, node: Callable[..., Result]) -> Callable[..., Result]:
    """`node`, run under the step name `name`, with one step line when it ends."""

    @functools.wraps(node)
    def run(*args: Any, **kwargs: Any) -> Result:
        token = current_step.set(name)
        started_at = time.time()
        started = time.monotonic()
        try:
            return node(*args, **kwargs)
        finally:
            seconds = time.monotonic() - started
            current_step.reset(token)
            logger.info(
                "step %s %.1fs",
                name,
                seconds,
                extra={
                    "timing": {
                        "kind": "step",
                        "name": name,
                        "start": started_at,
                        "end": started_at + seconds,
                        "seconds": seconds,
                    }
                },
            )

    return run


def log_call(
    *, tool: str, seconds: float, tier: int | None, model: str | None, failed: int
) -> None:
    """One line for one `generate`: `tier` is None when no tier answered."""
    step = current_step.get()
    logger.info(
        "call %s %s %.1fs tier=%s failed=%d",
        step or "-",
        tool or "text",
        seconds,
        tier,
        failed,
        extra={
            "timing": {
                "kind": "call",
                "step": step,
                "tool": tool,
                "seconds": seconds,
                "end": time.time(),
                "tier": tier,
                "model": model,
                "failed": failed,
            }
        },
    )


def in_this_context(work: Callable[..., Result]) -> Callable[..., Result]:
    """`work`, run later in another thread but with the step name of NOW."""
    captured = copy_context()

    def run(*args: Any, **kwargs: Any) -> Result:
        # One context can be entered by one thread at a time, so each run
        # uses its own copy.
        return captured.copy().run(work, *args, **kwargs)

    return run


class Collector(logging.Handler):
    """Keeps the timing records of a run, for a script or a test."""

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.records: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        timing = getattr(record, "timing", None)
        if timing is not None:
            with self._lock:
                self.records.append(dict(timing))


@contextmanager
def collecting() -> Iterator[Collector]:
    """Collect the timing lines of everything that runs inside the block."""
    collector = Collector()
    previous = logger.level
    logger.addHandler(collector)
    logger.setLevel(logging.INFO)
    try:
        yield collector
    finally:
        logger.removeHandler(collector)
        logger.setLevel(previous)

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from labpilot.llm._race import Provider, Race, RaceRules
from labpilot.llm.contracts import LLMResult, Tool
from labpilot.llm.defaults import (
    DEFAULT_CALL_STOP,
    DEFAULT_MAX_REJECTED_ANSWERS,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TOTAL_BUDGET,
    RETRY_DELAYS,
)
from labpilot.llm.errors import AllFreeTiersExhausted
from labpilot.llm.registry import CHAIN
from labpilot.timing import log_call

__all__ = ["LLMClient", "Provider"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMClient:
    chain: tuple[Provider, ...] = CHAIN
    total_budget: float = DEFAULT_TOTAL_BUDGET
    max_rejected_answers: int = DEFAULT_MAX_REJECTED_ANSWERS
    # A call that has not answered after this long is given up (None = never).
    call_stop: float | None = DEFAULT_CALL_STOP
    # A call still open after this long gets a second tier beside it, and the
    # first good answer wins (None = never). for_task sets it for each task.
    hedge_after: float | None = None
    # The waits before the retries of one tier. () = no retry, which
    # a measurement of one model alone wants. The product never changes it.
    retry_delays: tuple[float, ...] = RETRY_DELAYS

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        tool: Tool | None = None,
        problem_with: Callable[[LLMResult], str | None] | None = None,
    ) -> LLMResult:
        if not prompt.strip():
            raise ValueError("prompt must not be empty")

        started = time.monotonic()
        race = Race(
            self.chain,
            prompt,
            max_tokens=max_tokens,
            tool=tool,
            rules=RaceRules(
                deadline=started + self.total_budget,
                call_stop=self.call_stop,
                hedge_after=self.hedge_after,
                retry_delays=self.retry_delays,
            ),
        )
        rejected = 0
        try:
            while True:
                event = race.next_event()
                if event is None:  # nothing is open and nothing is left to ask
                    break
                provider, result = event
                problem = problem_with(result) if problem_with is not None else None
                if problem is None:
                    log_call(
                        tool=tool.name if tool else "",
                        seconds=time.monotonic() - started,
                        tier=result.tier,
                        model=result.model,
                        failed=len(race.attempts),
                    )
                    return replace(result, attempts=tuple(race.attempts))

                # The tier answered, but the caller says the answer is wrong. The
                # next tier may do better, so the walk goes on. The same tier is
                # NOT asked again (at temperature 0 it would say the same thing),
                # and its quota is fine, so it does not rest.
                logger.warning("tier %d: answer rejected: %s", provider.tier, problem)
                race.note(provider, f"answer rejected: {problem}")
                rejected += 1
                if rejected >= self.max_rejected_answers:
                    break
        finally:
            race.close()

        log_call(
            tool=tool.name if tool else "",
            seconds=time.monotonic() - started,
            tier=None,
            model=None,
            failed=len(race.attempts),
        )
        raise AllFreeTiersExhausted(tuple(race.attempts))

from __future__ import annotations

import contextvars
import itertools
import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Protocol

from labpilot.llm import _health
from labpilot.llm._failures import (
    model_is_unavailable,
    note_failure,
    wait_before_retry,
    worth_a_second_try,
)
from labpilot.llm._pacing import enter, leave
from labpilot.llm._rooms import book, with_margin
from labpilot.llm._stream import Cancel, cancel_token
from labpilot.llm.contracts import Attempt, LLMResult, Tool
from labpilot.llm.defaults import (
    FAST_FAILURE_SECONDS,
    LAST_RESORT_REST,
    LOOK_AGAIN,
    MAX_OPEN,
    TURN_WAIT_MAX,
)
from labpilot.llm.errors import LLMError
from labpilot.tokens import estimate_tokens

logger = logging.getLogger(__name__)


class Provider(Protocol):
    name: str
    tier: int
    api_key_env: str

    @property
    def pool(self) -> str: ...

    def complete(
        self, prompt: str, *, max_tokens: int = ..., tool: Tool | None = ...
    ) -> LLMResult: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class RaceRules:
    """How long one `generate` may take, and when it asks for help."""

    deadline: float
    call_stop: float | None
    hedge_after: float | None
    retry_delays: tuple[float, ...]


@dataclass(slots=True)
class _Call:
    """One open call of a race."""

    provider: Provider
    cancel: Cancel
    started: float


class Race:
    """The calls of one `generate`: usually one, more when the first one is late.

    The chain is walked in order and a tier that cannot take a call NOW is passed
    over at once: its quota or the tier itself rests (_health.py), its minute room
    is full (D70), its account has a call open and takes one at a time, or must
    rest longer than TURN_WAIT_MAX. A tier that fails is followed by the next one
    at once. When a call has been open for `hedge_after` seconds the next tier is
    started BESIDE it, and the first good answer wins (D130): no check on the
    first piece or on silence can see a model that starts well and writes slowly.
    """

    def __init__(
        self,
        chain: tuple[Provider, ...],
        prompt: str,
        *,
        max_tokens: int,
        tool: Tool | None,
        rules: RaceRules,
    ) -> None:
        self.rules = rules
        self.prompt = prompt
        self.max_tokens = max_tokens
        self.tool = tool
        self.deadline = rules.deadline
        self.tokens = with_margin(estimate_tokens(prompt))
        self.attempts: list[Attempt] = []
        self.waiting: list[Provider] = list(chain)
        self.passed: set[str] = set()
        self.look_again_at = 0.0
        self.open: dict[int, _Call] = {}
        self.events: queue.Queue[tuple[int, LLMResult | LLMError]] = queue.Queue()
        self.numbers = itertools.count()

    def note(self, provider: Provider, error: str) -> None:
        self.attempts.append(
            Attempt(tier=provider.tier, model=provider.name, error=error)
        )

    def next_event(self) -> tuple[Provider, LLMResult] | None:
        """The next answer, or None when the whole chain is used up."""
        while True:
            if not self.open and not self._start_one():
                return None
            try:
                number, outcome = self.events.get(timeout=self._patience())
            except queue.Empty:
                self._on_time()
                continue
            call = self.open.pop(number, None)
            if call is None:  # cut or lost: its late end is of no interest
                continue
            if isinstance(outcome, LLMResult):
                _health.good(call.provider.name)
                _health.good(call.provider.pool)
                return call.provider, outcome
            note_failure(call.provider.name, call.provider.pool, outcome)
            if outcome.slow:
                self._siblings_last(call.provider)
            prefix = (
                "not available on this account: "
                if model_is_unavailable(outcome)
                else ""
            )
            self.note(call.provider, f"{prefix}{outcome}")

    def close(self) -> None:
        """The race is over: end the calls that are still open."""
        for call in self.open.values():
            call.cancel.cancel()
        self.open.clear()

    def _siblings_last(self, slow: Provider) -> None:
        """A model that was silent is likely silent on its other keys too, and
        each costs the whole wait again: ask every other model first."""
        self.waiting.sort(key=lambda p: _family(p) == _family(slow))

    # ---- time

    def _patience(self) -> float:
        """Seconds until something must be done if no call ends before."""
        now = time.monotonic()
        moments = [self.deadline]
        if self.rules.call_stop is not None:
            moments += [c.started + self.rules.call_stop for c in self.open.values()]
        hedge = self._hedge_at()
        if hedge is not None:
            moments.append(hedge)
        return max(0.0, min(moments) - now)

    def _hedge_at(self) -> float | None:
        after = self.rules.hedge_after
        if after is None or len(self.open) >= MAX_OPEN or not self.waiting:
            return None
        late = max(c.started for c in self.open.values()) + after
        return max(late, self.look_again_at)

    def _on_time(self) -> None:
        now = time.monotonic()
        hedge = self._hedge_at()
        stop = self.rules.call_stop
        for number, call in list(self.open.items()):
            late = stop is not None and now >= call.started + stop
            if late or now >= self.deadline:
                self.open.pop(number)
                call.cancel.cancel()
                seconds = now - call.started
                self.note(call.provider, f"no answer after {seconds:.0f}s")
                if late:
                    _health.rest(call.provider.name, _health.SLOW)
                    self._siblings_last(call.provider)
        if now >= self.deadline:
            self._out_of_time()
        elif self.open and hedge is not None and now >= hedge:
            if not self._start_one(beside=True):
                # No tier is free for help now. One may be soon.
                self.look_again_at = now + LOOK_AGAIN

    # ---- starting

    def _start_one(self, *, beside: bool = False) -> bool:
        """Start the next tier that can take a call now. False when none can.

        The walk begins at the top every time: a tier passed over a moment ago
        (a full room, an open call, a short rest) may be free by now, and it
        stands above the ones after it for a reason.
        """
        if time.monotonic() >= self.deadline:
            self._out_of_time()
            return False
        if self._walk(self.waiting, beside):
            return True
        if beside or self.open:
            return False
        # Nothing is open and nothing can start. A tier that only rests is asked
        # after all, the shortest rest first; a spent quota (a long rest) is not.
        resting = [p for p in self.waiting if _rest_left(p) <= LAST_RESORT_REST]
        return self._walk(sorted(resting, key=_rest_left), beside, last_resort=True)

    def _walk(
        self, providers: list[Provider], beside: bool, *, last_resort: bool = False
    ) -> bool:
        busy = {c.provider.api_key_env for c in self.open.values()}
        models = {_family(c.provider) for c in self.open.values()}
        for provider in list(providers):
            if beside and (provider.api_key_env in busy or _family(provider) in models):
                # The same account or model would be late for the same reason.
                continue
            reason, rest = self._admit(provider, not last_resort)
            if reason is not None:
                if provider.name not in self.passed:  # one line is enough
                    self.passed.add(provider.name)
                    self.note(provider, f"skipped: {reason}")
                continue
            self.waiting.remove(provider)
            self._launch(provider, rest)
            return True
        return False

    def _out_of_time(self) -> None:
        for provider in self.waiting:
            self.note(provider, "skipped: time budget spent")
        self.waiting.clear()

    def _admit(self, provider: Provider, resting: bool) -> tuple[str | None, float]:
        if resting:
            if _health.left(provider.pool) > 0:
                return f"{provider.pool} exhausted", 0.0
            seconds = _health.left(provider.name)
            if seconds > 0:
                return f"resting for {seconds:.0f}s after a failure", 0.0
        wait = book(
            provider.pool,
            tokens=self.tokens,
            token_limit=getattr(provider, "max_input_tokens", None),
            request_limit=getattr(provider, "requests_per_minute", None),
        )
        if wait > 0:
            return f"room full for {wait:.0f}s", 0.0
        return enter(
            provider.api_key_env,
            concurrent=getattr(provider, "max_concurrent", None),
            gap=getattr(provider, "seconds_between_calls", 0.0),
            max_wait=TURN_WAIT_MAX,
        )

    def _launch(self, provider: Provider, rest: float) -> None:
        number = next(self.numbers)
        call = _Call(provider, Cancel(), time.monotonic())
        self.open[number] = call
        # The context is copied so that the timing of the step finds its name.
        context = contextvars.copy_context()

        def run() -> None:
            cancel_token.set(call.cancel)
            try:
                if rest > 0:
                    time.sleep(rest)
                self.events.put((number, self._complete(provider, call)))
            except LLMError as exc:
                self.events.put((number, exc))
            except BaseException as exc:  # a bug of ours must not hang the race
                self.events.put((number, LLMError(f"{provider.name}: {exc!r}")))
                if not isinstance(exc, Exception):
                    raise
            finally:
                leave(
                    provider.api_key_env,
                    concurrent=getattr(provider, "max_concurrent", None),
                    quiet=getattr(provider, "seconds_after_call", 0.0),
                )

        threading.Thread(target=lambda: context.run(run), daemon=True).start()

    def _complete(self, provider: Provider, call: _Call) -> LLMResult:
        attempt = 0
        while True:
            tried = time.monotonic()
            try:
                return provider.complete(
                    self.prompt, max_tokens=self.max_tokens, tool=self.tool
                )
            except LLMError as exc:
                if call.cancel.done or not worth_a_second_try(exc):
                    raise
                # A failure that came late is a slow or stuck tier: asking it
                # again would cost the same time again, so the walk goes on.
                if time.monotonic() - tried > FAST_FAILURE_SECONDS:
                    raise
                delay = wait_before_retry(exc, attempt, self.rules.retry_delays)
                if delay is None or time.monotonic() + delay >= self.deadline:
                    raise

            logger.warning(
                "tier %d did not answer, trying again in %.0fs (retry %d)",
                provider.tier,
                delay,
                attempt + 1,
            )
            time.sleep(delay)
            attempt += 1


def _family(provider: Provider) -> str:
    return getattr(provider, "model", provider.name)


def _rest_left(provider: Provider) -> float:
    return max(_health.left(provider.name), _health.left(provider.pool))

"""One ROUTE for every task that calls a model (slice 11, sections 31.20 and 33).

A route is the list of tiers a task walks, in order. It is COMPUTED, not
written by hand, from three tables:

- `TASKS` (here): what each task needs - a minimum strength, how big its prompt
  is, how many tokens it asks for, whether it sends many calls at once, whether
  it reads files, and when a hung call is given up;
- `RATINGS` (ratings.py): one row per tier - strength, measured seconds, calls a
  day, limits;
- `ACCURACY` (accuracy.py): how well each model did each task in the lesson 3
  bench.

Two steps. (1) FILTER: a tier is left out when it is too weak, when the prompt
and the answer do not fit, when a per-minute input cap is too small, when it is
scarce and the task reads no files, when the task sends many calls at once and
the tier takes one at a time, or when it is too slow for the task's stop.
(2) ORDER by ONE score that trades accuracy against speed:
    accuracy - w * log2(1 + seconds / normal) + q * quota - p * penalty
so a little more accuracy never buys a much slower model, and a lot more can
(w and normal per kind of task, SPEED_WEIGHT and NORMAL_SECONDS). The seconds
are the bench time of the model FAMILY on this task (accuracy.py), scaled by how
fast THIS tier's provider is against the family's other tiers (ratings.py), at
most twice or half. A tier that takes one call at a time loses BUSY_PENALTY in a
step that runs beside other steps, because the others hold its one slot. A bench
result on few cases is pulled toward the guess from the model's strength
(SHRINK), and a model the bench did not measure gets that guess alone. There
is NO penalty for a model or a provider being placed many times: a model that
is the best on many tasks leads them. The only crowd rule is the busy one
above, because it is a real limit (one call at a time). Four groups, in this
order: the strong tiers; strong tiers whose daily calls feed too few questions
of the task (FEW_QUESTIONS), as backups;
tiers below the task's strength (only a simple task keeps them); and the
tiers that are "not trusted".

A new tier needs only a row in RATINGS (and later a line in ACCURACY): the
routes follow. The walk itself (retries of 1 s and 3 s, a busy tier skipped)
is in chain.py.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, replace

from labpilot.llm.accuracy import ACCURACY
from labpilot.llm.ratings import RATINGS, Rating
from labpilot.llm.registry import CHAIN, KNOWN_DEAD, NOT_TRUSTED


@dataclass(frozen=True, slots=True)
class Task:
    kind: str  # small | many | serial | hidden | answer
    min_strength: int
    prompt_tokens: int  # the biggest prompt the task sends
    max_tokens: int  # what the task asks for
    calls: int  # calls one question makes
    stop: float  # seconds before a hung call is given up
    reads_files: bool = False
    simple: bool = False  # strength-1 tiers may serve it, at the end
    alone: bool = False  # no other model step runs at the same time


TASKS: dict[str, Task] = {
    "rewrite": Task("small", 2, 8_000, 3_000, 1, 30, simple=True, alone=True),
    # Not alone: when the two summaries were not stored at upload (D110), they
    # run in the same step as the planner and can want the same slot.
    "plan": Task("small", 3, 14_500, 4_000, 1, 30),
    "summary": Task("small", 2, 13_000, 4_000, 1, 30, simple=True),
    "gate": Task("small", 2, 1_500, 3_000, 1, 30, simple=True, alone=True),
    "checklist": Task("serial", 3, 4_000, 6_000, 2, 50),
    "fresh": Task("small", 2, 1_500, 1_000, 1, 30, simple=True),
    "judge": Task("serial", 2, 12_000, 12_000, 4, 50),
    "merge": Task("small", 2, 5_000, 4_000, 2, 30, simple=True),
    "merge_strong": Task("small", 4, 5_000, 4_000, 1, 30),
    "claims": Task("many", 2, 3_000, 6_000, 11, 45),
    "trace": Task("many", 2, 4_000, 12_000, 20, 45),
    "scan": Task("many", 2, 23_000, 8_000, 20, 45),
    "audit": Task("serial", 3, 28_000, 12_000, 8, 50, reads_files=True),
    "checklist_audit": Task("serial", 3, 28_000, 16_000, 2, 50, reads_files=True),
    "skeptic": Task("serial", 3, 31_000, 8_000, 2, 50, reads_files=True),
    "method": Task("hidden", 3, 25_000, 12_000, 2, 100, reads_files=True),
    "concept": Task("hidden", 3, 25_000, 12_000, 2, 100, reads_files=True),
    "respond_chat": Task("answer", 2, 8_000, 8_000, 1, 45, simple=True, alone=True),
    "respond_one": Task(
        "answer", 3, 31_000, 16_000, 1, 150, reads_files=True, alone=True
    ),
    "respond_two": Task(
        "answer", 4, 31_000, 32_000, 1, 180, reads_files=True, alone=True
    ),
}

MARGIN = 1.1  # the same 10% the length check of base.py adds to a prompt
MANY_MIN_RPM = 10  # a many-call task needs at least 10 calls a minute
# A tier whose daily calls feed fewer questions of a task is only a backup.
FEW_QUESTIONS = 20


def why_not(rating: Rating, tier, task: Task) -> str | None:
    """The reason this tier may not serve this task, or None."""
    floor = 1 if task.simple else task.min_strength
    if rating.strength < floor:
        return f"strength {rating.strength} is below {floor}"
    if task.max_tokens > tier.max_output_tokens:
        return f"its output cap {tier.max_output_tokens} is below {task.max_tokens}"
    if task.prompt_tokens * MARGIN + task.max_tokens > tier.context_window:
        return f"its window {tier.context_window} is too small"
    cap = getattr(tier, "max_input_tokens", None)
    if cap and task.prompt_tokens * MARGIN > cap:
        return f"its input cap {cap} a minute is too small"
    if rating.scarce and not task.reads_files:
        return "it has only a few calls a day, kept for tasks that read files"
    if task.kind == "many":
        if getattr(tier, "max_concurrent", None) == 1:
            return "it takes one call at a time and this task sends many"
        rpm = getattr(tier, "requests_per_minute", None)
        if rpm is not None and rpm < MANY_MIN_RPM:
            return f"{rpm} calls a minute is too few for many calls"
    seconds = rating.big_seconds if task.prompt_tokens > 6_000 else rating.seconds
    if seconds > task.stop / 2:
        return f"it takes {seconds:.0f} s, too slow for a {task.stop:.0f} s stop"
    return None


# A result on few cases is pulled toward the guess, as if 3 guessed cases were added.
SHRINK = 3


def accuracy(rating: Rating, task_name: str) -> float:
    """The bench result of this model on this task, pulled toward the strength guess
    when it rests on few cases; with no bench result, the guess alone."""
    guess = 0.15 + 0.12 * rating.strength  # strength 1 -> 0.27, 5 -> 0.75
    measured = ACCURACY.get(task_name, {}).get(rating.family)
    if measured is None:
        return guess
    acc, _, cases = measured
    return (cases * acc + SHRINK * guess) / (cases + SHRINK)


# How far the provider of a tier may move the time of its family: at most this
# many times slower or faster. The speed test is one call with nothing else
# running, so it is a fair COMPARISON of providers and a poor measure of a whole
# task; the bench time stays the base.
PROVIDER_FACTOR = (0.5, 2.0)


def _own_time(rating: Rating, task_name: str) -> float:
    """This tier's speed test: the big prompts for a task over 6,000 tokens."""
    big = TASKS[task_name].prompt_tokens > 6_000
    return rating.big_seconds if big else rating.seconds


def seconds(rating: Rating, task_name: str) -> float:
    """The time of this tier on this task.

    The bench time of the model FAMILY on this task (accuracy.py), scaled by this
    tier's speed test against the median of its family's tiers (ratings.py), the
    scale held inside PROVIDER_FACTOR. Each PROVIDER has one vote in that median
    (its own tiers are joined first), so a provider with three keys or ids of one
    model cannot move the others' scale. So the same model on a slower provider
    ranks a little lower, and a task's real length (a whole audit, not one line)
    still comes from the bench. A family the bench did not measure takes the
    tier's own speed test.
    """
    measured = ACCURACY.get(task_name, {}).get(rating.family)
    own = _own_time(rating, task_name)
    if measured is None:
        return own
    by_provider: dict[str, list[float]] = {}
    for r in RATINGS.values():
        if r.family == rating.family:
            by_provider.setdefault(r.provider, []).append(_own_time(r, task_name))
    votes = [statistics.median(times) for times in by_provider.values()]
    median = statistics.median(votes) if votes else own
    low, high = PROVIDER_FACTOR
    scale = min(high, max(low, own / median)) if median else 1.0
    return measured[1] * scale


# How much one doubling of the time costs, and the time that is normal, for each
# kind of task: speed matters most where a person waits for a quick step, least
# for the long report. First guesses; lesson 3 sweeps them (section 33).
SPEED_WEIGHT = {
    "small": 0.05,
    "many": 0.04,
    "serial": 0.04,
    "hidden": 0.02,
    "answer": 0.03,
}
NORMAL_SECONDS = {
    "small": 5.0,
    "many": 5.0,
    "serial": 20.0,
    "hidden": 20.0,
    "answer": 20.0,
}
SPEED_WEIGHT_TWO_FILES = 0.02
NORMAL_SECONDS_TWO_FILES = 30.0


def slowness(rating: Rating, task_name: str) -> float:
    """log2(1 + seconds / normal): 0 when instant, +1 for each doubling."""
    task = TASKS[task_name]
    normal = (
        NORMAL_SECONDS_TWO_FILES
        if task_name == "respond_two"
        else NORMAL_SECONDS[task.kind]
    )
    return math.log2(1 + seconds(rating, task_name) / normal)


def quota(rating: Rating, task: Task) -> float:
    """0..1: how many questions the daily calls can feed (1 = 500 or more)."""
    questions = max(rating.per_day / task.calls, 1.0)
    return min(1.0, math.log10(questions) / math.log10(500))


QUOTA_WEIGHT = 0.08
PENALTY_WEIGHT = 0.03
# A tier that takes ONE call at a time for its whole account (LiteRouter,
# Requesty) loses this in a step that runs beside other steps: the claims, the
# scan, the audit and the bug hunt run together, and they share its one slot, so
# most of their calls would find it busy and skip it. 0.10 lets it lead only
# where it is clearly the most accurate (measured on 2026-11-21: it then leads 2
# of the 14 parallel steps, against 9 without it, for 0.02 of mean accuracy).
BUSY_PENALTY = 0.10


def key(rating: Rating, task_name: str, *, one_at_a_time: bool = False) -> float:
    """One score: accuracy, minus the cost of being slow, plus small tie-breakers."""
    task = TASKS[task_name]
    weight = (
        SPEED_WEIGHT_TWO_FILES
        if task_name == "respond_two"
        else SPEED_WEIGHT[task.kind]
    )
    return (
        accuracy(rating, task_name)
        - weight * slowness(rating, task_name)
        + QUOTA_WEIGHT * quota(rating, task)
        - PENALTY_WEIGHT * rating.penalty
        - (BUSY_PENALTY if one_at_a_time and not task.alone else 0.0)
    )


def _model(name: str) -> str:
    for cut in (" (", " cheap", " stable", " 1017", " 0813"):
        name = name.split(cut)[0]
    return name


# The time a tier may take to count as QUICK for a kind of task, in seconds: a
# little more than the quickest accurate family of the bench.
TARGET = {"small": 15.0, "many": 40.0, "serial": 60.0, "hidden": 100.0, "answer": 100.0}
NEARLY_AS_GOOD = 0.20  # how far below the best a quick tier may be


def measured_or_short(rating: Rating, task_name: str) -> bool:
    """Do we know its time? The speed test is one line of answer, so on a task
    that writes a lot it says nothing about a family the bench did not measure."""
    task = TASKS[task_name]
    short = task.kind == "small" or (task.kind == "answer" and not task.reads_files)
    return short or rating.family in ACCURACY.get(task_name, {})


def route(task_name: str) -> tuple[str, ...]:
    """The names of the tiers this task walks, in order."""
    task = TASKS[task_name]
    # A tier with no row in RATINGS is in no route (a test fails until it has one).
    live = [t for t in CHAIN if t.name not in KNOWN_DEAD and t.name in RATINGS]
    ok = [t for t in live if why_not(RATINGS[t.name], t, task) is None]
    keys = {
        t.name: key(
            RATINGS[t.name],
            task_name,
            one_at_a_time=getattr(t, "max_concurrent", None) == 1,
        )
        for t in ok
    }

    # below the strength of the task (only a simple task keeps such a tier)
    def weak(tier) -> bool:
        return RATINGS[tier.name].strength < task.min_strength

    def few(tier) -> bool:  # its daily calls feed too few questions of this task
        return RATINGS[tier.name].per_day / task.calls < FEW_QUESTIONS

    trusted = [t for t in ok if t.name not in NOT_TRUSTED]
    strong = [t for t in trusted if not weak(t)]
    # FAST AND GOOD FIRST (D130). A tier that answers this task in its target time
    # and is nearly as accurate as the best one goes before every slower tier: a
    # route that begins with two slow models makes the person wait for both.
    best = max((accuracy(RATINGS[t.name], task_name) for t in strong), default=0.0)

    def quick(tier) -> bool:
        rating = RATINGS[tier.name]
        return (
            measured_or_short(rating, task_name)
            and seconds(rating, task_name) <= TARGET[task.kind]
            and accuracy(rating, task_name) >= best - NEARLY_AS_GOOD
        )

    placed: list[str] = []
    for group in (
        [t for t in strong if quick(t) and not few(t)],
        [t for t in strong if quick(t) and few(t)],
        # A refusal of a tier that answers sometimes costs a second, and it rests
        # after it; a slow model costs a minute.
        [t for t in ok if t.name in NOT_TRUSTED and not weak(t) and quick(t)],
        [t for t in strong if not quick(t) and not few(t)],
        [t for t in strong if not quick(t) and few(t)],  # strong, but a backup
        [t for t in trusted if weak(t)],
        [t for t in ok if t.name in NOT_TRUSTED and (weak(t) or not quick(t))],
    ):
        pool = list(group)
        while pool:
            lead = max(pool, key=lambda t: keys[t.name])
            rating = RATINGS[lead.name]
            # The keys of one Google model stay together, in key order.
            twins = [
                t
                for t in pool
                if rating.provider == "google" and _model(t.name) == _model(lead.name)
            ] or [lead]
            for t in sorted(twins, key=lambda t: t.name):
                placed.append(t.name)
                pool.remove(t)
    return tuple(placed)


# When a call of this kind is LATE: a second tier is started beside it and the
# first good answer wins (D130). A few seconds more than a normal answer.
HEDGE = {"small": 6.0, "many": 12.0, "serial": 18.0, "hidden": 30.0, "answer": 10.0}
HEDGE_REPORT = 40.0  # an answer about one or two files is long by nature
# A whole `generate`, with every tier it walks, ends here. A step waits for its
# slowest call, so one unlucky call must not hold the step: the caller goes on
# without that answer (every step does that already when all tiers fail).
BUDGET = {"small": 40.0, "many": 60.0, "serial": 60.0, "hidden": 100.0, "answer": 90.0}
BUDGET_REPORT = 300.0


@dataclass(frozen=True, slots=True)
class Route:
    tiers: tuple[str, ...]
    stop: float
    hedge: float
    budget: float


def _route(name: str, task: Task) -> Route:
    report = task.kind == "answer" and task.reads_files
    return Route(
        tiers=route(name),
        stop=task.stop,
        hedge=HEDGE_REPORT if report else HEDGE[task.kind],
        budget=BUDGET_REPORT if report else BUDGET[task.kind],
    )


ROUTES: dict[str, Route] = {name: _route(name, task) for name, task in TASKS.items()}


def left_out() -> dict[str, str]:
    """Every live tier that is in no route, with the reason for the easiest task."""
    in_a_route = {name for r in ROUTES.values() for name in r.tiers}
    easiest = TASKS["gate"]
    return {
        t.name: (
            why_not(RATINGS[t.name], t, easiest) or "no task it can serve"
            if t.name in RATINGS
            else "it has no row in RATINGS"
        )
        for t in CHAIN
        if t.name not in KNOWN_DEAD and t.name not in in_a_route
    }


# How hard a tier thinks before the answer a person waits for. Measured 2026-11-24
# on one real two-file prompt: DeepSeek V4.1 Flash wrote 9,934 thinking tokens at
# "low" (77 s) and 15,764 at "medium" (121 s) for a report of 3,000 to 5,000.
ANSWER_EFFORT = "low"


def _thinking_less(tier):
    body = getattr(tier, "extra_body", None) or {}
    if "reasoning" not in body:
        return tier
    return replace(tier, extra_body={**body, "reasoning": {"effort": ANSWER_EFFORT}})


def resolve(task_name: str, chain=CHAIN) -> tuple:
    """The tiers of `chain` that the route of this task names, in route order."""
    by_name = {getattr(t, "name", None): t for t in chain}
    found = tuple(by_name[n] for n in ROUTES[task_name].tiers if n in by_name)
    if TASKS[task_name].kind == "answer":
        return tuple(_thinking_less(t) for t in found)
    return found

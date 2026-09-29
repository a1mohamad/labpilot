"""Step 2, slice 1 - how fast is every tier?

    PYTHONPATH=. python scripts/measure_latency.py --dry-run
    PYTHONPATH=. python scripts/measure_latency.py
    PYTHONPATH=. python scripts/measure_latency.py --only Gemma Flash-Lite --rounds 2
    PYTHONPATH=. python scripts/measure_latency.py --report RUN.jsonl
    PYTHONPATH=. python scripts/measure_latency.py --fill RUN.jsonl --dry-run

SPENDS REAL QUOTA - roughly tiers x probes x rounds requests, and the Gemini Flash
tiers allow only 20 a day each. Read the plan that `--dry-run` prints first, and
check the exit ISP before any run (CLAUDE.md's network precondition): a refused
exit looks exactly like a slow tier here.

WHY THIS EXISTS. One report took 401s on tier 1 and 497s on another, and 98.2% of
that was generation. The chain is ordered by quality and by quota and has never
once been ordered by SPEED, so routing a node to a fast tier could only ever
happen by accident. This is the ranking Step 2's routing needs.

WHAT IT MEASURES, and why two probes and not one. Latency is not one number:

    seconds  =  fixed cost  +  (seconds per token) x (tokens written)

A gate that answers in 30 tokens is dominated by the fixed cost - the network,
the queue, the thinking. A report of 5,000 tokens is dominated by the speed. A
tier can be first on one and last on the other, so:

    short   a correspondence-gate-sized job, about 30 tokens out
    long    an explanation, about 400-600 tokens out

Two points fix the line, so the ranking can also answer "how long would a
300-token verdict or a 1,000-token summary take here". The prediction is only
trusted near the measured range, which is why 5,000 is NOT reported.

HOW THE NUMBERS ARE KEPT HONEST:

    NO RETRIES     A retry would hide exactly the slowness being measured. A
                   failure is a data point, and so is a timeout.
    ...EXCEPT THE  A failure BEFORE the provider answers says nothing about the
    NETWORK        model. Through a VPN proxy a tunnel that does not open in 10s
                   is reported as "Read timed out (read timeout=10.0)", which is
                   not the model being slow. Those are kind `network`, are
                   retried, and are never counted in a tier's numbers. On
                   2026-09-29 the network collapsed mid-run and 41 of 300
                   samples were lost this way, 20 of them in the last 25 calls.
    ONE AT A TIME  LiteRouter allows one concurrent request, and parallel calls
                   would contend on our own VPN link.
    A NONCE        Routeway caches identical requests for an hour, so a repeat
                   would report the cache's latency, not the model's.
    ROUNDS         Every tier gets a sample per round, rounds spread across the
                   run. Failures are correlated in time (Token Harbor was bad for
                   minutes at a stretch), so one call is a sample of ONE.
    TOKENS         Read from the provider's own usage, INCLUDING reasoning. A
                   thinking tier writes far more than it shows.
    SAVED AT ONCE  Every sample is appended to a file as it lands. A killed run
                   keeps its data - the 2026-09-19 script that retried into a
                   spent quota for five hours kept nothing.

Known dead routes are not called, and a tier with no key is reported as such.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import statistics
import sys
import time
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

from labpilot.llm import CHAIN, KNOWN_DEAD, LLMError

SHORT = (
    "You compare two pieces of work and decide whether they describe the same "
    "task.\n\n"
    'A: "A service that resizes uploaded images to three widths and stores each '
    'one in object storage."\n'
    'B: "A worker that takes an uploaded photo, produces a thumbnail, a medium '
    'and a large copy, and writes all three to a storage bucket."\n\n'
    "Reply with one JSON object and nothing else:\n"
    '{{"correspondence": "FULL" | "PARTIAL" | "NONE", '
    '"reason": "<one short sentence>"}}\n\n'
    "[request id: {nonce}]"
)

LONG = (
    "Two results are reported for the same benchmark. Explain, in about 300 "
    "words, why they could differ. Name at least three separate causes, and say "
    "which one you think is the most likely.\n\n"
    'Paper: "1,200 requests per second. 16 worker threads, keep-alive on, 1 KB '
    'payloads, a warm cache."\n'
    'Reimplementation: "940 requests per second. 8 worker threads, keep-alive '
    'off, 4 KB payloads, a cold cache."\n\n'
    "[request id: {nonce}]"
)

# REPORT-SIZED, added 2026-09-30 because the two probes above are about 500
# tokens and a report is ten times that. Speed does not scale in a straight
# line: the first ranking put tier 1 at 8s for 500 tokens, which cannot explain
# the 119-497s reports measured on the same tier. The model is told the length
# is part of the task so it does not stop early.
REPORT = (
    "Write a detailed technical report of about 2,000 words on why a "
    "reimplementation of a web server benchmark reports fewer requests per "
    "second than the original paper. Use these sections: Summary, Setup "
    "differences, Likely causes (at least six, each with an explanation and a way "
    "to test it), Ranking of the causes, Experiments to run next, and Limits of "
    "this analysis. Do not stop early: the length is part of the task.\n\n"
    'Paper: "1,200 requests per second. 16 worker threads, keep-alive on, 1 KB '
    'payloads, a warm cache."\n'
    'Reimplementation: "940 requests per second. 8 worker threads, keep-alive '
    'off, 4 KB payloads, a cold cache."\n\n'
    "[request id: {nonce}]"
)

PROBES = {"short": SHORT, "long": LONG, "report": REPORT}

# Tokens each probe may write. Deliberately generous: a reasoning tier can spend
# most of a small budget thinking and return nothing (measured, 2,048 was flaky),
# and a truncated answer would be timed as if it were finished.
OUTPUT_BUDGET = {"short": 2048, "long": 4096, "report": 8192}

# The longest one call may take before it is recorded as a timeout. A censored
# sample - "slower than this" - is still a ranking fact.
READ_CAP = 180.0

# A report-sized answer legitimately takes minutes: tier 1 needed 119 to 497s for
# a full report. A 180s cap would call a slow-but-working tier a timeout.
READ_CAP_BY_PROBE = {"report": 420.0}


def cap_for(probe: str) -> float:
    return READ_CAP_BY_PROBE.get(probe, READ_CAP)


# Seconds between two calls to one key, from limits the providers PUBLISH.
# Routeway is 5 a minute in one pool; Groq counts the tokens it RESERVES, so a
# 4,096-token budget is about two calls a minute; OrcaRouter is 10 a minute.
MIN_GAP = {
    "ROUTEWAY_API_KEY": 13.0,
    "GROQ_API_KEY": 30.0,
    "ORCAROUTER_API_KEY": 7.0,
}

# After a timeout the request may still be running on THEIR side, holding a slot.
# LiteRouter allows one concurrent request and answered 403 "too many concurrent
# requests" to sequential calls for exactly this reason.
AFTER_TIMEOUT_GAP = 60.0

# A failure that never reached the provider is tried again, because it says
# nothing about the model. Three tries in all, a few seconds apart.
NETWORK_ATTEMPTS = 3
NETWORK_RETRY_WAIT = 5.0

# What the fit is asked to predict. Both sit near the measured range; 5,000 does
# not, and an extrapolation seven times past the data would be a guess.
PREDICT_AT = (300, 1000)

# The two probes must differ by at least this many tokens before a line is drawn
# through them. MEASURED 2026-09-29: a thinking tier writes about the same number
# of tokens for BOTH probes (North Mini Code on Kilo: 396 then 422), so the slope
# came out as 86 s per 1,000 tokens and predicted a minute for an answer that
# measured ten seconds. Two points a few tokens apart draw a line through noise.
MIN_TOKEN_GAP = 200

OUT_DIR = Path("artifacts") / "step2" / "latency"


@dataclass(frozen=True, slots=True)
class Sample:
    tier: str
    pool: str
    probe: str
    round: int
    kind: str  # ok | timeout | network | http-<status> | no-key | error
    seconds: float
    status: int | None
    error: str
    generated: int | None  # every token the model wrote, reasoning included
    reasoning: int | None
    finish_reason: str
    chars: int
    at: str = ""  # UTC start time; runs saved before 2026-09-30 have none

    @property
    def ok(self) -> bool:
        return self.kind == "ok"


@dataclass(frozen=True, slots=True)
class Row:
    tier: str
    pool: str
    calls: int
    ok: int
    short_s: float | None
    long_s: float | None
    long_tokens: float | None
    per_1k: float | None
    predicted: dict[int, float]
    failures: str
    long_range: tuple[float, float] | None = None
    long_tok_s: float | None = None  # tokens written per second at the long probe
    report_s: float | None = None
    report_range: tuple[float, float] | None = None
    report_tokens: float | None = None
    report_tok_s: float | None = None


# ---------------------------------------------------------------------------
# Reading a provider's own usage
# ---------------------------------------------------------------------------


def usage_tokens(body: dict | None) -> tuple[int | None, int | None]:
    """(tokens the model wrote, of which reasoning) from a raw response body.

    The two families count differently, and confusing them is the easy mistake:
    OpenAI-shaped `completion_tokens` INCLUDES the reasoning, while Gemini's
    `candidatesTokenCount` EXCLUDES it, so Gemini's total is candidates plus
    thoughts. Cline wraps the whole reply in `data`. Missing usage is None, never
    zero - a zero would rank the tier as instant.
    """
    if not isinstance(body, dict):
        return None, None
    if isinstance(body.get("data"), dict):
        body = body["data"]

    meta = body.get("usageMetadata")
    if isinstance(meta, dict):
        written = meta.get("candidatesTokenCount")
        thought = meta.get("thoughtsTokenCount")
        if written is None and thought is None:
            return None, None
        return (written or 0) + (thought or 0), thought

    usage = body.get("usage")
    if isinstance(usage, dict) and usage.get("completion_tokens") is not None:
        details = usage.get("completion_tokens_details") or {}
        return usage["completion_tokens"], details.get("reasoning_tokens")

    return None, None


# ---------------------------------------------------------------------------
# Planning and pacing
# ---------------------------------------------------------------------------


def budget(provider, probe: str) -> int:
    """The `max_tokens` for a probe: the smoke run's own rule, never above what
    the tier accepts, so the measurement cannot be refused before it starts."""
    return min(
        OUTPUT_BUDGET[probe], provider.max_output_tokens, provider.context_window // 2
    )


def plan(providers: Sequence, probes: Sequence[str], rounds: int) -> dict[str, int]:
    """Requests each quota pool will be asked for."""
    counts: Counter[str] = Counter()
    for provider in providers:
        counts[provider.pool] += len(probes) * rounds
    return dict(counts)


def gap_needed(
    api_key_env: str, *, last_at: float | None, last_timed_out: bool, now: float
) -> float:
    """Seconds still to wait before this key may be called again."""
    if last_at is None:
        return 0.0
    gap = MIN_GAP.get(api_key_env, 0.0)
    if last_timed_out:
        gap = max(gap, AFTER_TIMEOUT_GAP)
    return max(0.0, gap - (now - last_at))


def prompt_for(probe: str) -> str:
    """A fresh prompt every call. The nonce is what keeps a caching gateway from
    answering the second sample out of memory and calling it the model's speed."""
    return PROBES[probe].format(nonce=uuid.uuid4().hex[:10])


# ---------------------------------------------------------------------------
# Summarising
# ---------------------------------------------------------------------------


def is_network_failure(sample: Sample) -> bool:
    """A failure BEFORE the provider gave any verdict.

    Runs saved before the `network` kind existed recorded these as `timeout` or
    `error`, so both old shapes are recognised: a "timeout" that ended long
    before the read cap (the VPN tunnel did not open), and a transport error.
    A real timeout runs to the cap - nothing in the 2026-09-29 run did.
    """
    if sample.kind == "network":
        return True
    if sample.kind == "timeout" and sample.seconds < cap_for(sample.probe) / 2:
        return True
    return sample.kind == "error" and "request failed" in sample.error


def effective(samples: Iterable[Sample]) -> list[Sample]:
    """One sample per (tier, probe, round): the last one that reached the provider.

    A network failure carries no verdict, so any later sample supersedes it -
    that is how a fill run repairs a file without rewriting it.
    """
    chosen: dict[tuple[str, str, int], Sample] = {}
    for sample in samples:
        key = (sample.tier, sample.probe, sample.round)
        previous = chosen.get(key)
        if (
            previous is None
            or is_network_failure(previous)
            or not is_network_failure(sample)
        ):
            chosen[key] = sample
    return list(chosen.values())


def _median(values: Iterable[float]) -> float | None:
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def _failure_summary(samples: Sequence[Sample], unmeasured: int = 0) -> str:
    kinds = Counter(s.kind for s in samples if not s.ok)
    parts = [f"{kind} x{n}" for kind, n in sorted(kinds.items())]
    if unmeasured:
        parts.append(f"network, unmeasured x{unmeasured}")
    return ", ".join(parts)


def summarize(samples: Sequence[Sample]) -> list[Row]:
    """One row per tier. Medians use SUCCESSFUL samples only: a 503 that came
    back in 0.4s is not a fast answer, and a timeout is not a slow one - both
    are counted in `failures` instead.

    A network failure that was never repaired is not a result about the model at
    all, so it does not count as a call: `ok/calls` is out of the calls the
    provider actually answered, and the gap is named in the notes."""
    by_tier: dict[str, list[Sample]] = defaultdict(list)
    for sample in effective(samples):
        by_tier[sample.tier].append(sample)

    rows = []
    for tier, every in by_tier.items():
        unmeasured = sum(1 for s in every if is_network_failure(s))
        group = [s for s in every if not is_network_failure(s)]
        good = [s for s in group if s.ok]
        short = [s for s in good if s.probe == "short"]
        long = [s for s in good if s.probe == "long"]

        short_s = _median(s.seconds for s in short)
        long_s = _median(s.seconds for s in long)
        short_tok = _median(s.generated for s in short)
        long_tok = _median(s.generated for s in long)

        report = [s for s in good if s.probe == "report"]
        report_s = _median(s.seconds for s in report)
        report_tok = _median(s.generated for s in report)

        slope = None
        enough = (
            None not in (short_tok, long_tok) and long_tok - short_tok >= MIN_TOKEN_GAP
        )
        if enough and None not in (short_s, long_s):
            candidate = (long_s - short_s) / (long_tok - short_tok)
            slope = candidate if candidate > 0 else None

        predicted = {}
        if slope is not None:
            for n in PREDICT_AT:
                predicted[n] = max(short_s, short_s + slope * (n - short_tok))

        rows.append(
            Row(
                tier=tier,
                pool=every[0].pool,
                calls=len(group),
                ok=len(good),
                short_s=short_s,
                long_s=long_s,
                long_tokens=long_tok,
                per_1k=None if slope is None else slope * 1000,
                predicted=predicted,
                failures=_failure_summary(group, unmeasured),
                long_range=(
                    (min(s.seconds for s in long), max(s.seconds for s in long))
                    if long
                    else None
                ),
                long_tok_s=(
                    long_tok / long_s if long_tok is not None and long_s else None
                ),
                report_s=report_s,
                report_range=(
                    (min(s.seconds for s in report), max(s.seconds for s in report))
                    if report
                    else None
                ),
                report_tokens=report_tok,
                report_tok_s=(
                    report_tok / report_s
                    if report_tok is not None and report_s
                    else None
                ),
            )
        )
    return rows


def rank(rows: Sequence[Row], by: str = "long") -> list[Row]:
    """Fastest first, on a number that was MEASURED.

    `long` and `short` are the median seconds of the two probes. `t1000` is the
    fitted prediction and is only there for tiers whose two probes differ enough
    to draw a line, so it is not the default. A tier with no number to rank on
    goes last, ordered by whatever it does have."""

    def key(row: Row):
        if by == "report":
            value, fallback = row.report_s, row.long_s
        elif by == "short":
            value, fallback = row.short_s, row.long_s
        elif by == "t1000":
            value, fallback = row.predicted.get(1000, row.long_s), row.short_s
        else:
            value, fallback = row.long_s, row.short_s
        if value is not None:
            return (0, value)
        return (1, fallback) if fallback is not None else (2, 0.0)

    return sorted(rows, key=key)


def format_report_probe(rows: Sequence[Row]) -> str:
    """The report-sized table: seconds, spread, tokens, and whether speed HOLDS.

    `held` is the tokens per second at report length divided by the tokens per
    second at the ~500-token job. Below 1.0 the tier slows down as it writes; it
    is only shown when both probes are in the loaded files."""

    def cell(value, spec=".1f"):
        return "-" if value is None else format(value, spec)

    def span(row: Row):
        if row.report_range is None:
            return "-"
        low, high = row.report_range
        return f"{low:.0f}-{high:.0f}"

    def held(row: Row):
        if row.report_tok_s is None or not row.long_tok_s:
            return None
        return row.report_tok_s / row.long_tok_s

    lines = [
        f"{'#':>2}  {'tier':34} {'ok':>5} {'report s':>9} {'range':>9} "
        f"{'tokens':>7} {'tok/s':>6} {'held':>5}  notes",
        "-" * 116,
    ]
    for place, row in enumerate(rank(rows, "report"), 1):
        lines.append(
            f"{place:>2}  {row.tier:34} {row.ok:>2}/{row.calls:<2} "
            f"{cell(row.report_s):>9} {span(row):>9} "
            f"{cell(row.report_tokens, '.0f'):>7} {cell(row.report_tok_s, '.0f'):>6} "
            f"{cell(held(row), '.2f'):>5}  {row.failures}"
        )
    lines.append("")
    lines.append(
        "report s is the median of the successful calls; tokens is what the "
        "provider says the model wrote, reasoning included. held is tok/s at "
        "report length over tok/s at the ~500-token job."
    )
    return "\n".join(lines)


def format_report(rows: Sequence[Row], by: str = "long") -> str:
    if by == "report":
        return format_report_probe(rows)

    def cell(value, spec=".1f"):
        return "-" if value is None else format(value, spec)

    def span(row: Row):
        if row.long_range is None:
            return "-"
        low, high = row.long_range
        return f"{low:.0f}-{high:.0f}"

    lines = [
        f"{'#':>2}  {'tier':34} {'ok':>5} {'short s':>8} {'long s':>7} "
        f"{'long range':>11} {'tok/s':>6} {'s/1k fit':>9}  notes",
        "-" * 120,
    ]
    for place, row in enumerate(rank(rows, by), 1):
        lines.append(
            f"{place:>2}  {row.tier:34} {row.ok:>2}/{row.calls:<2} "
            f"{cell(row.short_s):>8} {cell(row.long_s):>7} {span(row):>11} "
            f"{cell(row.long_tok_s, '.0f'):>6} {cell(row.per_1k):>9}"
            f"  {row.failures}"
        )
    lines.append("")
    lines.append(
        "seconds are medians of SUCCESSFUL calls and long range is their min-max: "
        "one tier varied 4-19s between rounds. tok/s is tokens written per second "
        "at the long probe, fixed cost included. s/1k fit is drawn only when the "
        "two probes differ by 200+ tokens."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def load_samples(paths: Iterable[Path]) -> list[Sample]:
    samples = []
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record.get("type") == "sample":
                record.pop("type")
                samples.append(Sample(**record))
    return samples


def _append(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def _exit_isp() -> dict:
    """Where the calls came from. Latency depends on the VPN exit, so a number
    without it cannot be compared with the next run."""
    try:
        info = requests.get("https://ipinfo.io/json", timeout=10).json()
        return {k: info.get(k) for k in ("ip", "org", "city", "country")}
    except (requests.RequestException, ValueError):
        return {}


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


class _Recorder:
    """Stands in for requests.post so the raw body - which holds the token
    counts - survives, because LLMResult does not carry usage."""

    def __init__(self, real):
        self.real = real
        self.body = None

    def __call__(self, *args, **kwargs):
        response = self.real(*args, **kwargs)
        try:
            self.body = response.json()
        except ValueError:
            self.body = None
        return response


def transport_kind(seconds: float, cap: float = READ_CAP) -> str:
    """A failure that carried no HTTP status and came from the network layer.

    Only one that ran to the read cap is the model being slow. Anything sooner -
    the VPN tunnel not opening in 10s, a connection reset - never reached the
    provider, and calling it a timeout would rank a fast model as slow."""
    return "timeout" if seconds >= cap * 0.9 else "network"


def measure(provider, probe: str, round_no: int, recorder: _Recorder) -> Sample:
    capped = dataclasses.replace(provider, timeout=(10.0, cap_for(probe)))
    recorder.body = None
    at = datetime.now(UTC).isoformat(timespec="seconds")
    started = time.monotonic()
    status = None
    error = ""
    kind = "ok"
    text = ""
    finish = ""
    try:
        result = capped.complete(prompt_for(probe), max_tokens=budget(provider, probe))
        text, finish = result.text, result.finish_reason
    except LLMError as exc:
        status, error = exc.status, str(exc)[:160]
        if isinstance(exc.__cause__, requests.exceptions.RequestException):
            kind = "transport"  # settled below, once the elapsed time is known
        elif status is not None:
            kind = f"http-{status}"
        elif "is not set" in error:
            kind = "no-key"
        else:
            kind = "error"
    seconds = time.monotonic() - started
    if kind == "transport":
        kind = transport_kind(seconds, cap_for(probe))

    generated, reasoning = usage_tokens(recorder.body) if kind == "ok" else (None, None)
    return Sample(
        tier=provider.name,
        pool=provider.pool,
        probe=probe,
        round=round_no,
        kind=kind,
        seconds=round(seconds, 2),
        status=status,
        error=error,
        generated=generated,
        reasoning=reasoning,
        finish_reason=finish,
        chars=len(text),
        at=at,
    )


def measure_until_reached(
    provider,
    probe: str,
    round_no: int,
    recorder: _Recorder,
    *,
    attempts: int = NETWORK_ATTEMPTS,
    wait: float = NETWORK_RETRY_WAIT,
    sleep=time.sleep,
) -> list[Sample]:
    """Every attempt, the last being the verdict.

    ONLY a network failure is retried. Anything the provider said - a 503, a 429,
    an empty answer - is the result being measured and is kept as it came."""
    tried: list[Sample] = []
    for attempt in range(attempts):
        sample = measure(provider, probe, round_no, recorder)
        tried.append(sample)
        if sample.kind != "network":
            break
        if attempt < attempts - 1:
            sleep(wait)
    return tried


def missing_jobs(
    samples: Iterable[Sample],
    providers: Sequence,
    probes: Sequence[str],
    rounds: int,
) -> list[tuple[object, str, int]]:
    """What still needs a real answer: never sampled, or only ever a network
    failure. In the order a normal run would take them, so pacing still works."""
    settled = {
        (s.tier, s.probe, s.round)
        for s in effective(samples)
        if not is_network_failure(s)
    }
    return [
        (provider, probe, round_no)
        for round_no in range(1, rounds + 1)
        for probe in probes
        for provider in providers
        if (provider.name, probe, round_no) not in settled
    ]


def _select(only: Sequence[str]):
    measured, dead, no_key = [], [], []
    for provider in CHAIN:
        if only and not any(w.lower() in provider.name.lower() for w in only):
            continue
        if provider.name in KNOWN_DEAD:
            dead.append(provider)
        elif not os.environ.get(provider.api_key_env, "").strip():
            no_key.append(provider)
        else:
            measured.append(provider)
    return measured, dead, no_key


def _print_plan(measured, dead, no_key, probes, rounds) -> None:
    total = len(measured) * len(probes) * rounds
    print(
        f"{len(measured)} tiers x {len(probes)} probes x {rounds} rounds "
        f"= {total} requests"
    )
    print()
    print("requests per quota pool (published daily limits are in CLAUDE.md):")
    for pool, count in sorted(plan(measured, probes, rounds).items()):
        print(f"  {count:>4}  {pool}")
    if dead:
        print(f"\nnot called, known dead: {', '.join(p.name for p in dead)}")
    if no_key:
        print(f"not called, no key here: {', '.join(p.name for p in no_key)}")


def _execute(jobs, out: Path) -> list[Sample]:
    """Take the jobs in order, one at a time, saving each sample as it lands."""
    recorder = _Recorder(requests.post)
    requests.post = recorder
    last: dict[str, tuple[float, bool]] = {}
    samples: list[Sample] = []
    try:
        for provider, probe, round_no in jobs:
            at, timed_out = last.get(provider.pool, (None, False))
            wait = gap_needed(
                provider.api_key_env,
                last_at=at,
                last_timed_out=timed_out,
                now=time.monotonic(),
            )
            if wait > 0:
                time.sleep(wait)

            for attempt, sample in enumerate(
                measure_until_reached(provider, probe, round_no, recorder), 1
            ):
                samples.append(sample)
                _append(out, {"type": "sample", **dataclasses.asdict(sample)})
                detail = (
                    f"out {sample.generated} (reasoning {sample.reasoning}) "
                    f"{sample.finish_reason}"
                    if sample.ok
                    else sample.error[:70]
                )
                retry = f" [try {attempt}]" if attempt > 1 else ""
                print(
                    f"r{round_no} {probe:5} {provider.name:34} "
                    f"{sample.kind:9} {sample.seconds:6.1f}s  {detail}{retry}",
                    flush=True,
                )
            last[provider.pool] = (time.monotonic(), samples[-1].kind == "timeout")
    finally:
        requests.post = recorder.real
    return samples


def _header(rounds: int) -> dict:
    return {
        "type": "header",
        "started": datetime.now(UTC).isoformat(),
        "exit": _exit_isp(),
        "rounds": rounds,
        "read_cap": READ_CAP,
        "budget": OUTPUT_BUDGET,
        "probes": {
            name: hashlib.sha256(text.encode()).hexdigest()[:12]
            for name, text in PROBES.items()
        },
    }


def _probes(args) -> list[str]:
    probes = [p.strip() for p in args.probes.split(",")]
    for probe in probes:
        if probe not in PROBES:
            sys.exit(f"unknown probe {probe!r}; choose from {sorted(PROBES)}")
    return probes


def run(args) -> None:
    load_dotenv(dotenv_path=os.path.join(os.getcwd(), ".env"))
    probes = _probes(args)

    measured, dead, no_key = _select(args.only)
    _print_plan(measured, dead, no_key, probes, args.rounds)
    if args.dry_run:
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = (
        Path(args.out)
        if args.out
        else OUT_DIR / (datetime.now(UTC).strftime("%Y-%m-%d_%H-%M") + ".jsonl")
    )
    _append(out, _header(args.rounds))
    print(f"\nwriting {out}\n")

    jobs = [
        (provider, probe, round_no)
        for round_no in range(1, args.rounds + 1)
        for probe in probes
        for provider in measured
    ]
    _execute(jobs, out)

    print()
    print(format_report(summarize(load_samples([out])), args.by))


def fill(args) -> None:
    """Re-measure only what a saved run is missing: never sampled, or lost to the
    network. Appends to the same file; `effective` then lets the new samples
    supersede the failures, so nothing is rewritten and nothing is lost."""
    load_dotenv(dotenv_path=os.path.join(os.getcwd(), ".env"))
    out = Path(args.fill)
    probes = _probes(args)
    measured, _, _ = _select(args.only)
    jobs = missing_jobs(load_samples([out]), measured, probes, args.rounds)

    print(f"{out}: {len(jobs)} samples to (re)measure")
    for pool, count in sorted(Counter(p.pool for p, _, _ in jobs).items()):
        print(f"  {count:>4}  {pool}")
    if args.dry_run or not jobs:
        return

    _append(out, _header(args.rounds) | {"fill": len(jobs)})
    print()
    _execute(jobs, out)

    print()
    print(format_report(summarize(load_samples([out])), args.by))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", nargs="*", default=[], help="tier name fragments")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--probes", default="short,long")
    parser.add_argument(
        "--by", choices=("long", "short", "t1000", "report"), default="long"
    )
    parser.add_argument("--dry-run", action="store_true", help="print the plan only")
    parser.add_argument("--out", help="jsonl file to append to")
    parser.add_argument("--report", nargs="+", help="rank saved runs, call nothing")
    parser.add_argument("--fill", help="re-measure what this saved run is missing")
    args = parser.parse_args()

    if args.report:
        print(format_report(summarize(load_samples(map(Path, args.report))), args.by))
        return
    if args.fill:
        fill(args)
        return
    run(args)


if __name__ == "__main__":
    main()

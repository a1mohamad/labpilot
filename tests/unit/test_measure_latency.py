"""The logic behind scripts/measure_latency.py.

The script spends real quota, so everything that decides WHAT it reports is kept
pure and pinned here. A slip in it does not fail loudly: a wrong token count or
a median that includes failures produces a ranking that looks plausible and
routes Step 2's nodes to the wrong tier.
"""

from __future__ import annotations

import json

import pytest
import requests

from labpilot.llm import CHAIN, KNOWN_DEAD, LLMError
from labpilot.llm.contracts import LLMResult
from scripts import measure_latency as ml


def sample(
    tier="T",
    probe="short",
    kind="ok",
    seconds=1.0,
    generated=30,
    pool="P",
    reasoning=None,
    round=1,
):
    return ml.Sample(
        tier=tier,
        pool=pool,
        probe=probe,
        round=round,
        kind=kind,
        seconds=seconds,
        status=None if kind in ("ok", "timeout", "error") else 503,
        error="" if kind == "ok" else "boom",
        generated=generated if kind == "ok" else None,
        reasoning=reasoning,
        finish_reason="stop" if kind == "ok" else "",
        chars=10,
    )


# --- reading a provider's own usage ----------------------------------------


def test_openai_completion_tokens_already_include_the_reasoning():
    body = {
        "usage": {
            "completion_tokens": 900,
            "completion_tokens_details": {"reasoning_tokens": 700},
        }
    }

    assert ml.usage_tokens(body) == (900, 700)


def test_gemini_thoughts_are_ADDED_because_candidates_exclude_them():
    """The one place the two families disagree. Counting Gemini the OpenAI way
    would call a tier that thought for 800 tokens and wrote 30 a 30-token tier,
    and rank it as far faster than it is."""
    body = {"usageMetadata": {"candidatesTokenCount": 30, "thoughtsTokenCount": 800}}

    assert ml.usage_tokens(body) == (830, 800)


def test_a_gemini_reply_with_no_thoughts_counts_only_what_it_wrote():
    body = {"usageMetadata": {"candidatesTokenCount": 30}}

    assert ml.usage_tokens(body) == (30, None)


def test_cline_wraps_the_usage_one_level_down():
    body = {"data": {"usage": {"completion_tokens": 120}}, "success": True}

    assert ml.usage_tokens(body) == (120, None)


@pytest.mark.parametrize("body", [None, {}, {"usage": {}}, {"usageMetadata": {}}, []])
def test_missing_usage_is_none_never_zero(body):
    """Zero would rank the tier as instant."""
    assert ml.usage_tokens(body) == (None, None)


# --- planning and pacing ----------------------------------------------------


def test_the_plan_counts_probes_times_rounds_per_pool():
    class P:
        def __init__(self, pool):
            self.pool = pool

    tiers = [P("a"), P("a"), P("b")]

    assert ml.plan(tiers, ["short", "long"], 3) == {"a": 12, "b": 6}


def test_the_output_budget_never_exceeds_what_the_tier_accepts():
    class Small:
        max_output_tokens = 1000
        context_window = 8000

    class Tight:
        max_output_tokens = 65_536
        context_window = 8000  # Groq: the window counts prompt AND reserved output

    assert ml.budget(Small, "long") == 1000
    assert ml.budget(Tight, "long") == 4000
    assert ml.budget(Tight, "short") == 2048


@pytest.mark.parametrize(
    ("env", "elapsed", "timed_out", "expected"),
    [
        ("ROUTEWAY_API_KEY", 3.0, False, 10.0),  # 13s gap, 3s already passed
        ("ROUTEWAY_API_KEY", 20.0, False, 0.0),  # long enough ago
        ("GOOGLE_API_KEY", 0.1, False, 0.0),  # no published limit to respect
        ("GOOGLE_API_KEY", 10.0, True, 50.0),  # a timeout may still hold a slot
    ],
)
def test_the_wait_before_the_next_call_to_a_key(env, elapsed, timed_out, expected):
    wait = ml.gap_needed(
        env, last_at=100.0, last_timed_out=timed_out, now=100.0 + elapsed
    )

    assert wait == pytest.approx(expected)


def test_the_first_call_to_a_key_waits_for_nothing():
    assert (
        ml.gap_needed("ROUTEWAY_API_KEY", last_at=None, last_timed_out=False, now=5)
        == 0
    )


def test_no_two_samples_ever_send_the_same_prompt():
    """Routeway caches identical requests for an hour. A repeat would report the
    cache's latency as the model's."""
    prompts = {ml.prompt_for("short") for _ in range(50)}

    assert len(prompts) == 50
    assert "{nonce}" not in next(iter(prompts))


def test_the_two_probes_really_ask_for_different_amounts_of_writing():
    """The fit needs two points with different token counts; if both probes
    asked for the same thing the slope would be noise.

    The PROMPT's length says nothing about the answer's - a first version of
    this test compared the two prompts and failed, correctly, because the short
    one is the longer text. What differs is what each one ASKS FOR."""
    assert "one JSON object" in ml.PROBES["short"]
    assert "about 300 words" in ml.PROBES["long"]
    assert ml.OUTPUT_BUDGET["long"] > ml.OUTPUT_BUDGET["short"]


def test_every_pacing_key_is_one_a_shipped_tier_really_uses():
    """A typo here would leave a limited provider unpaced with no error."""
    used = {provider.api_key_env for provider in CHAIN}

    assert set(ml.MIN_GAP) <= used


def test_the_known_dead_routes_are_not_measured(monkeypatch):
    for provider in CHAIN:
        monkeypatch.setenv(provider.api_key_env, "k")

    measured, dead, _ = ml._select([])

    assert {p.name for p in dead} == set(KNOWN_DEAD)
    assert not {p.name for p in measured} & set(KNOWN_DEAD)


def test_a_tier_with_no_key_is_reported_not_called(monkeypatch):
    for provider in CHAIN:
        monkeypatch.setenv(provider.api_key_env, "k")
    monkeypatch.delenv("GROQ_API_KEY")

    measured, _, no_key = ml._select([])

    assert no_key
    assert all(p.api_key_env == "GROQ_API_KEY" for p in no_key)
    assert not any(p.api_key_env == "GROQ_API_KEY" for p in measured)


# --- summarising ------------------------------------------------------------


def test_medians_use_successful_calls_only():
    """A 503 that came back in 0.4s is not a fast answer."""
    samples = [
        sample(seconds=10.0, round=1),
        sample(seconds=12.0, round=2),
        sample(seconds=0.4, kind="http-503", round=3),
        sample(seconds=180.0, kind="timeout", round=4),
    ]

    (row,) = ml.summarize(samples)

    assert row.short_s == 11.0
    assert (row.ok, row.calls) == (2, 4)
    assert row.failures == "http-503 x1, timeout x1"


def test_the_fixed_cost_and_the_speed_come_out_of_the_two_probes():
    """20s for 30 tokens and 30s for 530 tokens is 10s over 500 tokens, so 20s
    per 1,000 tokens, with the rest of the first probe as fixed cost."""
    samples = [
        sample(probe="short", seconds=20.0, generated=30),
        sample(probe="long", seconds=30.0, generated=530),
    ]

    (row,) = ml.summarize(samples)

    assert row.per_1k == pytest.approx(20.0)
    assert row.predicted[1000] == pytest.approx(20.0 + 0.02 * (1000 - 30))
    assert row.predicted[300] == pytest.approx(20.0 + 0.02 * (300 - 30))


def test_a_thinking_tier_that_wrote_more_for_the_short_job_gets_no_slope():
    """If the short probe generated as many tokens as the long one - reasoning
    ran away - there is no line, and inventing one would rank it on noise."""
    samples = [
        sample(probe="short", seconds=20.0, generated=900),
        sample(probe="long", seconds=25.0, generated=600),
    ]

    (row,) = ml.summarize(samples)

    assert row.per_1k is None
    assert row.predicted == {}


def test_a_long_probe_faster_than_the_short_one_gives_no_slope():
    samples = [
        sample(probe="short", seconds=30.0, generated=30),
        sample(probe="long", seconds=20.0, generated=500),
    ]

    (row,) = ml.summarize(samples)

    assert row.predicted == {}


def test_the_ranking_is_fastest_first_and_a_tier_that_never_answered_is_last():
    fast = [
        sample(tier="fast", probe="short", seconds=1.0, generated=30),
        sample(tier="fast", probe="long", seconds=6.0, generated=530),
    ]
    slow = [
        sample(tier="slow", probe="short", seconds=5.0, generated=30),
        sample(tier="slow", probe="long", seconds=30.0, generated=530),
    ]
    dead = [sample(tier="dead", kind="http-503", seconds=0.2)]

    ranked = ml.rank(ml.summarize(dead + slow + fast))

    assert [row.tier for row in ranked] == ["fast", "slow", "dead"]


def test_ranking_by_the_short_job_can_disagree_with_ranking_by_a_long_one():
    """The whole reason there are two probes. Quick to answer, slow to write."""
    quick_then_slow = [
        sample(tier="A", probe="short", seconds=1.0, generated=30),
        sample(tier="A", probe="long", seconds=60.0, generated=530),
    ]
    slow_then_quick = [
        sample(tier="B", probe="short", seconds=8.0, generated=30),
        sample(tier="B", probe="long", seconds=10.0, generated=530),
    ]
    rows = ml.summarize(quick_then_slow + slow_then_quick)

    assert [r.tier for r in ml.rank(rows, by="short")] == ["A", "B"]
    assert [r.tier for r in ml.rank(rows, by="t1000")] == ["B", "A"]


def test_the_report_names_every_tier_and_its_failures():
    rows = ml.summarize(
        [sample(tier="Only", kind="http-429", seconds=0.3), sample(tier="Ok")]
    )

    text = ml.format_report(rows)

    assert "Only" in text
    assert "http-429 x1" in text
    assert "Ok" in text


# --- storage ----------------------------------------------------------------


def test_a_saved_run_loads_back_without_its_header(tmp_path):
    path = tmp_path / "run.jsonl"
    ml._append(path, {"type": "header", "exit": {"org": "somewhere"}})
    first = sample(tier="A", seconds=2.5)
    ml._append(path, {"type": "sample", **ml.dataclasses.asdict(first)})

    assert ml.load_samples([path]) == [first]


def test_every_sample_is_written_the_moment_it_lands(tmp_path):
    """A killed run must keep what it measured."""
    path = tmp_path / "run.jsonl"

    ml._append(path, {"type": "sample", **ml.dataclasses.asdict(sample())})
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1

    ml._append(path, {"type": "sample", **ml.dataclasses.asdict(sample(tier="B"))})
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["tier"] for line in lines] == ["T", "B"]


# --- the network, and repairing a run that lost samples to it ---------------


@pytest.mark.parametrize(
    ("kind", "seconds", "error", "expected"),
    [
        ("network", 5.0, "", True),
        ("timeout", 10.5, "", True),  # the VPN tunnel did not open in 10s
        ("timeout", 180.0, "", False),  # ran to the cap: the model was slow
        ("error", 1.0, "Tier: request failed: HTTPSConnectionPool(", True),
        ("error", 1.0, "Tier: unexpected response shape: {", False),
        ("error", 11.0, "Tier: returned an empty answer", False),
        ("http-503", 2.0, "Tier HTTP 503", False),
        ("http-429", 1.0, "Tier HTTP 429", False),
        ("ok", 3.0, "", False),
    ],
)
def test_only_a_failure_before_the_provider_answered_is_a_network_failure(
    kind, seconds, error, expected
):
    """An old run recorded these as `timeout` or `error`, so both old shapes
    have to be recognised - and a provider's own refusal never is."""
    s = ml.Sample(
        **{
            **ml.dataclasses.asdict(sample()),
            "kind": kind,
            "seconds": seconds,
            "error": error,
        }
    )

    assert ml.is_network_failure(s) is expected


def test_a_failure_that_ran_to_the_cap_is_a_timeout_and_a_quick_one_is_the_network():
    assert ml.transport_kind(10.5) == "network"
    assert ml.transport_kind(ml.READ_CAP * 0.9) == "timeout"
    assert ml.transport_kind(ml.READ_CAP) == "timeout"


def test_a_later_sample_supersedes_a_network_failure_for_the_same_slot():
    lost = sample(kind="network", seconds=10.5)
    repaired = sample(seconds=4.0)

    assert ml.effective([lost, repaired]) == [repaired]


def test_a_network_failure_never_replaces_a_real_answer():
    """A duplicate slot must not let a dropped connection overwrite a result."""
    real = sample(seconds=4.0)
    lost = sample(kind="network", seconds=10.5)

    assert ml.effective([real, lost]) == [real]


def test_different_rounds_and_probes_are_different_slots():
    slots = [
        sample(round=1),
        sample(round=2),
        sample(probe="long"),
        sample(tier="B"),
    ]

    assert len(ml.effective(slots)) == 4


def test_an_unrepaired_network_failure_is_not_counted_as_a_call_on_the_model():
    rows = ml.summarize(
        [
            sample(round=1, seconds=4.0),
            sample(round=2, kind="network", seconds=10.5),
        ]
    )

    (row,) = rows
    assert (row.ok, row.calls) == (1, 1)
    assert "network, unmeasured x1" in row.failures


def test_a_repaired_network_failure_counts_and_leaves_no_note():
    (row,) = ml.summarize(
        [
            sample(round=1, kind="network", seconds=10.5),
            sample(round=1, seconds=4.0),
        ]
    )

    assert (row.ok, row.calls) == (1, 1)
    assert "network" not in row.failures


class Named:
    def __init__(self, name):
        self.name = name


def test_only_the_missing_samples_are_scheduled_in_a_normal_runs_order():
    a, b = Named("A"), Named("B")
    have = [
        sample(tier="A", probe="short", round=1),
        sample(tier="B", probe="short", round=1, kind="network", seconds=10.5),
    ]

    jobs = ml.missing_jobs(have, [a, b], ["short", "long"], 1)

    assert [(p.name, probe, r) for p, probe, r in jobs] == [
        ("B", "short", 1),  # lost to the network
        ("A", "long", 1),  # never sampled
        ("B", "long", 1),
    ]


def test_nothing_is_scheduled_when_every_slot_has_an_answer():
    have = [sample(tier="A", probe="short", round=1)]

    assert ml.missing_jobs(have, [Named("A")], ["short"], 1) == []


def test_a_provider_refusal_is_a_finished_sample_not_a_gap_to_fill():
    """A 503 is the result. Re-running it would launder the tier's reliability."""
    have = [sample(tier="A", kind="http-503", seconds=2.0)]

    assert ml.missing_jobs(have, [Named("A")], ["short"], 1) == []


def scripted_measure(monkeypatch, *kinds):
    outcomes = iter(kinds)
    monkeypatch.setattr(
        ml, "measure", lambda *a, **k: sample(kind=next(outcomes), seconds=1.0)
    )


def test_only_a_network_failure_is_retried(monkeypatch):
    scripted_measure(monkeypatch, "network", "network", "ok")
    slept = []

    tried = ml.measure_until_reached(
        object(), "short", 1, None, attempts=3, wait=5.0, sleep=slept.append
    )

    assert [s.kind for s in tried] == ["network", "network", "ok"]
    assert slept == [5.0, 5.0]


@pytest.mark.parametrize("kind", ["http-503", "http-429", "error", "timeout", "ok"])
def test_anything_the_provider_said_is_taken_as_it_came(monkeypatch, kind):
    scripted_measure(monkeypatch, kind, "ok")
    slept = []

    tried = ml.measure_until_reached(
        object(), "short", 1, None, attempts=3, wait=5.0, sleep=slept.append
    )

    assert [s.kind for s in tried] == [kind]
    assert slept == []


def test_the_network_is_given_up_on_after_the_last_attempt_without_a_pointless_wait(
    monkeypatch,
):
    scripted_measure(monkeypatch, "network", "network", "network", "ok")
    slept = []

    tried = ml.measure_until_reached(
        object(), "short", 1, None, attempts=3, wait=5.0, sleep=slept.append
    )

    assert [s.kind for s in tried] == ["network"] * 3
    assert slept == [5.0, 5.0]


@ml.dataclasses.dataclass(frozen=True)
class FakeProvider:
    """Just enough of a provider for measure(): it is copied with a new
    timeout, budgeted, and asked to complete."""

    behaviour: object
    name: str = "Fake"
    pool: str = "P"
    max_output_tokens: int = 4096
    context_window: int = 100_000
    timeout: tuple = (10.0, 180.0)

    def complete(self, prompt, *, max_tokens):
        return self.behaviour(prompt, max_tokens)


def failing(message, *, status=None, cause=None):
    def behaviour(prompt, max_tokens):
        error = LLMError(message, status=status)
        error.__cause__ = cause
        raise error

    return behaviour


def measured(behaviour, recorder=None):
    recorder = recorder or ml._Recorder(None)
    return ml.measure(FakeProvider(behaviour), "short", 2, recorder)


def test_a_good_answer_is_timed_stamped_and_counted_from_the_providers_usage():
    recorder = ml._Recorder(None)

    def behaviour(prompt, max_tokens):
        recorder.body = {"usage": {"completion_tokens": 42}}
        return LLMResult(text="hello", model="m", tier=1, finish_reason="stop")

    result = measured(behaviour, recorder)

    assert result.kind == "ok"
    assert (result.generated, result.chars, result.finish_reason) == (42, 5, "stop")
    assert result.round == 2
    assert result.at.endswith("+00:00"), "a UTC timestamp, so runs can be lined up"


def test_a_transport_failure_that_ended_at_once_is_recorded_as_the_network():
    result = measured(
        failing(
            "Fake: request failed: boom",
            cause=requests.exceptions.ConnectTimeout("tunnel"),
        )
    )

    assert result.kind == "network"


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"message": "Fake HTTP 503", "status": 503}, "http-503"),
        ({"message": "Fake HTTP 429", "status": 429}, "http-429"),
        ({"message": "Fake: KEY is not set"}, "no-key"),
        ({"message": "Fake: unexpected response shape: {"}, "error"),
    ],
)
def test_what_the_provider_said_keeps_its_own_kind(kwargs, expected):
    assert measured(failing(**kwargs)).kind == expected


def test_a_refusal_is_never_mistaken_for_the_network():
    """The retry rule hangs on this: a 503 must not be retried into a success."""
    result = measured(failing("Fake HTTP 503", status=503))

    assert not ml.is_network_failure(result)


def test_the_call_is_capped_so_a_hang_becomes_a_recorded_timeout(monkeypatch):
    seen = {}

    def behaviour(prompt, max_tokens):
        return LLMResult(text="x", model="m", tier=1)

    provider = FakeProvider(behaviour, timeout=(99.0, 999.0))
    original = ml.dataclasses.replace

    def spy(obj, **changes):
        seen.update(changes)
        return original(obj, **changes)

    monkeypatch.setattr(ml.dataclasses, "replace", spy)
    ml.measure(provider, "short", 1, ml._Recorder(None))

    assert seen["timeout"] == (10.0, ml.READ_CAP)


def test_a_run_saved_before_timestamps_still_loads(tmp_path):
    path = tmp_path / "old.jsonl"
    old = ml.dataclasses.asdict(sample())
    del old["at"]
    ml._append(path, {"type": "sample", **old})

    (loaded,) = ml.load_samples([path])

    assert loaded.at == ""


# --- ranking on what was measured -------------------------------------------


def test_two_probes_a_few_tokens_apart_draw_no_line():
    """MEASURED 2026-09-29: a thinking tier wrote 396 tokens for the short probe
    and 422 for the long one. A line through those points said 86 s per 1,000
    tokens for an answer that took ten seconds."""
    samples = [
        sample(probe="short", seconds=7.6, generated=396),
        sample(probe="long", seconds=9.8, generated=422),
    ]

    (row,) = ml.summarize(samples)

    assert row.per_1k is None
    assert row.predicted == {}
    assert row.long_s == 9.8, "the measured number is still there to rank on"


def test_a_gap_of_exactly_the_minimum_is_enough_for_a_line():
    samples = [
        sample(probe="short", seconds=2.0, generated=30),
        sample(probe="long", seconds=6.0, generated=30 + ml.MIN_TOKEN_GAP),
    ]

    (row,) = ml.summarize(samples)

    assert row.per_1k == pytest.approx(20.0)


def test_the_default_ranking_uses_the_measured_long_time_even_with_no_line():
    """The line is a bonus. A tier that cannot have one must still be ranked,
    on the number it does have, not thrown to the bottom."""
    no_line = [
        sample(tier="thinker", probe="short", seconds=7.0, generated=400),
        sample(tier="thinker", probe="long", seconds=9.0, generated=420),
    ]
    slower = [
        sample(tier="plain", probe="short", seconds=1.0, generated=30),
        sample(tier="plain", probe="long", seconds=20.0, generated=530),
    ]

    ranked = ml.rank(ml.summarize(slower + no_line))

    assert [row.tier for row in ranked] == ["thinker", "plain"]


def test_a_tier_that_only_answered_the_short_probe_ranks_after_every_full_one():
    short_only = [sample(tier="short-only", probe="short", seconds=1.0)]
    full = [
        sample(tier="full", probe="short", seconds=9.0, generated=30),
        sample(tier="full", probe="long", seconds=90.0, generated=530),
    ]
    silent = [sample(tier="silent", kind="http-429", seconds=0.5)]

    ranked = ml.rank(ml.summarize(silent + short_only + full))

    assert [row.tier for row in ranked] == ["full", "short-only", "silent"]


def test_the_spread_and_the_tokens_per_second_are_reported():
    """One tier varied 4 to 19 seconds between rounds for the same job, so a
    median alone would look far steadier than it is."""
    samples = [
        sample(probe="long", seconds=18.0, generated=400, round=1),
        sample(probe="long", seconds=10.0, generated=400, round=2),
        sample(probe="long", seconds=4.0, generated=400, round=3),
    ]

    (row,) = ml.summarize(samples)

    assert row.long_range == (4.0, 18.0)
    assert row.long_tok_s == pytest.approx(400 / 10.0)


def test_the_report_shows_the_range_and_a_dash_where_there_is_no_number():
    rows = ml.summarize(
        [
            sample(tier="Steady", probe="long", seconds=9.0, generated=500),
            sample(tier="Silent", kind="http-503", seconds=0.5),
        ]
    )

    text = ml.format_report(rows)

    assert "long range" in text and "tok/s" in text
    assert "9-9" in text

"""The routes of every task (slice 11, section 33)."""

from __future__ import annotations

import pytest

from labpilot.llm import routes
from labpilot.llm.accuracy import ACCURACY
from labpilot.llm.ratings import RATINGS
from labpilot.llm.registry import CHAIN, KNOWN_DEAD, NOT_TRUSTED

TASKS = sorted(routes.TASKS)
BY_NAME = {t.name: t for t in CHAIN}
LIVE = [t.name for t in CHAIN if t.name not in KNOWN_DEAD]


def tiers(task):
    return routes.ROUTES[task].tiers


def test_there_is_a_route_for_every_task_and_for_no_other():
    assert set(routes.ROUTES) == set(routes.TASKS)


def test_every_live_tier_has_a_rating_and_no_rating_is_for_a_dead_or_unknown_tier():
    assert set(RATINGS) == set(LIVE)


@pytest.mark.parametrize("task", TASKS)
def test_a_route_holds_only_live_tiers_and_each_once(task):
    names = tiers(task)
    assert len(names) == len(set(names))
    assert set(names) <= set(LIVE)


@pytest.mark.parametrize("task", TASKS)
def test_every_route_holds_at_least_seven_models(task):
    assert len({routes._model(n) for n in tiers(task)}) >= 7


def test_every_live_tier_is_in_a_route_or_named_with_a_reason():
    in_a_route = {n for task in TASKS for n in tiers(task)}
    left = routes.left_out()
    assert set(LIVE) == in_a_route | set(left)
    assert all(reason for reason in left.values())


@pytest.mark.parametrize("task", TASKS)
def test_a_tier_that_is_not_trusted_still_serves_as_the_last_backup(task):
    spec = routes.TASKS[task]
    allowed = {
        t.name
        for t in CHAIN
        if t.name in NOT_TRUSTED
        and t.name in RATINGS
        and routes.why_not(RATINGS[t.name], t, spec) is None
    }
    assert allowed <= set(tiers(task))


def test_some_route_holds_a_tier_that_is_not_trusted():
    assert any(n in NOT_TRUSTED for task in TASKS for n in tiers(task))


@pytest.mark.parametrize("task", TASKS)
def test_a_tier_that_is_not_trusted_comes_after_every_trusted_one(task):
    names = tiers(task)
    flags = [n in NOT_TRUSTED for n in names]
    assert flags == sorted(flags)


@pytest.mark.parametrize("task", TASKS)
def test_a_tier_below_the_strength_of_a_task_is_only_at_the_end_of_a_simple_task(task):
    spec = routes.TASKS[task]
    weak = [RATINGS[n].strength < spec.min_strength for n in tiers(task)]
    # (a tier with too few calls a day is also a backup; it may stand among the weak)
    if not spec.simple:
        assert not any(weak)
    trusted = [
        w for n, w in zip(tiers(task), weak, strict=True) if n not in NOT_TRUSTED
    ]
    assert trusted == sorted(trusted)


@pytest.mark.parametrize("task", TASKS)
def test_a_task_that_reads_no_file_never_spends_a_scarce_tier(task):
    if not routes.TASKS[task].reads_files:
        assert not any(RATINGS[n].scarce for n in tiers(task))


@pytest.mark.parametrize("task", [t for t in TASKS if routes.TASKS[t].kind == "many"])
def test_a_task_with_many_calls_has_no_one_at_a_time_or_slow_rate_tier(task):
    for name in tiers(task):
        tier = BY_NAME[name]
        assert getattr(tier, "max_concurrent", None) != 1, name
        rpm = getattr(tier, "requests_per_minute", None)
        assert rpm is None or rpm >= routes.MANY_MIN_RPM, name


@pytest.mark.parametrize("task", TASKS)
def test_every_tier_can_take_the_prompt_and_write_the_answer_of_its_task(task):
    spec = routes.TASKS[task]
    for name in tiers(task):
        tier = BY_NAME[name]
        assert spec.max_tokens <= tier.max_output_tokens, name
        assert (
            spec.prompt_tokens * routes.MARGIN + spec.max_tokens <= tier.context_window
        ), name
        cap = getattr(tier, "max_input_tokens", None)
        assert cap is None or spec.prompt_tokens * routes.MARGIN <= cap, name


def test_the_answer_routes_ask_what_the_answer_prompts_ask():
    asked = tuple(
        routes.TASKS[t].max_tokens
        for t in ("respond_chat", "respond_one", "respond_two")
    )
    assert asked == (8_000, 16_000, 32_000)


@pytest.mark.parametrize("task", TASKS)
def test_the_keys_of_one_google_model_stand_together_in_key_order(task):
    names = list(tiers(task))
    for name in names:
        if " (key 2)" in name:
            base = name.replace(" (key 2)", "")
            i = names.index(base)
            assert names[i : i + 3] == [base, f"{base} (key 2)", f"{base} (key 3)"]


def test_every_measured_family_is_the_family_of_a_live_tier():
    families = {r.family for r in RATINGS.values()}
    for task, measured in ACCURACY.items():
        assert task in routes.TASKS
        assert set(measured) <= families, task


def test_a_little_more_accuracy_never_buys_a_much_slower_model(monkeypatch):
    from dataclasses import replace

    base = RATINGS["Gemini 3.5 Flash-Lite"]
    fast, slow = replace(base, family="fast"), replace(base, family="slow")
    monkeypatch.setitem(
        routes.ACCURACY, "gate", {"fast": (0.90, 3.0, 20), "slow": (0.95, 60.0, 20)}
    )
    assert routes.key(fast, "gate") > routes.key(slow, "gate")


def test_a_lot_more_accuracy_wins_in_the_long_report(monkeypatch):
    from dataclasses import replace

    base = RATINGS["Gemini 3.5 Flash-Lite"]
    fast, slow = replace(base, family="fast"), replace(base, family="slow")
    monkeypatch.setitem(
        routes.ACCURACY,
        "respond_two",
        {"fast": (0.80, 30.0, 20), "slow": (0.95, 150.0, 20)},
    )
    assert routes.key(slow, "respond_two") > routes.key(fast, "respond_two")


def test_why_not_refuses_a_prompt_over_the_input_cap_of_a_tier():
    gemma = BY_NAME["Gemma 4 26B A4B"]
    big = routes.Task("small", 1, 20_000, 1_000, 1, 90)
    assert "input cap" in routes.why_not(RATINGS[gemma.name], gemma, big)


def test_why_not_refuses_a_tier_whose_output_cap_is_below_the_answer():
    tier = BY_NAME["DeepSeek V4.1 Flash (Token Harbor)"]
    assert "output cap" in routes.why_not(
        RATINGS[tier.name], tier, routes.TASKS["respond_two"]
    )


def test_resolve_keeps_the_route_order_and_drops_names_the_chain_lacks():
    names = tiers("gate")
    some = [BY_NAME[names[2]], BY_NAME[names[0]]]
    assert routes.resolve("gate", some) == (BY_NAME[names[0]], BY_NAME[names[2]])


def test_the_stop_is_longer_for_a_bigger_job():
    assert (
        routes.ROUTES["gate"].stop
        < routes.ROUTES["audit"].stop
        < routes.ROUTES["respond_two"].stop
    )


def test_the_same_model_on_a_slower_provider_ranks_lower(monkeypatch):
    # The bench gives the task's time to the model FAMILY; each tier's provider
    # then scales it, so the same model on a slow provider ranks a little lower.
    from dataclasses import replace

    base = RATINGS["Gemini 3.5 Flash-Lite"]
    quick = replace(base, family="fam", seconds=2.0, big_seconds=2.0)
    slow = replace(base, family="fam", seconds=8.0, big_seconds=8.0)
    monkeypatch.setitem(routes.RATINGS, "quick tier", quick)
    monkeypatch.setitem(routes.RATINGS, "slow tier", slow)
    monkeypatch.setitem(routes.ACCURACY, "gate", {"fam": (0.90, 10.0, 20)})
    assert routes.seconds(quick, "gate") < routes.seconds(slow, "gate")
    assert routes.key(quick, "gate") > routes.key(slow, "gate")


def test_a_provider_moves_the_time_of_its_family_at_most_by_the_set_factor(
    monkeypatch,
):
    from dataclasses import replace

    base = RATINGS["Gemini 3.5 Flash-Lite"]
    normal = replace(base, family="fam", seconds=2.0, big_seconds=2.0)
    crawl = replace(base, family="fam", seconds=2000.0, big_seconds=2000.0)
    monkeypatch.setitem(routes.RATINGS, "normal tier", normal)
    monkeypatch.setitem(routes.RATINGS, "other normal tier", normal)
    monkeypatch.setitem(routes.RATINGS, "crawl tier", crawl)
    monkeypatch.setitem(routes.ACCURACY, "gate", {"fam": (0.90, 10.0, 20)})
    low, high = routes.PROVIDER_FACTOR
    assert routes.seconds(crawl, "gate") == 10.0 * high
    assert routes.seconds(normal, "gate") == 10.0


def test_a_family_the_bench_did_not_measure_takes_its_own_speed_test():
    from dataclasses import replace

    base = RATINGS["Gemini 3.5 Flash-Lite"]
    rating = replace(base, family="never measured", seconds=1.0, big_seconds=50.0)
    assert routes.seconds(rating, "gate") == 1.0
    assert routes.seconds(rating, "audit") == 50.0


def test_one_at_a_time_costs_only_in_a_step_that_runs_beside_others():
    rating = RATINGS["Gemini 3.5 Flash-Lite"]
    for task in ("rewrite", "respond_two"):  # nothing else runs then
        assert routes.TASKS[task].alone
        assert routes.key(rating, task, one_at_a_time=True) == routes.key(rating, task)
    for task in ("audit", "judge"):  # they run beside the other finders
        assert not routes.TASKS[task].alone
        gap = routes.key(rating, task) - routes.key(rating, task, one_at_a_time=True)
        assert gap == pytest.approx(routes.BUSY_PENALTY)


def test_a_close_tier_that_is_often_busy_drops_below_a_free_one(monkeypatch):
    # In a step that runs beside others, a one-at-a-time tier only a little more
    # accurate than a free tier must rank below it: its slot is often taken.
    from dataclasses import replace

    base = RATINGS["Gemini 3.5 Flash-Lite"]
    busy, free = replace(base, family="busy"), replace(base, family="free")
    monkeypatch.setitem(
        routes.ACCURACY, "audit", {"busy": (0.84, 100.0, 20), "free": (0.80, 100.0, 20)}
    )
    assert not routes.TASKS["audit"].alone
    assert routes.key(busy, "audit", one_at_a_time=True) < routes.key(free, "audit")


def test_a_much_stronger_tier_still_leads_although_it_takes_one_call_at_a_time(
    monkeypatch,
):
    from dataclasses import replace

    base = RATINGS["Gemini 3.5 Flash-Lite"]
    strong, weak = replace(base, family="strong"), replace(base, family="weak")
    monkeypatch.setitem(
        routes.ACCURACY,
        "audit",
        {"strong": (0.95, 100.0, 20), "weak": (0.70, 100.0, 20)},
    )
    assert routes.key(strong, "audit", one_at_a_time=True) > routes.key(weak, "audit")


def test_each_provider_has_one_vote_in_the_speed_of_its_family(monkeypatch):
    # Three tiers of one model on one provider must not outvote two others: the
    # scale of a tier stays the same when a provider adds another key or id.
    from dataclasses import replace

    base = RATINGS["Gemini 3.5 Flash-Lite"]

    def tier(provider, secs):
        return replace(
            base, family="fam", provider=provider, seconds=secs, big_seconds=secs
        )

    monkeypatch.setitem(routes.ACCURACY, "gate", {"fam": (0.90, 10.0, 20)})
    for name, rating in {
        "a": tier("fast", 2.0),
        "b": tier("fast", 2.0),
        "c": tier("fast", 2.0),
        "d": tier("mid", 4.0),
        "e": tier("slow", 6.0),
    }.items():
        monkeypatch.setitem(routes.RATINGS, name, rating)
    # one vote each: median(2, 4, 6) = 4, so the 4-second tier keeps the bench time
    assert routes.seconds(routes.RATINGS["d"], "gate") == 10.0
    monkeypatch.setitem(routes.RATINGS, "f", tier("fast", 2.0))  # a fourth key
    assert routes.seconds(routes.RATINGS["d"], "gate") == 10.0


def test_plan_is_not_alone_because_it_can_run_beside_the_summaries():
    assert not routes.TASKS["plan"].alone


def test_no_two_tasks_walk_the_same_route():
    walks = {name: route.tiers for name, route in routes.ROUTES.items()}
    assert len(set(walks.values())) == len(walks)


@pytest.mark.parametrize("task", TASKS)
def test_a_model_placed_many_times_is_not_pushed_down_for_it(task):
    # Inside the first group (strong, trusted, enough calls a day) the tiers stand
    # in the order of their score alone: no penalty for a model or a provider that
    # is already high in the route. The keys of one Google model stand together,
    # so only the first key of each such model is compared.
    t = routes.TASKS[task]
    by_name = {tier.name: tier for tier in routes.CHAIN}
    first_group = [
        name
        for name in routes.ROUTES[task].tiers
        if name not in routes.NOT_TRUSTED
        and RATINGS[name].strength >= t.min_strength
        and RATINGS[name].per_day / t.calls >= routes.FEW_QUESTIONS
    ]
    leaders, seen = [], set()
    for name in first_group:
        model = routes._model(name)
        if RATINGS[name].provider == "google":
            if model in seen:
                continue
            seen.add(model)
        leaders.append(name)
    scores = [
        routes.key(
            RATINGS[n],
            task,
            one_at_a_time=getattr(by_name[n], "max_concurrent", None) == 1,
        )
        for n in leaders
    ]
    assert scores == sorted(scores, reverse=True)

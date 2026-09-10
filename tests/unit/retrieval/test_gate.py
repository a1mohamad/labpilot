from __future__ import annotations

from labpilot.retrieval.gate import SKIP_MARGIN, margin, should_rerank


def test_the_margin_is_the_lead_of_the_best_hit_over_the_runner_up():
    assert margin((0.9, 0.4, 0.1)) == 0.5


def test_the_margin_reads_the_two_best_scores_not_the_first_two():
    """A gate that depends on its caller having sorted the list is a gate that
    breaks the first time somebody fuses two rankings and forgets - and it
    breaks by comparing the wrong pair, with no error anywhere."""
    assert margin((0.1, 0.4, 0.9)) == 0.5


def test_one_hit_leads_nothing_so_the_margin_is_zero():
    """Claiming a large lead here would make the gate skip reranking exactly
    when it has the least evidence for doing so."""
    assert margin((0.9,)) == 0.0
    assert margin(()) == 0.0


def test_fewer_than_two_hits_cannot_be_reordered_so_there_is_nothing_to_buy():
    assert should_rerank((0.9,), skip_margin=0.01) is False
    assert should_rerank((), skip_margin=0.01) is False


def test_an_uncalibrated_gate_is_off_and_always_reranks():
    """None means the threshold has not been earned yet. Shipping "always
    rerank" is the behaviour that cannot be silently wrong, and a threshold in
    this project is calibrated, never chosen."""
    assert SKIP_MARGIN is None
    assert should_rerank((0.99, 0.01), skip_margin=None) is True


def test_an_obvious_winner_skips_and_a_close_call_reranks():
    assert should_rerank((0.99, 0.01), skip_margin=0.10) is False
    assert should_rerank((0.61, 0.60), skip_margin=0.10) is True


def test_a_margin_exactly_on_the_threshold_reranks():
    """The cheap side of a tie keeps the evidence honest: pay the call rather
    than guess, because the gate exists to save money, not to decide rankings.

    The numbers are EXACT binary fractions on purpose. The first version of
    this test used 0.70 and 0.60, whose difference is 0.09999999999999998 and
    never equals the threshold - so `<=` and `<` behaved identically and the
    test could not fail. Mutation testing caught it; reading it did not.
    """
    assert (0.75 - 0.25) == 0.5  # premise: the boundary is really a boundary

    assert should_rerank((0.75, 0.25), skip_margin=0.5) is True

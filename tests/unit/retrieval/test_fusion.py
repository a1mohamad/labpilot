from __future__ import annotations

import pytest

from labpilot.retrieval import (
    RRF_K,
    RRF_WEIGHTS,
    SCORE_ALPHA,
    score_fusion,
    weighted_rrf,
)


def test_a_chunk_both_rankers_found_beats_a_chunk_only_one_found():
    """The whole point of fusing: agreement is evidence.

    Chunk 9 is second on both lists and so is never anyone's best guess.
    Chunk 1 is first on one list and absent from the other. Two seconds beat
    one first, which is what RRF exists to express.
    """
    fused = weighted_rrf([1, 9], [7, 9], weights=(1.0, 1.0))

    assert fused[0] == 9


def test_a_zero_weight_ranker_cannot_change_the_order():
    """The keyword weight is a dial, and 0 must really mean off.

    Everything the second list alone knows about scores 0, so it can only be
    appended after the first list - never interleaved into it.
    """
    dense = [4, 8, 15, 16]

    fused = weighted_rrf(dense, [16, 15, 8, 4], weights=(1.0, 0.0))

    assert list(fused[: len(dense)]) == dense


def test_a_bigger_weight_lets_the_second_ranker_win():
    """The opposite direction of the same dial, so a weight that is read but
    never applied cannot pass both tests."""
    dense = [1, 2]
    sparse = [2, 1]

    assert weighted_rrf(dense, sparse, weights=(1.0, 0.1))[0] == 1
    assert weighted_rrf(dense, sparse, weights=(1.0, 5.0))[0] == 2


def test_a_smaller_k_makes_the_top_places_count_for_more():
    """k is the flattener: score is weight / (k + place).

    At a large k every place is worth almost the same, so a chunk found twice
    low down overtakes a chunk found once at the very top. At a small k the
    top place keeps its advantage. That is why k=5 and k=60 are different
    strategies rather than different scales.
    """
    # Chunk 1 is first on the dense list and nowhere on the other.
    # Chunk 2 is sixth and second - never anyone's best guess, but found twice.
    dense = [1, 91, 92, 93, 94, 2]
    sparse = [95, 2]

    assert weighted_rrf(dense, sparse, k=1, weights=(1.0, 1.0))[0] == 1
    assert weighted_rrf(dense, sparse, k=60, weights=(1.0, 1.0))[0] == 2


def test_the_fused_order_is_repeatable_when_scores_tie():
    """Two chunks with identical scores must not swap between runs, or two
    reports of the same comparison stop being comparable - the same reason
    every call is made at temperature 0.

    The fixture has to make a REAL tie, and the higher chunk_index has to be
    seen FIRST. Chunk 2 is first on the dense list and second on the sparse
    one, and chunk 1 is the mirror of that, so the two scores are equal to the
    bit. Without the chunk_index tie-break the answer falls out as insertion
    order - which is (2, 1) here, not (1, 2).
    """
    fused = weighted_rrf([2, 1], [1, 2], weights=(1.0, 1.0))

    assert fused == (1, 2)


def test_every_ranking_needs_its_own_weight():
    """Silently reusing or dropping a weight would quietly change the mix."""
    with pytest.raises(ValueError, match="weight"):
        weighted_rrf([1, 2], [3, 4], [5, 6], weights=(1.0, 0.15))


def test_a_k_below_one_is_refused():
    """At k = 0 the first place divides by 1 and still works, so nothing
    fails loudly - but a negative k divides by zero at place -k. Refusing
    below 1 keeps the formula in the region the sweep actually measured."""
    with pytest.raises(ValueError, match="k must be positive"):
        weighted_rrf([1, 2], [3, 4], k=0)


def test_the_defaults_are_the_measured_ones_and_not_the_textbook_ones():
    """This test guards a DECISION, not a behaviour.

    The textbook defaults are k=60 and w=1.0, and that is the worst row in our
    own table - the only setting that lost recall@50, on two corpora and two
    embedders. Anyone "correcting" these values back to the published ones
    should have to argue with a red build first.
    """
    assert (RRF_K, RRF_WEIGHTS) == (5, (1.0, 0.15))
    assert RRF_K < 60
    assert RRF_WEIGHTS[1] < 1.0


# --- score fusion: THE METHOD THAT SHIPS -----------------------------------
#
# `score a=0.85` was #1 of 51 settings over 20 corpora and 423 queries, so it
# is what the ask path calls. wRRF above stays reachable and is NOT what was
# measured best - keep the two straight.


def test_the_scales_of_the_two_channels_cannot_matter():
    """THE STEP RRF EXISTS TO AVOID, and therefore the one that can be wrong.

    A cosine similarity lives in [-1, 1] and a BM25 score is unbounded - ours
    reach 30+. Adding them raw would let BM25 outvote cosine by arithmetic
    rather than by agreement, whatever alpha said.
    """
    dense = [(1, 0.9), (2, 0.1)]
    small = score_fusion(dense, [(2, 0.02), (3, 0.01)])
    large = score_fusion(dense, [(2, 20.0), (3, 10.0)])

    assert small == large


def test_the_dense_channel_carries_the_weight():
    """alpha = 0.85 on dense. The keyword side reorders and rescues; it must
    never be able to take over, which is what makes always-on safe."""
    fused = score_fusion([(1, 1.0), (2, 0.0)], [(2, 1.0), (1, 0.0)])

    assert fused[0] == 1


def test_a_chunk_only_the_keyword_channel_found_still_scores():
    """`D2` in one line: CLIP_NORM = 1.5 was place 46 on cosine, 4 on BM25.

    A missing channel contributes 0.0 rather than excluding the chunk, so the
    rescue is possible at all.
    """
    fused = score_fusion([(1, 1.0)], [(2, 1.0)])

    assert set(fused) == {1, 2}


def test_a_flat_channel_counts_as_agreement_not_as_absence():
    """BM25 returns equal scores when every hit holds the query terms alike.

    min-max over a flat list has no range to divide by. Mapping it to 0.0
    would delete the channel exactly when it agreed with itself most strongly,
    so the degenerate case is 1.0 - and this matches the benchmark that
    produced the measurement.
    """
    fused = score_fusion([(1, 0.5), (2, 0.5)], [(2, 7.0), (3, 7.0)])

    assert fused[0] == 2, "the chunk BOTH channels found must lead"


def test_tied_chunks_are_ordered_by_id_and_not_by_set_iteration():
    """`temperature: 0` buys nothing if retrieval is unstable, and a full tie
    is COMMON here: min-max maps every flat channel to 1.0.

    THE IDS ARE FIVE DIGITS ON PURPOSE. The first version of this test used
    3, 5 and 9, and removing the tie-break did not fail it - because a CPython
    set of small ints happens to iterate in ascending order, so the coincidence
    did the tie-break's job. A real repository reaches 16,754 chunks, and there
    set order is not sorted:

        with the tie-break     (1327, 8485, 13782, 15923, 16754)
        without it             (8485, 1327, 16754, 15923, 13782)

    Same family as "a fixture numbered from zero cannot tell an id from a
    position": the fixture was too tidy to be able to fail.
    """
    ids = [13782, 1327, 8485, 16754, 15923]
    dense = [(i, 1.0) for i in ids]
    sparse = [(i, 2.0) for i in reversed(ids)]

    assert score_fusion(dense, sparse) == tuple(sorted(ids))


def test_an_alpha_outside_the_unit_interval_is_a_callers_bug():
    with pytest.raises(ValueError, match="weight on the dense channel"):
        score_fusion([(1, 1.0)], [(2, 1.0)], alpha=1.5)


def test_the_shipped_alpha_is_the_measured_one():
    """0.85 is not a tidy default - it won a 51-setting search. RRF's own k=60
    and w=1.0 were tidy defaults and were the WORST row in our table."""
    assert SCORE_ALPHA == 0.85

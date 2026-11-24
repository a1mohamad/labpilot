from __future__ import annotations

import pytest

from labpilot.retrieval import SCORE_ALPHA, score_fusion


def test_the_scales_of_the_two_channels_cannot_matter():
    """THE STEP RANK FUSION AVOIDS, and therefore the one that can be wrong.

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
    """0.85 is not a tidy default - it won a 51-setting search."""
    assert SCORE_ALPHA == 0.85

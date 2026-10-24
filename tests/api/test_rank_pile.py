from labpilot.api import searching
from labpilot.ingest import Chunk
from labpilot.rerank import SKIP, Ranking


def chunk(index):
    return Chunk(
        text=f"text {index}",
        source="train.py",
        start_line=index,
        end_line=index + 1,
        side="B",
        artifact_id="B-1",
        chunk_index=index,
    )


def pile(size):
    return tuple(chunk(100 + i) for i in range(size))


def reranker(order, model="fake-rerank"):
    calls = []

    def rank(question, documents, *, top_n):
        calls.append((question, list(documents), top_n))
        return Ranking(order=order(len(documents)), model=model)

    return rank, calls


def test_the_reranker_reads_only_the_window_of_the_pile():
    big = pile(35)
    assert len(big) > searching.RERANK_WINDOW
    rank, calls = reranker(lambda n: tuple(range(n)))

    searching.rank_pile("why?", big, rank=rank)

    assert calls[0][1] == [c.text for c in big[: searching.RERANK_WINDOW]]


def test_the_question_is_the_one_we_were_given_and_the_whole_order_is_asked_for():
    rank, calls = reranker(lambda n: tuple(range(n)))

    searching.rank_pile("why do results differ?", pile(5), rank=rank)

    assert calls[0][0] == "why do results differ?"
    assert calls[0][2] is None


def test_positions_are_mapped_back_to_the_chunks_not_to_their_ids():
    rank, _ = reranker(lambda n: (2, 0, 1))

    kept = searching.rank_pile("why?", pile(3), rank=rank)

    assert [c.chunk_index for c in kept] == [102, 100, 101]


def test_the_reranked_best_come_first_and_the_rest_of_the_pile_follows():
    # R23: the selector, not this function, decides how many fit the prompt.
    assert searching.RERANK_WINDOW > searching.RERANK_TOP_N
    big = pile(40)
    rank, _ = reranker(lambda n: tuple(reversed(range(n))))

    kept = searching.rank_pile("why?", big, rank=rank)

    best = big[: searching.RERANK_WINDOW][::-1][: searching.RERANK_TOP_N]
    assert kept[: searching.RERANK_TOP_N] == best
    assert sorted(kept, key=lambda c: c.chunk_index) == sorted(
        big, key=lambda c: c.chunk_index
    )
    rest = [c for c in big if c not in best]
    assert list(kept[searching.RERANK_TOP_N :]) == rest


def test_when_no_tier_answered_the_first_vector_top_n_of_the_pile_are_kept():
    big = pile(40)
    rank, _ = reranker(lambda n: tuple(range(n)), model=SKIP)

    kept = searching.rank_pile("why?", big, rank=rank)

    assert kept[: searching.VECTOR_TOP_N] == big[: searching.VECTOR_TOP_N]
    assert kept == big


def test_an_empty_pile_costs_no_call():
    rank, calls = reranker(lambda n: ())

    assert searching.rank_pile("why?", (), rank=rank) == ()
    assert calls == []

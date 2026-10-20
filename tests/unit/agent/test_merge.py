from labpilot.agent.merge import make_merge_node, merge_chunks
from labpilot.ingest import Chunk


def chunk(index, *, side="B", artifact="B-1"):
    return Chunk(
        text=f"text {index}",
        source="train.py",
        start_line=index,
        end_line=index + 1,
        side=side,
        artifact_id=artifact,
        chunk_index=index,
    )


def indexes(chunks):
    return [c.chunk_index for c in chunks]


def test_the_chunks_of_every_query_are_taken_in_turns_by_rank():
    first = (chunk(1), chunk(2), chunk(3))
    second = (chunk(11), chunk(12))

    merged = merge_chunks([first, second])

    assert indexes(merged) == [1, 11, 2, 12, 3]


def test_a_cut_from_the_end_takes_a_little_from_every_query():
    queries = [tuple(chunk(100 * q + r) for r in range(4)) for q in range(3)]

    merged = merge_chunks(queries)

    kept = indexes(merged[:6])
    assert [index // 100 for index in kept].count(0) == 2
    assert [index // 100 for index in kept].count(1) == 2
    assert [index // 100 for index in kept].count(2) == 2


def test_a_chunk_found_by_two_queries_is_kept_once_in_its_best_place():
    first = (chunk(1), chunk(2))
    second = (chunk(2), chunk(3))

    merged = merge_chunks([first, second])

    assert indexes(merged) == [1, 2, 3]


def test_the_same_index_in_two_artifacts_is_two_different_chunks():
    on_a = chunk(5, side="A", artifact="A-1")
    on_b = chunk(5, side="B", artifact="B-1")

    merged = merge_chunks([(on_a,), (on_b,)])

    assert merged == (on_a, on_b)


def test_a_query_that_found_nothing_does_not_stop_the_others():
    merged = merge_chunks([(), (chunk(1),), ()])

    assert indexes(merged) == [1]


def test_no_search_at_all_gives_no_chunks():
    assert merge_chunks([]) == ()


def on_a(index):
    return chunk(index, side="A", artifact="A-1")


def state(found, question="why?"):
    return {"found": found, "question": question, "sides": "the sides"}


def test_each_side_is_ranked_once_with_the_question_and_its_own_pile():
    calls = []

    def rank_side(question, pile):
        calls.append((question, indexes(pile)))
        return pile

    node = make_merge_node(lambda sides: None, rank_side)
    first_a = (on_a(1), on_a(2))
    second_a = (on_a(2), on_a(3))

    node(state([first_a, (chunk(7),), second_a]))

    assert calls == [("why?", [1, 2, 3]), ("why?", [7])]


def test_the_ranked_piles_are_joined_with_side_a_first():
    node = make_merge_node(lambda sides: None, lambda question, pile: pile[:1])

    out = node(state([(chunk(1), chunk(2)), (on_a(5),)]))

    assert [(c.side, c.chunk_index) for c in out["chunks"]] == [("A", 5), ("B", 1)]


def test_a_side_with_no_chunk_is_never_ranked():
    calls = []

    def rank_side(question, pile):
        calls.append(pile)
        return pile

    node = make_merge_node(lambda sides: None, rank_side)

    node(state([(), (chunk(1),)]))

    assert len(calls) == 1


def test_the_node_gives_the_totals_and_empties_the_found_lists():
    node = make_merge_node(lambda sides: {"A": 3, "B": 9}, lambda question, pile: pile)

    out = node(state([(chunk(1),)]))

    assert out["totals"] == {"A": 3, "B": 9}
    assert out["found"].value == []

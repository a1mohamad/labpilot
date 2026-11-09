from labpilot.agent import Bug, Difference
from labpilot.agent.merge import make_merge_node
from labpilot.agent.respond import deciding_parts, make_respond_node, with_parts
from labpilot.ingest import Chunk


def chunk(index, side="B"):
    return Chunk(
        text=f"text {index}",
        source="f.py",
        start_line=index,
        end_line=index,
        side=side,
        artifact_id=f"{side}-1",
        chunk_index=index,
    )


def difference(kind, evidence, unclear=False):
    return Difference(
        kind, "B does x", "[f.py]", "x", evidence=evidence, unclear=unclear
    )


def bug(verdict, evidence):
    return Bug("code", "it breaks", "[f.py]", "x", verdict=verdict, evidence=evidence)


def test_differences_and_real_bugs_come_first_then_the_rest_each_once():
    found = deciding_parts(
        [
            difference("silent", chunk(3)),
            difference("differs", chunk(4)),
            difference("missing", chunk(5), unclear=True),
        ],
        [bug("unclear", chunk(6)), bug("real", chunk(2)), bug("real", chunk(4))],
    )

    assert [c.chunk_index for c in found] == [4, 2, 3, 5, 6]


def test_findings_with_no_part_give_none():
    assert deciding_parts([difference("differs", None)], [bug("real", None)]) == ()


def test_respond_hands_the_findings_and_their_parts_to_the_prompt():
    seen = []

    def make_prompt(chunks, **kwargs):
        seen.append(kwargs)
        return "p", chunks

    node = make_respond_node(make_prompt, lambda prompt: "r")
    differences = [difference("differs", chunk(2))]
    bugs = [bug("real", chunk(4))]
    node(
        {
            "chunks": (chunk(9),),
            "question": "why?",
            "totals": {"B": 9},
            "a": "A-1",
            "b": "B-1",
            "differences": differences,
            "bugs": bugs,
        }
    )

    assert seen[0]["differences"] == differences
    assert seen[0]["bugs"] == bugs
    assert [c.chunk_index for c in seen[0]["evidence"]] == [2, 4]


def test_without_findings_respond_hands_them_over_empty():
    seen = []
    node = make_respond_node(
        lambda chunks, **kw: seen.append(kw) or ("p", chunks), lambda p: "r"
    )

    node({"chunks": (), "question": "why?", "totals": None, "a": "A-1", "b": "B-1"})

    assert seen[0]["differences"] == ()
    assert seen[0]["bugs"] == ()
    assert seen[0]["evidence"] == ()
    assert seen[0]["reference"] is False


def test_a_side_small_enough_is_read_whole_and_not_ranked():
    whole = (chunk(0, "A"), chunk(1, "A"), chunk(2, "A"))
    ranked = []

    def rank_side(question, pile):
        ranked.append(pile[0].side)
        return pile

    node = make_merge_node(
        lambda sides: {"A": 3, "B": 9},
        rank_side,
        lambda sides, side: whole if side == "A" else None,
    )
    out = node(
        {
            "question": "why?",
            "sides": {},
            "found": [(chunk(1, "A"),), (chunk(5, "B"),)],
        }
    )

    assert out["chunks"] == (*whole, chunk(5, "B"))
    assert ranked == ["B"]


def test_without_a_whole_side_function_every_side_is_ranked():
    node = make_merge_node(lambda sides: {}, lambda question, pile: pile)

    out = node({"question": "q", "sides": {}, "found": [(chunk(1, "A"),)]})

    assert out["chunks"] == (chunk(1, "A"),)


def test_a_missing_deciding_part_goes_at_the_end_and_no_id_moves():
    held = (chunk(0), chunk(1), chunk(2))

    joined = with_parts(held, (chunk(9), chunk(1)))

    assert [c.chunk_index for c in joined] == [0, 1, 2, 9]


def test_respond_numbers_the_prompt_and_saves_the_chunks_on_one_list():
    seen = []

    def make_prompt(chunks, **kwargs):
        seen.append(chunks)
        return "p", chunks

    node = make_respond_node(make_prompt, lambda prompt: "r")
    out = node(
        {
            "chunks": (chunk(5), chunk(6)),
            "question": "why?",
            "totals": {"B": 9},
            "a": "A-1",
            "b": "B-1",
            "differences": [difference("differs", chunk(2))],
        }
    )

    assert [c.chunk_index for c in seen[0]] == [5, 6, 2]
    assert out["chunks"] == seen[0]

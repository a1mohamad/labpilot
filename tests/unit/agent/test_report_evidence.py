from labpilot.agent import A_SILENT, Claim, CodeFinding, Finding
from labpilot.agent.merge import make_merge_node
from labpilot.agent.respond import deciding_parts, make_respond_node
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


CLAIM = Claim("fact", "[paper.md]", "fact")


def finding(verdict, evidence):
    return Finding(CLAIM, verdict, "", "[f.py]", "q", "n", evidence)


def code(evidence, a_says="A says otherwise"):
    return CodeFinding("B does x", "[f.py]", "x", a_says, evidence)


def test_mismatches_come_first_then_differences_then_silences_each_once():
    found = deciding_parts(
        [finding("match", chunk(1)), finding("mismatch", chunk(2))],
        [code(chunk(3), A_SILENT), code(chunk(4)), code(chunk(2))],
    )

    assert [c.chunk_index for c in found] == [2, 4, 3]


def test_findings_with_no_part_give_none():
    assert deciding_parts([finding("absent", None)], [code(None)]) == ()


def test_respond_hands_the_deciding_parts_to_the_prompt():
    seen = []

    def make_prompt(chunks, **kwargs):
        seen.append(kwargs)
        return "p", chunks

    node = make_respond_node(make_prompt, lambda prompt: "r")
    node(
        {
            "chunks": (chunk(9),),
            "question": "why?",
            "totals": {"B": 9},
            "a": "A-1",
            "b": "B-1",
            "findings": [finding("mismatch", chunk(2))],
            "code_findings": [code(chunk(4))],
        }
    )

    assert [c.chunk_index for c in seen[0]["evidence"]] == [2, 4]


def test_without_findings_respond_gives_no_evidence():
    seen = []
    node = make_respond_node(
        lambda chunks, **kw: seen.append(kw) or ("p", chunks), lambda p: "r"
    )

    node({"chunks": (), "question": "why?", "totals": None, "a": "A-1", "b": "B-1"})

    assert "evidence" not in seen[0]


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

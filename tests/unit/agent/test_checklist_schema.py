import pytest

from labpilot.agent import (
    MAX_OBLIGATIONS,
    BugsError,
    merge_obligations,
    read_checklist,
    read_checklist_audit,
)
from labpilot.ingest import Chunk

SOURCES = ["[train.py · def step · lines 1-9]", "[train.py · def eval · lines 10-19]"]


TEXTS = ["bias2 = 1 - beta1**step", "threshold = best_on(val)"]


def chunk(index):
    return Chunk(
        text=f"text {index}",
        source="train.py",
        start_line=index,
        end_line=index,
        side="B",
        artifact_id="B-1",
        chunk_index=index,
    )


RULES = ("Is the bias correction of the second moment made with beta2?", "Is it safe?")


def test_a_checklist_is_read_and_cleaned():
    assert read_checklist({"obligations": [" Is it A? ", "", 3, "Is it B?"]}) == (
        "Is it A?",
        "Is it B?",
    )


@pytest.mark.parametrize(
    "arguments",
    [
        {"obligations": "Is it A?"},
        {"obligations": []},
        {"obligations": ["Is it A?"] * (MAX_OBLIGATIONS + 1)},
    ],
)
def test_a_checklist_that_is_not_a_good_list_is_refused(arguments):
    with pytest.raises(BugsError):
        read_checklist(arguments)


def test_the_same_obligation_from_two_checklists_is_kept_once():
    assert merge_obligations(
        [("Is the key long?", "Is MD5 refused?"), ("is the key LONG",)]
    ) == (
        "Is the key long?",
        "Is MD5 refused?",
    )


def test_each_broken_rule_becomes_a_concept_suspect_with_its_rule():
    answers = {
        "answers": [
            {"n": 0, "meets": "no", "part": 0, "quote": "beta1**step", "text": "beta1"},
            {"n": 1, "meets": "yes"},
        ]
    }

    (got,) = read_checklist_audit(answers, RULES, SOURCES, TEXTS, [chunk(0), chunk(1)])

    assert got.kind == "concept" and got.source == SOURCES[0]
    assert got.text == f"beta1 [obligation: {RULES[0]}]"
    assert got.evidence == chunk(0)


@pytest.mark.parametrize(
    "item",
    [
        {"n": 7, "meets": "no", "part": 0, "quote": "beta1"},
        {"n": 0, "meets": "maybe", "part": 0, "quote": "beta1"},
        {"n": 0, "meets": "no", "part": 9, "quote": "beta1"},
        {"n": 0, "meets": "no", "part": 0, "quote": "never written"},
        {"n": 0, "meets": "no"},
    ],
)
def test_a_no_that_cannot_be_placed_or_named_is_dropped(item):
    answers = {"answers": [item, {"n": 1, "meets": "yes"}]}

    assert read_checklist_audit(answers, RULES, SOURCES, TEXTS) == ()


@pytest.mark.parametrize(
    "arguments",
    [{"answers": "no"}, {"answers": []}, {"answers": [{"n": 9, "meets": "no"}]}],
)
def test_an_audit_that_answers_no_rule_is_refused(arguments):
    with pytest.raises(BugsError):
        read_checklist_audit(arguments, RULES, SOURCES, TEXTS)


@pytest.mark.parametrize("meets", ["yes", "n/a"])
def test_a_rule_that_is_met_or_does_not_apply_is_not_a_defect(meets):
    # A model often gives the part and the quote with a "yes" too.
    answers = {"answers": [{"n": 0, "meets": meets, "part": 0, "quote": "beta1**step"}]}

    assert read_checklist_audit(answers, RULES, SOURCES, TEXTS) == ()

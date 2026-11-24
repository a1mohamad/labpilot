import pytest

from labpilot.agent._safety_net import or_nothing
from labpilot.agent._schema import index, is_located, list_schema, number


def test_a_list_schema_names_its_key_once_and_requires_it():
    schema = list_schema("facts", {"n": {"type": "integer"}}, ["n"])

    assert schema["required"] == ["facts"]
    items = schema["properties"]["facts"]["items"]
    assert items["properties"] == {"n": {"type": "integer"}}
    assert items["required"] == ["n"]


@pytest.mark.parametrize("value", [True, False, 1.0, "1", None])
def test_only_a_real_integer_is_a_number(value):
    assert number(value) is None
    assert index(value, 5) is None


@pytest.mark.parametrize(
    ("value", "found"), [(-1, None), (0, 0), (2, 2), (3, None), (99, None)]
)
def test_an_index_is_one_of_the_places_of_the_list(value, found):
    assert index(value, 3) == found


def test_an_item_with_its_three_fields_is_located():
    assert is_located({"text": "t", "part": 0, "quote": "q"})


@pytest.mark.parametrize(
    "item",
    [
        "text",
        {"part": 0, "quote": "q"},
        {"text": 1, "part": 0, "quote": "q"},
        {"text": "t", "part": True, "quote": "q"},
        {"text": "t", "part": "0", "quote": "q"},
        {"text": "t", "part": 0},
    ],
)
def test_an_item_with_a_wrong_field_is_not_located(item):
    assert not is_located(item)


def test_a_finder_that_fails_gives_nothing_and_says_so(caplog):
    def fails():
        raise LookupError("no tier")

    assert or_nothing(fails, LookupError, "bugs") == []
    assert "no bugs, the answer goes on: no tier" in caplog.text


def test_a_finder_that_works_gives_its_list():
    assert or_nothing(lambda: ("a", "b"), LookupError, "bugs") == ["a", "b"]


def test_a_bug_of_ours_is_not_hidden_by_the_safety_net():
    def broken():
        raise TypeError("our bug")

    with pytest.raises(TypeError):
        or_nothing(broken, LookupError, "bugs")

from labpilot.prompts import groups_of, whole_files


def text(tokens):
    # estimate_tokens counts one token for every three characters.
    return "x" * (3 * tokens)


def flat(groups):
    return [index for group in groups for index in group]


def test_without_files_the_groups_are_equal_shares_as_before():
    parts = [text(100)] * 10

    assert groups_of(parts, 500) == [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9]]


def test_a_small_file_on_the_boundary_is_not_split():
    # 10 parts of 100 tokens, two groups of 500: the plain cut falls after part 4,
    # inside file c.py (parts 3 to 5).
    parts = [text(100)] * 10
    files = ["a.py"] * 3 + ["c.py"] * 3 + ["d.py"] * 4

    groups = groups_of(parts, 500, files=files)

    for name in set(files):
        holding = [g for g in groups if any(files[i] == name for i in g)]
        assert len(holding) == 1, name
    assert flat(groups) == list(range(10))


def test_the_cut_moves_to_the_nearer_edge_of_the_file():
    # c.py is parts 4 to 6; the plain cut is after part 4, so ending the group
    # before c.py moves one part and ending it after c.py moves two.
    parts = [text(100)] * 10
    files = ["a.py"] * 4 + ["c.py"] * 3 + ["d.py"] * 3

    assert groups_of(parts, 500, files=files) == [[0, 1, 2, 3], [4, 5, 6, 7, 8, 9]]


def test_a_file_bigger_than_a_group_is_cut_between_its_parts():
    parts = [text(100)] * 10
    files = ["big.py"] * 10

    assert groups_of(parts, 500, files=files) == [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9]]


def test_many_tiny_files_never_share_a_cut():
    parts = [text(30)] * 60
    # Files of 4 parts: the plain cuts (after parts 14, 29 and 44) fall inside files.
    files = [f"f{n // 4}.py" for n in range(60)]

    groups = groups_of(parts, 400, files=files)

    assert len(groups) > 2 and all(groups)
    assert flat(groups) == list(range(60))
    for left, right in zip(groups, groups[1:], strict=False):
        assert files[left[-1]] != files[right[0]]


def test_whole_files_skips_a_file_that_does_not_fit_and_tries_the_next():
    parts = [text(300), text(400), text(400), text(200)]
    files = ["a.py", "b.py", "b.py", "c.py"]

    assert whole_files(parts, files, 600) == [0, 3]


def test_whole_files_keeps_the_order_and_takes_everything_that_fits():
    parts = [text(100)] * 4
    files = ["a.py", "a.py", "b.py", "c.py"]

    assert whole_files(parts, files, 1_000) == [0, 1, 2, 3]


def test_a_first_file_bigger_than_the_limit_is_read_by_its_first_parts():
    parts = [text(400)] * 4
    files = ["big.py"] * 4

    assert whole_files(parts, files, 1_000) == [0, 1]


def test_a_big_file_is_skipped_when_a_later_file_fits():
    parts = [text(400)] * 4 + [text(100)]
    files = ["big.py"] * 4 + ["small.py"]

    assert whole_files(parts, files, 1_000) == [4]


def test_every_part_gets_its_number_in_front_in_order():
    from labpilot.prompts._groups import numbered_parts

    assert numbered_parts(["alpha", "beta"]) == ["[part 0]\nalpha", "[part 1]\nbeta"]
    assert numbered_parts([]) == []


def test_no_prompt_numbers_its_parts_by_hand():
    # The model names a part by this number and the code reads it back, so one
    # function writes it. A copy that drifts would make a step read the wrong part.
    from pathlib import Path

    import labpilot.prompts as package

    folder = Path(package.__file__).parent
    by_hand = [
        path.name
        for path in folder.glob("*.py")
        if path.name != "_groups.py" and "[part {number}]" in path.read_text("utf-8")
    ]

    assert by_hand == []

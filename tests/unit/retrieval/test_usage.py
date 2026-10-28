from labpilot.retrieval import unused_definitions


def part(header, text):
    return (header, text)


def test_a_function_defined_and_never_named_again_is_found():
    parts = [
        part(
            "[train.py · class Data · def pos_weight · lines 1-4]",
            "    def pos_weight(self):\n        return 1.7",
        ),
        part("[train.py · def main · lines 10-12]", "def main():\n    loss = Loss()"),
    ]

    found = unused_definitions(parts)

    assert found == {
        "pos_weight": "[train.py · class Data · def pos_weight · lines 1-4]",
        "main": "[train.py · def main · lines 10-12]",
    }


def test_a_call_anywhere_in_the_file_counts_as_a_use():
    parts = [
        part("[a.py · def helper · lines 1-2]", "def helper():\n    return 1"),
        part("[a.py · def main · lines 3-5]", "def main():\n    x = helper()"),
    ]

    assert "helper" not in unused_definitions(parts)


def test_a_reference_without_a_call_also_counts():
    parts = [
        part("[a.py · def hook · lines 1-2]", "def hook(x):\n    return x"),
        part("[a.py · lines 3-3]", "HOOKS = [hook]"),
    ]

    assert "hook" not in unused_definitions(parts)


def test_a_name_that_only_contains_the_word_is_not_a_use():
    parts = [
        part("[a.py · def scale · lines 1-2]", "def scale(x):\n    return x"),
        part("[a.py · lines 3-3]", "rescale = 2\nscale_factor = 3"),
    ]

    assert "scale" in unused_definitions(parts)


def test_the_def_line_repeated_in_an_overlapping_part_is_not_a_use():
    head = "[a.py · def lonely · part 1/2 · lines 1-9]"
    parts = [
        part(head, "def lonely():\n    pass"),
        part(
            "[a.py · def lonely · part 2/2 · lines 5-9]", "def lonely():\n    return 2"
        ),
    ]

    assert unused_definitions(parts) == {"lonely": head}


def test_dunder_methods_are_left_out_because_the_language_calls_them():
    parts = [part("[a.py · class C · def __len__ · lines 1-2]", "def __len__(self):")]

    assert unused_definitions(parts) == {}


def test_parts_with_no_def_label_give_nothing():
    parts = [part("[notes.md · 3 Method · lines 1-9]", "We train for 5 epochs.")]

    assert unused_definitions(parts) == {}


def test_where_each_constant_is_set_is_found():
    from labpilot.retrieval import constant_definitions

    parts = [
        (0, "class TrainConfig:\n    CLIP_NORM = 1.5\n    LR: float = 3e-4"),
        (1, "    clip(self.config.CLIP_NORM)\nif CLIP_NORM == 2:"),
        (2, "    CLIP_NORM = 1.5  # an overlapping copy"),
        (3, "    WARMUP == 0  # a comparison, not a setting"),
    ]

    assert constant_definitions(parts) == {"CLIP_NORM": 0, "LR": 0}


def test_the_constants_a_text_names_are_listed_once_in_order():
    from labpilot.retrieval import constants_named

    text = "clip(self.config.CLIP_NORM)\nx = cfg.LR * cfg.CLIP_NORM\nif ok:"

    assert constants_named(text) == ["CLIP_NORM", "LR"]


def test_a_method_inside_a_class_part_is_found_though_the_header_names_only_the_class():
    # 2026-10-24: QuoraDataset is ONE part, so pos_class_weight was never seen.
    parts = [
        (
            "[t.py · class Data · lines 1-6]",
            "class Data:\n    def pos_weight(self, device):\n        return 1.7\n",
        ),
        ("[t.py · def main · lines 8-10]", "def main():\n    return Data()\nmain()\n"),
    ]

    assert unused_definitions(parts) == {
        "pos_weight": "[t.py · class Data · lines 1-6]"
    }


def test_a_method_a_framework_calls_by_itself_is_never_reported():
    # PyTorch calls forward() through model(x); pytest calls test_ functions.
    parts = [
        (
            "[m.py · class Net · def forward · lines 1-2]",
            "    def forward(self, x):\n        return x\n",
        ),
        (
            "[m.py · def test_net · lines 4-5]",
            "def test_net():\n    assert Net()(1) == 1\n",
        ),
        ("[m.py · def on_epoch_end · lines 7-8]", "def on_epoch_end():\n    pass\n"),
    ]

    assert unused_definitions(parts) == {}

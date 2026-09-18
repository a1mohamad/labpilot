"""A module-level constant must be declared once.

`VECTOR_TOP_N` was declared TWICE in `api/services.py`, identically, about 270
lines apart. The second shadowed the first, so editing the first one would have
changed nothing at run time and nothing would have said so - the same silent
class as a hardcoded registry: the file looks like it holds the decision and
one of the two copies is decoration.

Found 2026-09-18 while shipping slice 8 v3's measured value.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "labpilot"


def constants(tree: ast.Module) -> list[str]:
    """Names assigned at MODULE level, in CONSTANT_CASE."""
    names: list[str] = []
    for node in tree.body:
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]

        for target in targets:
            if isinstance(target, ast.Name) and target.id.isupper():
                names.append(target.id)
    return names


def test_no_module_level_constant_is_declared_twice():
    duplicated: dict[str, list[str]] = {}

    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        repeated = [
            name for name, count in Counter(constants(tree)).items() if count > 1
        ]
        if repeated:
            duplicated[str(path.relative_to(ROOT))] = repeated

    assert not duplicated, (
        f"a second declaration silently shadows the first: {duplicated}"
    )


def test_the_three_top_n_numbers_keep_their_order():
    """`RERANK_TOP_N <= VECTOR_TOP_N <= SEARCH_LIMIT`, and it is arithmetic.

    You cannot send more than you kept, and you cannot keep more than you
    retrieved. CLAUDE.md has stated this since 2026-09-14 as the ONE rule among
    the three - every actual value is a knob slice 8 may move - and nothing
    enforced it. All three live in different packages, so no single module can.

    Break it and the failure is silent: a cut to 30 out of a window of 20
    returns 20 and simply stops being a cut. A `RERANK_TOP_N` above
    `VECTOR_TOP_N` is worse still - it would make the DEGRADED path narrower
    than the good one, which is backwards.

    Added 2026-09-18, when slice 8 v3 moved `VECTOR_TOP_N` 25 -> 30.
    """
    from labpilot.api.services import RERANK_WINDOW, VECTOR_TOP_N
    from labpilot.rerank.defaults import RERANK_TOP_N
    from labpilot.store.defaults import SEARCH_LIMIT

    assert RERANK_TOP_N <= VECTOR_TOP_N, (
        f"the degraded path would send {VECTOR_TOP_N} and the reranked one "
        f"{RERANK_TOP_N} - the fallback cannot be the wider of the two"
    )
    assert VECTOR_TOP_N <= SEARCH_LIMIT, (
        f"search returns {SEARCH_LIMIT} per side and the cut keeps "
        f"{VECTOR_TOP_N} - a cut larger than the window is not a cut"
    )
    assert RERANK_TOP_N <= RERANK_WINDOW, (
        f"the reranker reads {RERANK_WINDOW} and we keep {RERANK_TOP_N} of "
        "them - it cannot return more than it was shown"
    )
    assert RERANK_WINDOW <= SEARCH_LIMIT, (
        f"search returns {SEARCH_LIMIT} per side and the reranker is handed "
        f"{RERANK_WINDOW} - a window wider than the search is not a window"
    )

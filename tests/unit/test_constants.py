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

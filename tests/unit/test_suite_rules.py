"""Guards on the test suite itself, and both of them protect a real cost.

Same family as test_packaging and test_architecture: they cross every package,
they read files rather than call code, and nothing else notices when the rule
they hold is broken.

The rule these exist for is CLAUDE.md's cost split - `unit/` and `api/` run on
every push and must never touch a real service, while `smoke/` spends real API
quota and must never run unasked.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

TESTS = pathlib.Path(__file__).resolve().parents[1]
FREE_OF_CREDENTIALS = ("unit", "api")


def _module(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _marks(tree: ast.Module, function: ast.FunctionDef) -> str:
    """Every marker that applies to `function`, decorator and module level."""
    applied = [ast.unparse(d) for d in function.decorator_list]
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets
        ):
            applied.append(ast.unparse(node.value))
    return " ".join(applied)


def _tests_in(path: pathlib.Path):
    tree = _module(path)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            yield node, tree


@pytest.mark.parametrize(
    "path", sorted((TESTS / "smoke").rglob("test_*.py")), ids=lambda p: p.name
)
def test_every_smoke_test_carries_the_smoke_marker(path):
    """An unmarked smoke test runs on EVERY push and spends real API quota.

    conftest.py skips by marker alone, so the whole cost gate rests on each
    test remembering it. Nothing else would report the loss - the suite would
    simply be slower and the quota would be gone.
    """
    unmarked = [
        node.name
        for node, tree in _tests_in(path)
        if "mark.smoke" not in _marks(tree, node)
    ]

    assert not unmarked, (
        f"{path.name}: {unmarked} would run without --run-smoke and spend real "
        f"provider quota on every push. Add @pytest.mark.smoke."
    )


@pytest.mark.parametrize("folder", FREE_OF_CREDENTIALS)
def test_no_default_test_loads_real_credentials(folder):
    """`load_dotenv` in unit/ or api/ means that test wants real keys.

    Wanting real keys is the first step of reaching a real service, and both
    folders run on every push. Measured 2026-09-05: only integration/ and
    smoke/ load them, which is exactly the cost split CLAUDE.md describes - so
    this pins a property the suite already has rather than asking for a change.
    """
    offenders = [
        str(path.relative_to(TESTS))
        for path in (TESTS / folder).rglob("test_*.py")
        for node in ast.walk(_module(path))
        if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("load_dotenv")
    ]

    assert not offenders, (
        f"{sorted(set(offenders))} load .env, but tests/{folder}/ runs on every "
        f"push and must not reach a real service. Move the test to "
        f"integration/ (a live database) or smoke/ (real API quota)."
    )

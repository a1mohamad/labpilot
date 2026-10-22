"""The scripts are code nobody runs on every push, so they rot quietly.

D45 split `api/services.py` and renamed several functions, and slice 5 removed the
one-shot search. A script that still names a removed function fails only the day
somebody runs it - often in the middle of a measurement, hours in. Reading the
imports costs nothing and runs on every push.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = sorted((ROOT / "scripts").glob("*.py"))


def _missing_imports(path: pathlib.Path) -> list[str]:
    missing = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[0] == "labpilot"
        ):
            continue
        try:
            module = importlib.import_module(node.module)
        except ImportError:
            missing.append(f"module {node.module}")
            continue
        for alias in node.names:
            if hasattr(module, alias.name):
                continue
            try:
                importlib.import_module(f"{node.module}.{alias.name}")
            except ImportError:
                missing.append(f"{node.module}.{alias.name}")
    return missing


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_every_name_a_script_takes_from_labpilot_still_exists(path):
    missing = _missing_imports(path)

    assert not missing, (
        f"scripts/{path.name} imports {missing}, which no longer exist in "
        f"labpilot/. Update the script, or delete it if it is finished."
    )


def test_every_function_the_end_to_end_benchmark_times_still_exists():
    """The benchmark patches these by NAME, so an import check cannot see them.

    It timed `searching.rerank_and_cut` until slice 5 removed it; the script
    would have crashed on its first run after that.
    """
    path = ROOT / "scripts" / "bench_end_to_end.py"
    spec = importlib.util.spec_from_file_location("bench_end_to_end", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    gone = [
        f"{module.__name__}.{name}"
        for module, name in script.TIMED
        if not hasattr(module, name)
    ]

    assert not gone, f"the benchmark times functions that are gone: {gone}"

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "labpilot"

SHARED = frozenset({"tokens", "_text"})
ADAPTERS = frozenset({"llm", "embed", "rerank", "sources", "store"})
CORE = frozenset({"agent", "ingest", "prompts", "retrieval"})
ENTRY = frozenset({"api"})

MAY_IMPORT: dict[str, frozenset[str]] = {
    "shared": frozenset(),
    "adapters": SHARED,
    "core": SHARED | CORE,
    "entry": SHARED | ADAPTERS | CORE | ENTRY,
}

LAYER_OF = {
    **dict.fromkeys(SHARED, "shared"),
    **dict.fromkeys(ADAPTERS, "adapters"),
    **dict.fromkeys(CORE, "core"),
    **dict.fromkeys(ENTRY, "entry"),
}


def _units() -> set[str]:
    packages = {p.parent.name for p in PACKAGE_ROOT.glob("*/__init__.py")}
    modules = {p.stem for p in PACKAGE_ROOT.glob("*.py") if p.stem != "__init__"}
    return packages | modules


def _unit_of(path: Path) -> str:
    relative = path.relative_to(PACKAGE_ROOT).parts
    return relative[0] if len(relative) > 1 else path.stem


def _imports() -> dict[str, set[str]]:
    edges: dict[str, set[str]] = {unit: set() for unit in _units()}
    for path in PACKAGE_ROOT.rglob("*.py"):
        importer = _unit_of(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names = [node.module] if node.module else []
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                continue
            for name in names:
                parts = name.split(".")
                if parts[0] != "labpilot" or len(parts) < 2:
                    continue
                imported = parts[1]
                if imported != importer:
                    edges[importer].add(imported)
    return edges


GRAPH = _imports()


def test_every_package_is_assigned_to_a_layer():
    unassigned = _units() - set(LAYER_OF)
    assert not unassigned, (
        f"{sorted(unassigned)} belong to no layer. Decide what each one is - "
        f"shared, adapter, core or entry - and add it above. A package nobody "
        f"has classified is a package nobody has thought about."
    )


@pytest.mark.parametrize("importer", sorted(GRAPH))
def test_a_package_only_imports_the_layers_below_it(importer):
    allowed = MAY_IMPORT[LAYER_OF[importer]]
    crossed = GRAPH[importer] - allowed
    assert not crossed, (
        f"{importer} ({LAYER_OF[importer]}) imports {sorted(crossed)}, which its "
        f"layer may not reach. Allowed: {sorted(allowed) or 'nothing of ours'}"
    )


def test_the_import_graph_has_no_cycles():
    WALKING, DONE = 1, 2
    state: dict[str, int] = {}
    trail: list[str] = []

    def walk(unit: str) -> list[str] | None:
        state[unit] = WALKING
        trail.append(unit)
        for nxt in sorted(GRAPH.get(unit, set())):
            if state.get(nxt) == WALKING:
                return trail[trail.index(nxt) :] + [nxt]
            if nxt not in state:
                found = walk(nxt)
                if found:
                    return found
        state[unit] = DONE
        trail.pop()
        return None

    for unit in sorted(GRAPH):
        if unit not in state:
            cycle = walk(unit)
            if cycle:
                pytest.fail(f"import cycle: {' -> '.join(cycle)}")


# Libraries that reach the outside world. The layer rule above only governs OUR
# packages. Decision D7 says nodes get such things as functions handed in from
# outside, so every node can be tested with a fake and no network. A node that
# imports one of these directly would pass the layer rule and still break D7.
OUTSIDE_WORLD = frozenset(
    {
        "aiohttp",
        "httpx",
        "psycopg",
        "psycopg_pool",
        "requests",
        "socket",
        "subprocess",
        "urllib",
        "urllib3",
    }
)


def _third_party_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_the_agent_package_never_reaches_the_outside_world_itself():
    files = sorted((PACKAGE_ROOT / "agent").rglob("*.py"))
    assert files, "labpilot/agent/ holds no files, so this test checks nothing"

    reached = {
        path.name: sorted(_third_party_imports(path) & OUTSIDE_WORLD)
        for path in files
        if _third_party_imports(path) & OUTSIDE_WORLD
    }

    assert not reached, (
        f"{reached} reach the outside world directly. A node must get the "
        f"function it needs from api/ (decision D7), or it can no longer be "
        f"tested with a fake and no network."
    )

"""Guards for project configuration that code can silently drift away from.

Same family as test_every_chain_env_var_is_mapped_in_the_smoke_workflow: these
files are just text, reading them costs nothing, and nothing else notices when
they stop matching the code.
"""

from __future__ import annotations

import ast
import importlib.metadata
import pathlib
import re
import sys

SOURCE = pathlib.Path("labpilot")
REQUIREMENTS = pathlib.Path("requirements.txt")
ENV_EXAMPLE = pathlib.Path(".env.example")
CI_WORKFLOW = pathlib.Path(".github/workflows/ci.yaml")

READERS = {("os", "getenv"), ("os", "environ", "get")}
SAMPLES = pathlib.Path("data/samples")
SOURCES = SAMPLES / "SOURCES.md"
THIRD_PARTY_SUFFIXES = {".pdf", ".docx", ".doc", ".xlsx", ".pptx", ".zip"}

# Packages that cannot fit the 512MB instance the API and ingest share.
TOO_HEAVY_TO_DEPLOY = {
    "torch",
    "torchvision",
    "tensorflow",
    "transformers",
    "sentence-transformers",
    "langchain-community",
    # The local cross-encoder. Measured 2026-09-11: it is a fine measurement
    # instrument and a bad tier - it made retrieval worse on all four runs -
    # so it is a dev dependency twice over, on memory AND on quality.
    "onnxruntime",
    "onnxruntime-gpu",
    "scipy",
    "spacy",
}


def _modules() -> list[ast.Module]:
    return [
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for path in sorted(SOURCE.rglob("*.py"))
    ]


def imported_packages() -> set[str]:
    found: set[str] = set()
    for tree in _modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                found.add(node.module.split(".")[0])

    return {
        name
        for name in found
        if name not in sys.stdlib_module_names and name != SOURCE.name
    }


def imported_modules() -> set[str]:
    """The FULL dotted names, `langgraph.checkpoint.base`, not just `langgraph`."""
    found: set[str] = set()
    for tree in _modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                found.add(node.module)

    return {
        name
        for name in found
        if name.split(".")[0] not in sys.stdlib_module_names
        and name.split(".")[0] != SOURCE.name
    }


def _normalised(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def packages_providing(modules: set[str]) -> dict[str, set[str]]:
    """Which installed packages ship each module, read from their own file lists."""
    wanted: dict[pathlib.PurePosixPath, str] = {}
    for module in modules:
        base = pathlib.PurePosixPath(*module.split("."))
        wanted[base / "__init__.py"] = module
        wanted[base.with_suffix(".py")] = module

    providers: dict[str, set[str]] = {module: set() for module in modules}
    for dist in importlib.metadata.distributions():
        for file in dist.files or ():
            module = wanted.get(pathlib.PurePosixPath(file.as_posix()))
            if module:
                providers[module].add(_normalised(dist.metadata["Name"]))

    return providers


def _dotted(node: ast.AST) -> tuple[str, ...]:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)

    return tuple(reversed(parts))


def environment_variables_read() -> set[str]:
    """Only literal names. A key read through a variable — every provider's
    api_key_env — is data, and test_registry.py already guards those."""
    found: set[str] = set()
    for tree in _modules():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _dotted(node.func) not in READERS:
                continue
            if node.args and isinstance(node.args[0], ast.Constant):
                if isinstance(node.args[0].value, str):
                    found.add(node.args[0].value)

    return found


def test_every_package_labpilot_imports_is_pinned():
    """A transitive dependency is not a pinned one.

    pydantic and starlette were imported directly and arrived only through
    FastAPI, so a FastAPI upgrade could have changed either version underneath
    us with nothing failing. CI cannot catch this: it installs
    requirements-dev.txt, which pulls the whole tree in regardless.
    """
    pinned = {
        line.split("==")[0].split("[")[0].strip().lower().replace("-", "_")
        for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    aliases = {"dotenv": "python_dotenv"}

    missing = sorted(
        name
        for name in imported_packages()
        if aliases.get(name, name).replace("-", "_") not in pinned
    )

    assert not missing, f"imported by labpilot/ but not in requirements.txt: {missing}"


def test_every_module_labpilot_imports_comes_from_a_pinned_package():
    """The test above reads only the FIRST word of an import, and that is not
    enough when packages share a namespace.

    `langgraph.checkpoint.base` starts with `langgraph`, which IS pinned, but the
    module ships in `langgraph-checkpoint`, a different package that arrives only
    through another one. Delete its pin and the old test stays green, the suite
    stays green on this machine, and a fresh install fails at import.
    """
    pinned = {
        _normalised(line.split("==")[0].split("[")[0].strip())
        for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }

    unpinned = {
        module: sorted(found)
        for module, found in packages_providing(imported_modules()).items()
        if not found & pinned
    }

    assert not unpinned, (
        f"imported by labpilot/ but no package that ships it is pinned in "
        f"requirements.txt (module: the packages that ship it): {unpinned}"
    )


def test_every_requirement_is_pinned_to_an_exact_version():
    loose = [
        line.strip()
        for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#") and "==" not in line
    ]

    assert not loose, f"not pinned to an exact version: {loose}"


def test_every_environment_variable_the_code_reads_is_documented():
    """A knob nobody knows about is a knob nobody can turn.

    Matches a declaration line, not the name anywhere in the file. The first
    version searched the whole text, so a name still mentioned in a neighbour's
    comment counted as documented and the test could not fail.
    """
    declared = {
        line.split("=", 1)[0].strip()
        for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }

    missing = sorted(environment_variables_read() - declared)

    assert not missing, f"read by labpilot/ but not declared in .env.example: {missing}"


def test_no_runtime_requirement_would_blow_the_memory_budget():
    """CLAUDE.md calls installing torch "the single decision that would end the
    free tier instantly": ~800MB installed, 300-500MB resident, against a hard
    512MB Render ceiling that ingest and the API already share. The rule has
    been prose since 2026-08-11 and nothing enforced it.

    Runtime only. requirements-dev.txt may hold heavy packages -- the local
    ONNX reranker is deliberately a dev dependency that never ships.
    """
    installed = {
        line.split("==", 1)[0].strip().lower()
        for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }

    fatal = sorted(installed & TOO_HEAVY_TO_DEPLOY)

    assert not fatal, (
        f"{fatal} in requirements.txt would not fit the 512MB instance. "
        f"Use an ONNX or hosted equivalent, or make it a dev dependency."
    )


def test_every_committed_fixture_names_its_source_and_its_licence():
    """Anything in data/samples/ is in git history forever and cannot be
    audited afterwards. SOURCES.md is where provenance lives, and its own rule
    -- record the source and licence in the same commit -- had nothing
    enforcing it.

    WIDENED 2026-09-19, because it had been checking the wrong half. It matched
    on SUFFIX, so only binaries counted, and a retrieval fixture is a .json --
    which meant TEN of them (the whole v3 Python zoo) landed undocumented while
    this stayed green. A fixture is exactly as permanent as a PDF and names a
    third-party repository, a commit and a licence, so it needs the same rule.

    Fixtures are checked by their DIRECTORY name, because every one of them is
    called `queries.json` and matching on that would pass for all of them the
    moment any single fixture was documented.
    """
    documented = SOURCES.read_text(encoding="utf-8")

    binaries = {
        path.name
        for path in SAMPLES.rglob("*")
        if path.is_file() and path.suffix.lower() in THIRD_PARTY_SUFFIXES
    }
    fixtures = {path.parent.name for path in SAMPLES.glob("*/queries.json")}

    undocumented = sorted(
        name for name in binaries | fixtures if name not in documented
    )

    assert not undocumented, (
        f"committed to data/samples/ but not recorded in SOURCES.md: {undocumented}"
    )


def test_ci_really_runs_the_database_tests():
    """A `database` test skips itself when DATABASE_URL is missing.

    So CI without a database does not fail - it reports green while running
    none of them, which is how ten store tests sat unexercised for a week.
    A container, not the real project: CI runs on every push, and two
    concurrent jobs sharing one database would both drop the test schema.
    """
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "DATABASE_URL:" in workflow, (
        "CI sets no DATABASE_URL, so every `database` test will skip there "
        "and the suite will pass without running one of them."
    )
    assert "pgvector/pgvector" in workflow, (
        "CI must bring its own pgvector service. Pointing it at the real "
        "project makes concurrent jobs fight over the same test schema."
    )

"""Guards for project configuration that code can silently drift away from.

Same family as test_every_chain_env_var_is_mapped_in_the_smoke_workflow: these
files are just text, reading them costs nothing, and nothing else notices when
they stop matching the code.
"""

from __future__ import annotations

import ast
import pathlib
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
    """A binary in data/samples/ is in git history forever and cannot be
    audited afterwards. SOURCES.md is where provenance lives, and its own rule
    -- record the source and licence in the same commit -- had nothing
    enforcing it.
    """
    documented = SOURCES.read_text(encoding="utf-8")

    undocumented = sorted(
        path.name
        for path in SAMPLES.rglob("*")
        if path.is_file()
        and path.suffix.lower() in THIRD_PARTY_SUFFIXES
        and path.name not in documented
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

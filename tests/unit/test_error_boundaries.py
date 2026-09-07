"""Every error the entry layer can meet must be handled, or named as an exception.

Same family as test_packaging and test_architecture: it crosses every package,
it reads source rather than calling it, and nothing else notices when the rule
it holds is broken.

The rule exists because this project has been bitten by the same shape three
times, and CLAUDE.md predicts a fourth:

    slice 3  a malformed notebook raised LoaderError, which was not an
             ApiError, so it reached the 500 handler - reported as OUR bug
             rather than as the user's file.
    slice 3  the same error inside chunk_source silently truncated an entire
             repository walk, because a generator stops at the first raise.
    slice 4  the closing review predicted that wiring store/ would send
             UnknownArtifact, ModelMismatch, ConnectionFailed, NotConfigured
             and EmbeddingError straight to the 500 handler.

A new exception does not appear in an old `except` clause, and the failure it
causes is a 500 or a silent truncation - never a message naming the real cause.
So the boundary is checked by a test instead of by remembering.
"""

from __future__ import annotations

import ast
import importlib
import pathlib

API = pathlib.Path(__file__).resolve().parents[2] / "labpilot" / "api"

# Errors the entry layer genuinely may leave alone, each with the reason it is
# safe. This is the "pin the exceptions by name" pattern used for
# OUTPUT_TOO_SMALL: a deliberate gap is documented, and an accidental one
# breaks the build.
ALLOWED_TO_ESCAPE: dict[str, str] = {
    # LLMClient's own loop catches this per tier and moves to the next one, so
    # it cannot reach api/. AllFreeTiersExhausted is the one that does escape,
    # and services.py catches it.
    "LLMError": "the fallback chain swallows it inside LLMClient",
    # chunk_source() lives in services.py but NO route calls it - the endpoint
    # still accepts two uploaded files only. Slice 7 wires the repository door
    # and must map these first, or an oversized repo becomes a 500 that blames
    # us for the user's input.
    "SourceError": "chunk_source has no caller yet - slice 7 must map it",
    "CloneFailed": "chunk_source has no caller yet - slice 7 must map it",
    "SourceNotFound": "chunk_source has no caller yet - slice 7 must map it",
    "SourceTooLarge": "chunk_source has no caller yet - slice 7 must map it",
    "UnsafeArchive": "chunk_source has no caller yet - slice 7 must map it",
    "UnsupportedURL": "chunk_source has no caller yet - slice 7 must map it",
}


def _api_source() -> list[ast.Module]:
    return [
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for path in sorted(API.rglob("*.py"))
    ]


def _packages_the_api_imports(trees) -> set[str]:
    found = set()
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                parts = node.module.split(".")
                if parts[0] == "labpilot" and len(parts) > 1 and parts[1] != "api":
                    found.add(parts[1])
    return found


def _names_the_api_catches(trees) -> set[str]:
    caught = set()
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is not None:
                raised = (
                    node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
                )
                caught.update(ast.unparse(name).split(".")[-1] for name in raised)
    return caught


def _errors_exported_by(package: str) -> set[str]:
    module = importlib.import_module(f"labpilot.{package}")
    return {
        name
        for name in getattr(module, "__all__", ())
        if isinstance(getattr(module, name, None), type)
        and issubclass(getattr(module, name), Exception)
    }


def test_every_error_the_api_can_meet_is_caught_or_named():
    trees = _api_source()
    caught = _names_the_api_catches(trees)

    unhandled: dict[str, set[str]] = {}
    for package in sorted(_packages_the_api_imports(trees)):
        missing = _errors_exported_by(package) - caught - set(ALLOWED_TO_ESCAPE)
        if missing:
            unhandled[package] = missing

    assert not unhandled, (
        f"the API imports {sorted(unhandled)} and would let "
        f"{sorted(n for names in unhandled.values() for n in names)} reach the "
        f"500 handler, which reports the user's input as OUR bug. Catch each "
        f"one in api/services.py and map it to an ApiError, or add it to "
        f"ALLOWED_TO_ESCAPE with the reason it is safe."
    )


def test_the_escape_list_does_not_outlive_its_reason():
    """An allowlist that names errors nobody imports any more is a lie.

    It would also hide a real gap: a name left behind here silences the check
    for that name for ever, including on a package that later starts using it.
    """
    trees = _api_source()
    reachable = set()
    for package in _packages_the_api_imports(trees):
        reachable |= _errors_exported_by(package)

    stale = sorted(set(ALLOWED_TO_ESCAPE) - reachable)

    assert not stale, (
        f"{stale} are listed as deliberately unhandled, but the API no longer "
        f"imports the package that raises them. Delete these entries."
    )

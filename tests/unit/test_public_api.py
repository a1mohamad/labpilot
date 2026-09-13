"""Every name a package door promises must really be there.

Same family as test_packaging and test_architecture: it crosses every package,
and nothing else notices when the rule it holds is broken.

RUFF DOES NOT CATCH THIS, and the reason is the whole point of the file. F822 -
undefined name in `__all__` - is EXEMPTED inside `__init__.py`, because a
re-export door legitimately names things it did not define. Measured 2026-09-13
against this repo's own ruff, same rule, two files of identical content:

    a plain module   ->  F822 Undefined name `ghost` in `__all__`
    an __init__.py   ->  All checks passed

CLAUDE.md's slice 4 closing review wrote a test like this one and DELETED it,
reasoning "ruff already catches it". The premise was false, and the bug it
would have caught went live in the newest package: rerank/__init__.py listed
RERANK_MAX_TOKENS in `__all__` and never imported it, so

    from labpilot.rerank import *   ->  AttributeError

while the suite and both ruff commands stayed green.

Only PACKAGES are checked, never the top-level modules. `tokens.py` and
`_text.py` are plain modules, where F822 does fire - and a second guard on a
failure the linter already holds is a number, not protection. That is the rule
the slice 4 review meant to apply; it just had the wrong answer about which
files the linter covers.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "labpilot"

PACKAGES = sorted(path.parent.name for path in PACKAGE_ROOT.glob("*/__init__.py"))


def test_the_packages_under_test_are_really_found():
    """The parametrized test below is vacuous if this list is empty.

    A glob that silently matches nothing would report every package green
    without importing one - the same shape as a `database` test skipping
    itself and leaving the suite looking covered.
    """
    assert len(PACKAGES) >= 8, PACKAGES


@pytest.mark.parametrize("package", PACKAGES)
def test_every_name_a_package_promises_is_importable(package):
    module = importlib.import_module(f"labpilot.{package}")
    promised = getattr(module, "__all__", ())
    missing = [name for name in promised if not hasattr(module, name)]

    assert not missing, (
        f"labpilot.{package} promises {missing} in __all__ and does not "
        f"import them, so `from labpilot.{package} import *` raises "
        f"AttributeError. Ruff cannot see this inside an __init__.py."
    )

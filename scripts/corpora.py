"""The corpus zoo, described by data rather than by code.

Slice 8's first run had three corpora and one loader function each. Twelve
corpora would have meant twelve functions in a measurement script, so adding a
corpus would have been a code change and nobody would have added the twelfth.

Here a corpus is a `corpus` block inside its own `queries.json`:

    "corpus": {
        "key": "cobra",                what the scripts call it
        "env": "LABPILOT_COBRA_SRC",   the checkout, NEVER committed
        "include": ["**/*.go"],        globs, relative to that root
        "exclude": ["**/*_test.go"],   globs, applied to the relative path
        "source": "relpath"            how `file` in a query is spelled
    }

`key` exists because the embedding cache is named after it. The directory is
`golang_geo` and the key is `geo`, and renaming the key would silently orphan
100 MB of paid-for vectors - so the short name is the identity and the folder
is only where the file lives.

`source` is load-bearing and is the one field that cannot be guessed. A query's
`file` must match `Chunk.source` exactly or its ground truth resolves to
nothing, and the two existing fixtures disagree: `requests` spells it
`adapters.py` (the bare name, because it is one flat directory) and `geo`
spells it `s2/cellid.go`. Both are legitimate; only the fixture knows which.

Third-party source is never committed. Every corpus names an environment
variable pointing at a checkout, exactly as `geo` and `requests` already did.
"""

from __future__ import annotations

import fnmatch
import json
import os
from dataclasses import dataclass
from pathlib import Path

from labpilot.ingest import chunk_file

SAMPLES = Path("data/samples")


@dataclass(frozen=True)
class Query:
    id: str
    text: str
    file: str
    expects: tuple[int, ...]
    asks: str
    wording: str


def _spec(name: str) -> tuple[dict, Path]:
    """The corpus block and the directory holding it, found by KEY."""
    for path in sorted(SAMPLES.glob("*/queries.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            continue
        block = raw.get("corpus", {})
        if block.get("key", path.parent.name) == name:
            return block, path.parent
    raise SystemExit(f"no fixture declares the corpus {name!r}")


def _root(spec: dict, name: str) -> Path:
    """The checkout this corpus lives in, or a clear refusal naming the fix."""
    var = spec["env"]
    raw = os.environ.get(var, "").strip()
    if not raw or not Path(raw).is_dir():
        raise SystemExit(
            f"{var} is not set to a directory, so the {name!r} corpus cannot "
            f"be loaded. It is third-party or personal material and is NOT "
            f"committed: see its queries.json for the source, "
            f"and scripts/fetch_corpora.py to fetch it."
        )
    return Path(raw)


def _paths(root: Path, spec: dict) -> list[Path]:
    """Every file the corpus includes, sorted, with excludes applied.

    SORTED IS CORRECTNESS, not tidiness. Chunk ids are positional, so if the
    walk order shifts between machines the ground-truth line numbers still
    resolve but every cached vector lines up with the wrong chunk.
    """
    found: set[Path] = set()
    for pattern in spec["include"]:
        found.update(p for p in root.glob(pattern) if p.is_file())

    excluded = spec.get("exclude", ())
    kept = []
    for path in sorted(found):
        rel = str(path.relative_to(root)).replace("\\", "/")
        if any(fnmatch.fnmatch(rel, pattern) for pattern in excluded):
            continue
        kept.append(path)
    return kept


def chunks_for(name: str) -> list:
    """Chunk a corpus, without needing its queries.

    Separate from `load` because chunk vectors do not depend on the query set,
    so the slow embedders can be paid for before a fixture exists.
    """
    spec, _ = _spec(name)
    root = _root(spec, name)
    by_name = spec.get("source", "relpath") == "name"

    chunks = []
    for path in _paths(root, spec):
        rel = str(path.relative_to(root)).replace("\\", "/")
        chunks.extend(
            chunk_file(
                path,
                side="B",
                artifact_id=name,
                source=path.name if by_name else rel,
            )
        )
    return chunks


def queries_for(name: str) -> list[Query]:
    _, folder = _spec(name)
    raw = json.loads((folder / "queries.json").read_text(encoding="utf-8"))
    return [
        Query(
            q["id"],
            q["query"],
            q["file"],
            tuple(q["expects"]),
            q["asks"],
            q["wording"],
        )
        for q in raw["queries"]
    ]


def load(name: str) -> tuple[list, list[Query]]:
    return chunks_for(name), queries_for(name)


def _declared() -> dict[str, dict]:
    """Every fixture that describes its own corpus, discovered on disk.

    A corpus with no `env` key is legacy and keeps its hand-written loader -
    today that is only `quora`, whose queries.json is a bare list written
    before the schema existed.
    """
    specs: dict[str, dict] = {}
    for path in sorted(SAMPLES.glob("*/queries.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "env" in raw.get("corpus", {}):
            block = raw["corpus"]
            specs[block.get("key", path.parent.name)] = block
    return specs


SPECS = _declared()

"""What retrieval looks like on the corpus a REAL INGEST would build.

    PYTHONPATH=. python scripts/score_real_ingest.py smsspam disaster titanic
    PYTHONPATH=. python scripts/score_real_ingest.py --count-only --all

EVERY CORPUS IN THE ZOO IS ONE LANGUAGE - `**/*.py`, `**/*.go`. That was the
right choice for comparing embedders and windows, because it holds the material
constant. It is NOT what a user gets: `POST /artifacts` walks a repository with
`labpilot.sources.walk`, which reads 58 suffixes and skips by directory, size,
secret suffix and machine-written content.

So this script builds the corpus THE PRODUCT'S OWN WAY - the real walk, the real
loaders, the real refusals - and scores the SAME queries against it.

    narrow   the fixture's include globs, one language
    real     sources.walk(), everything the product would actually store

Ground truth survives because it is stored as FILE + LINE. The extra files do
not move the line that answers a question; they compete with it, and that
competition is the whole measurement.

WHY NOT A WIDENED `include` GLOB. That was tried first and it is wrong twice
over. Globs do not know about SKIP_DIRECTORIES, so `disaster` came out at
400,497 chunks - almost all of it `node_modules` the product would never read.
And `corpora.chunks_for` lets `LooksGenerated` escape, where the product catches
it and counts a skip, so one minified file aborted the whole corpus instead of
being dropped. Measuring "what a real ingest sees" means using the real walk.

Embedding quota only. No generation.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from dotenv import load_dotenv

from labpilot.api.services import chunk_source
from labpilot.sources import Source, SourceError
from scripts import corpora
from scripts.score_hybrid import EMBEDDERS, embedded, targets

RESULTS = Path(".logs/results")
DEFAULT_EMBEDDER = "codestral"


def real_chunks(name: str) -> tuple[list, dict[str, int]]:
    """The corpus the product builds, by CALLING the product.

    This used to re-implement `chunk_source` - walk, chunk, catch - and that
    was wrong the moment ingest grew a gate the copy did not have. When
    duplicate dropping shipped on 2026-09-18 the copy silently went on
    measuring the OLD pipeline, which is the one failure this whole script
    exists to catch, one level up.

    So it calls `api.services.chunk_source` and reads the skips off the Source.
    """
    spec, _ = corpora._spec(name)
    root = corpora._root(spec, name)

    source = Source(root=root, name=name)
    try:
        chunks = list(chunk_source(source, side="B"))
    except SourceError as exc:
        # NOT a bug in this script. The product REFUSES this repository, and
        # that refusal is the measurement: a corpus we score happily is one the
        # user could not have ingested. Reported, never swallowed.
        return [], {f"REFUSED: {type(exc).__name__}": str(exc)}
    return chunks, dict(source.skipped)


def score(chunks: list, queries: list, vectors, query_vectors) -> dict:
    places = []
    for index, query in enumerate(queries):
        want = targets(chunks, query)
        if not want:
            continue
        q = query_vectors[index]
        order = sorted(
            range(len(chunks)),
            key=lambda i: -sum(a * b for a, b in zip(vectors[i], q, strict=True)),
        )
        place = next(
            (rank for rank, i in enumerate(order, 1) if i in want), len(chunks) + 1
        )
        places.append(place)

    return {
        "queries": len(places),
        "MRR": statistics.mean(1 / p for p in places) if places else 0.0,
        "r@10": statistics.mean(p <= 10 for p in places) if places else 0.0,
        "r@50": statistics.mean(p <= 50 for p in places) if places else 0.0,
    }


def run(names: list[str], *, count_only: bool, model: str) -> None:
    rows = []
    for name in names:
        narrow, queries = corpora.load(name)
        wide, skipped = real_chunks(name)

        head = (
            f"\n=== {name}: {len(narrow)} -> {len(wide)} chunks "
            f"({(len(wide) / len(narrow) - 1) * 100:+.0f}%), "
            f"{len(queries)} queries"
        )
        refusal = next((v for k, v in skipped.items() if k.startswith("REFUSED")), None)
        if refusal:
            # NOT a gap in the table. The product REFUSES this repository, and
            # scoring it as 0.000 would pool a refusal in with a measurement.
            print(f"  THE PRODUCT REFUSES THIS REPOSITORY: {refusal}")
            print(f"  our fixture scores {len(narrow)} chunks of it quite happily")
            rows.append({"corpus": name, "narrow": len(narrow), "refused": refusal})
            continue

        print(head)
        if skipped:
            print(f"  the product would SKIP: {skipped}")
        if count_only:
            rows.append({"corpus": name, "narrow": len(narrow), "real": len(wide)})
            continue

        embedder = EMBEDDERS[model]
        # The tag IS the cache key, so the real-ingest corpus needs its own or
        # it would overwrite ~100MB of vectors belonging to the narrow one.
        # EXACTLY score_hybrid's tag, so the narrow half costs nothing: it is
        # already embedded. Slashes in a model name would make this a path.
        tag = f"{name}_{embedder.model.replace('/', '_')}"
        qv = embedded(
            embedder, [q.text for q in queries], task="query", tag=f"{tag}_queries"
        )
        a = score(
            narrow,
            queries,
            embedded(
                embedder,
                [c.embed_text for c in narrow],
                task="document",
                tag=f"{tag}_chunks",
            ),
            qv,
        )
        b = score(
            wide,
            queries,
            embedded(
                embedder,
                [c.embed_text for c in wide],
                task="document",
                tag=f"{tag}_realingest",
            ),
            qv,
        )

        print(f"  {'':10}{'chunks':>8}{'MRR':>8}{'r@10':>8}{'r@50':>8}")
        print(
            f"  {'narrow':10}{len(narrow):8}{a['MRR']:8.3f}"
            f"{a['r@10']:8.3f}{a['r@50']:8.3f}"
        )
        print(
            f"  {'REAL':10}{len(wide):8}{b['MRR']:8.3f}{b['r@10']:8.3f}{b['r@50']:8.3f}"
        )
        rows.append(
            {
                "corpus": name,
                "narrow": len(narrow),
                "real": len(wide),
                "queries": a["queries"],
                "narrow_MRR": a["MRR"],
                "real_MRR": b["MRR"],
                "narrow_r@10": a["r@10"],
                "real_r@10": b["r@10"],
                "narrow_r@50": a["r@50"],
                "real_r@50": b["r@50"],
                "skipped": skipped,
            }
        )

    # A REFUSED repository has no score, and pooling it as 0.000 mixes a
    # product refusal into a measurement - which is what the first version of
    # this script did, dragging the pooled delta from -0.14 to -0.22.
    scored = [r for r in rows if "real_MRR" in r]
    if not count_only and scored:
        refused = len(rows) - len(scored)
        print("")
        print(
            f"pooled, every SCORED corpus weighted once "
            f"({len(scored)} scored, {refused} refused)"
        )
        for label in ("MRR", "r@10", "r@50"):
            n = statistics.mean(r[f"narrow_{label}"] for r in scored)
            w = statistics.mean(r[f"real_{label}"] for r in scored)
            print(f"  {label:6} fixture {n:.4f}   REAL {w:.4f}   {w - n:+.4f}")

    RESULTS.mkdir(parents=True, exist_ok=True)
    name = "real_ingest_counts" if count_only else "real_ingest"
    (RESULTS / f"{name}.json").write_text(json.dumps(rows, indent=1))


def main(argv: list[str]) -> int:
    load_dotenv()
    count_only = "--count-only" in argv
    model = next(
        (a.split("=")[1] for a in argv if a.startswith("--model=")), DEFAULT_EMBEDDER
    )
    names = (
        sorted(corpora.SPECS)
        if "--all" in argv
        else [a for a in argv[1:] if not a.startswith("--")]
    )
    if not names:
        print(f"usage: {argv[0]} <corpus>... | --all [--count-only] [--model=...]")
        return 2
    run(names, count_only=count_only, model=model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

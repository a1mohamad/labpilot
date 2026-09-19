"""What the corpus zoo IS, and the PYTHON SHARE of any subset of it.

    PYTHONPATH=. python scripts/zoo.py
    PYTHONPATH=. python scripts/zoo.py quora requests geo docx

Slice 8 v3 exists because three v2 decisions turned out to have ZERO Python
behind them, and nobody noticed because the composition of a subset was never
printed beside its result. The run's fifth standing rule is that every
conclusion states its Python share, so this computes it rather than leaving it
to be counted by hand - which is exactly how the denominator errors in G18
were made.

`language` is read from each fixture's own corpus block, so a corpus cannot be
counted as Python by being listed here. "Python + Markdown" counts as Python:
a notebook is a Python artifact, and both of the zoo's notebook corpora spell
their language that way.
"""

from __future__ import annotations

import sys

# The product is a PYTHON and machine-learning tool. A notebook is Python.
DIFF = False
PYTHON_LANGUAGES = {"Python", "Python + Markdown"}


def facets() -> dict[str, dict]:
    """Every corpus in the zoo, including the ones with hand-written loaders."""
    from scripts.aggregate import facets as _facets

    return _facets()


def is_python(name: str, info: dict[str, dict] | None = None) -> bool:
    info = info if info is not None else facets()
    return info.get(name, {}).get("language", "?") in PYTHON_LANGUAGES


def share(names: list[str], info: dict[str, dict] | None = None) -> tuple[int, int]:
    """(python, total) over the named corpora."""
    info = info if info is not None else facets()
    return sum(1 for n in names if is_python(n, info)), len(names)


def overlaps() -> dict[str, float]:
    """Each fixture's query-answer word overlap, its measured DIFFICULTY.

    Reported beside every decision because the zoo is NOT uniform: it spans
    0.244 (jq) to 0.672 (docs), a 2.8x range inherited from v2. That does not
    corrupt a method comparison, which is a delta within one corpus, but it
    does mean an ABSOLUTE score only holds at the difficulty it was measured
    at - so a decision has to say which.
    """
    from scripts.query_difficulty import measure

    out: dict[str, float] = {}
    for name in facets():
        try:
            got = measure(name)
        except Exception:  # noqa: BLE001 - a corpus whose checkout is absent
            continue
        if got:
            out[name] = got[0]
    return out


def describe(names: list[str], with_difficulty: bool = False) -> str:
    """The one sentence rule 5 asks for beside every conclusion."""
    info = facets()
    known = [n for n in names if n in info]
    python, total = share(known, info)
    if not total:
        return "no known corpora"
    sizes = sorted(
        (info[n].get("chunks", 0) for n in known if info[n].get("chunks")),
    )
    span = f", sizes {sizes[0]} to {sizes[-1]}" if sizes else ""
    hard = ""
    if with_difficulty:
        ov = overlaps()
        got = sorted(ov[n] for n in known if n in ov)
        if got:
            hard = f", overlap {got[0]:.2f}-{got[-1]:.2f}"
    return f"{total} corpora, {python} Python ({python / total:.0%}){span}{hard}"


def main(argv: list[str]) -> int:
    from scripts import corpora

    # --measure CHUNKS every corpus instead of trusting the recorded number.
    # Not paranoia: two v2 fixtures were found carrying the chunk counts they
    # had BEFORE the fnmatch fix in G1 - cobra recorded 408 against a real
    # 193, websocket 167 against 78 - so a size column built from metadata
    # would have printed a denominator that was twice the truth. Metadata goes
    # stale silently; a measurement cannot.
    global DIFF
    DIFF = "--difficulty" in argv
    measure = "--measure" in argv
    argv = [a for a in argv if not a.startswith("--")]

    info = facets()
    for name in info:
        spec = corpora.SPECS.get(name, {})
        info[name]["chunks"] = spec.get("chunks_at_this_commit", 0)

    names = argv[1:] or sorted(info)
    unknown = [n for n in names if n not in info]
    for name in unknown:
        print(f"  ! unknown corpus {name!r}")
    names = [n for n in names if n in info]

    if measure:
        from scripts.score_hybrid import CHUNK_LOADERS

        for name in names:
            loader = CHUNK_LOADERS.get(name)
            if loader is None:
                continue
            real = len(loader())
            if real != info[name]["chunks"]:
                print(f"  ! {name}: recorded {info[name]['chunks']}, real {real}")
            info[name]["chunks"] = real

    print(f"{'corpus':12} {'language':20} {'format':9} {'chunks':>7}  python")
    for name in sorted(names, key=lambda n: info[n]["chunks"]):
        row = info[name]
        mark = "YES" if is_python(name, info) else "-"
        print(
            f"{name:12} {row['language']:20} {row['format']:9} "
            f"{row['chunks']:7}  {mark}"
        )

    python, total = share(names, info)
    print()
    print(f"  {describe(names, with_difficulty=DIFF)}")
    if total and python / total < 0.5:
        print(
            "  ! UNDER HALF PYTHON - the zoo is half Python and the product is "
            "a Python tool, so this subset does not represent it (rule 2.6)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

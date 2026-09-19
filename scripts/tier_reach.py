"""Which rerank tiers can actually serve which corpora, and at what window.

    PYTHONPATH=. python scripts/tier_reach.py
    PYTHONPATH=. python scripts/tier_reach.py --window=30

COSTS NOTHING. It reads the corpora and the tiers' own declared limits, so it
is arithmetic over data already on disk.

THE QUESTION. Slice 8 found that a tier's usable window is a property of the
CORPUS, not only of the provider: gemma serves 50 Python chunks and refuses 30
Go ones, because the same tier is being handed twice as much text. That was
one observation on one pair of corpora. This is all thirteen against every
tier, so "which tiers can we actually reach" stops being a guess.

THE CAUSAL CHAIN, which is the finding rather than the table:

    a language with no AST splitter
      -> split_recursive packs to the cap
      -> chunks are about twice as large
      -> one rerank call is about twice as many tokens
      -> the cheap, high-quota tiers stop being reachable

So the splitter - a decision made in slice 3, about parsing - decides which
rerank providers exist for that corpus. Those two things are five slices apart
and nothing connected them.

THE ESTIMATE IS OURS AND IT IS ROUGH. `estimate_tokens` is chars/3, measured
to over-count real content by about 3-5%, and a provider tokenizes its own
way. A corpus within a few percent of a limit should be treated as unknown,
not as refused.
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

from labpilot.tokens import estimate_tokens
from scripts.score_hybrid import CORPORA

# A rerank call carries the query once per document - Voyage publishes the
# formula - so the cost is `mean_document_tokens * N + query_tokens * N`.
QUERY_TOKENS = 20

# Ceilings as the providers enforce them, with the budget each one buys.
# Gemma's is PER MINUTE, so a single call larger than the ceiling can never
# pass however long you wait - the Groq shape, one layer over.
TIERS: tuple[tuple[str, int, str], ...] = (
    ("gemini-3.5-flash-lite", 1_000_000, "500/day x 2 keys"),
    ("gemini-3.1-flash-lite", 1_000_000, "500/day x 2 keys"),
    ("gemma-4-26b-a4b-it", 16_000, "14,400/day x 2 keys"),
    ("gemma-4-31b-it", 16_000, "14,400/day x 2 keys"),
    ("voyage rerank-3-lite", 10_000, "3 RPM, card-free"),
    ("cohere rerank-v4.0-fast", 1_000_000, "1,000 a MONTH"),
)


def order() -> tuple[str, ...]:
    """Every corpus in the zoo, smallest first.

    This was a hardcoded tuple of the thirteen v2 corpora, and it is the one
    place the project's own "a corpus is DATA, not code" rule was broken: the
    seven Python corpora added in v3 were silently absent from this table
    while every other script picked them up automatically. A hardcoded list
    does not fail when it goes stale, it just quietly measures less - so the
    order is derived from the zoo and sorted by size, which is what the old
    tuple spelled out by hand anyway.
    """
    from scripts import corpora

    sizes = {}
    for name in CORPORA:
        spec = corpora.SPECS.get(name, {})
        sizes[name] = spec.get("chunks_at_this_commit", 0)
    return tuple(sorted(sizes, key=lambda n: (sizes[n], n)))


def main(argv: list[str]) -> int:
    load_dotenv(".env")
    window = int(
        next((a.split("=")[1] for a in argv if a.startswith("--window=")), "50")
    )

    print(f"cost of ONE {window}-document rerank call, by corpus")
    print(
        f"  {'corpus':11}{'chunks':>7}{'mean tok':>9}{'call tok':>9}"
        f"{'tiers':>7}   widest window each tier could take"
    )

    rows = []
    for name in order():
        chunks, _ = CORPORA[name]()
        mean = sum(estimate_tokens(c.embed_text) for c in chunks) / len(chunks)
        per_document = mean + QUERY_TOKENS
        call = int(per_document * window)
        serves = [tier for tier, limit, _ in TIERS if call <= limit]
        # The window at which the TIGHTEST real ceiling starts accepting this
        # corpus - the number section 14.3's per-tier window needs.
        widest = int(16_000 / per_document)
        rows.append((name, len(chunks), mean, call, serves))
        print(
            f"  {name:11}{len(chunks):7}{mean:9.0f}{call:9}"
            f"{len(serves):4} of {len(TIERS)}   gemma: {widest:3} documents"
        )

    print()
    for tier, limit, budget in TIERS:
        served = [name for name, _, _, call, _ in rows if call <= limit]
        print(
            f"  {tier:26} limit {limit:>9}  serves {len(served):2} of "
            f"{len(rows)}   ({budget})"
        )

    starved = [name for name, _, _, _, serves in rows if len(serves) <= 3]
    print()
    if starved:
        print(
            f"  {len(starved)} of {len(rows)} corpora are down to the three "
            f"large-context tiers at window {window}:"
        )
        print(f"    {', '.join(starved)}")
        print(
            "  and of those three, one is 1,000 calls a MONTH - so the working "
            "budget is the two Flash-Lite keys, 1,000 calls a day."
        )
    else:
        cheap = sum(
            1
            for tier, limit, _ in TIERS
            if tier.startswith("gemma")
            and all(call <= limit for _, _, _, call, _ in rows)
        )
        print(
            f"  every corpus reaches more than three tiers at window {window}"
            + (
                f", including {cheap} Gemma tier(s) - 14,400 calls a day each,"
                " against Flash-Lite's 500"
                if cheap
                else ""
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

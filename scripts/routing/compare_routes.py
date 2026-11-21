"""Show how the routes would change with the PROPOSED tables.

    python -m scripts.routing.compare_routes          the first 3 models of each task
    python -m scripts.routing.compare_routes --top 5

Calls no model. It computes every route twice: with the tables in labpilot/llm/
(today) and with the tables in artifacts/routing-bench/proposed/ (what
write_ratings.py and analyze_bench.py wrote). A task whose first models change is
printed with both lists. Review those before you run the scripts with --apply.

Why the first 3: a call almost always ends on one of them, so a change lower in
a route seldom changes what the person waits for.
"""

from __future__ import annotations

import argparse
import runpy

from scripts.routing._common import PROPOSED


def _models(names, top):
    seen = []
    for name in names:
        model = name.split(" (key")[0]
        if model not in seen:
            seen.append(model)
        if len(seen) == top:
            break
    return seen


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--top", type=int, default=3)
    args = ap.parse_args()

    from labpilot.llm import routes

    today = {task: routes.route(task) for task in routes.TASKS}
    changed = False
    if (PROPOSED / "ratings.py").exists():
        routes.RATINGS = runpy.run_path(str(PROPOSED / "ratings.py"))["RATINGS"]
        changed = True
    if (PROPOSED / "accuracy.py").exists():
        routes.ACCURACY = runpy.run_path(str(PROPOSED / "accuracy.py"))["ACCURACY"]
        changed = True
    if not changed:
        print(
            f"nothing proposed in {PROPOSED}: "
            "run write_ratings.py or analyze_bench.py write"
        )
        return

    moved = 0
    for task in routes.TASKS:
        new = routes.route(task)
        before, after = _models(today[task], args.top), _models(new, args.top)
        if before != after:
            moved += 1
            print(f"\n{task}  ({len(today[task])} -> {len(new)} tiers)")
            print("  today:    " + " | ".join(before))
            print("  proposed: " + " | ".join(after))
    total = len(routes.TASKS)
    print(f"\n{moved} of {total} tasks change in their first {args.top} models")


if __name__ == "__main__":
    main()

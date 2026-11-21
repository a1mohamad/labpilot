"""Copy the labelled cases of the bench into artifacts/routing-bench/data/.

    python -m scripts.routing.collect_data

The bench reuses cases and answer keys that earlier slices wrote, all written
BEFORE any model was scored on them:

    slice9-study    the three pairs quora, adam and otp, their bug and concept
                    keys, the summaries, the claims, the bug pool and the
                    difference items (section 29)
    slice7-review   the 32 hand-made claims with their verdicts (section 25)
    slice10-study   the 45 + 24 labelled planner questions (section 31.11)
    slice8-m28      the gate pairs with the verdicts allowed (section 28.9)

They live in git-ignored study folders. This script gathers them in ONE folder,
so the bench (and a scheduled job later) needs nothing else. Run it once, and
again only if a study folder changes. It calls no model.
"""

from __future__ import annotations

import shutil

from scripts.routing._common import DATA, REPO

ART = REPO / "artifacts"
FILES = {
    "slice9-study/keys.py": "keys9.py",
    "slice9-study/fb_gold.py": "fb_gold.py",
    "slice9-study/results/summaries.json": "summaries9.json",
    "slice9-study/results/fb_pool.json": "fb_pool.json",
    "slice9-study/results/fm_items.jsonl": "fm_items.jsonl",
    "slice9-study/results/claims_quora.json": "claims_quora.json",
    "slice9-study/results/claims_adam.json": "claims_adam.json",
    "slice9-study/results/claims_otp.json": "claims_otp.json",
    "slice7-review/harness/gold.py": "gold7.py",
    "slice10-study/planner_questions.py": "planner_questions.py",
    "slice10-study/planner_heldout.py": "planner_heldout.py",
    "slice8-m28/m28_pairs.py": "m28_pairs.py",
    "slice8-m28/m28_summaries.json": "m28_summaries.json",
}
FOLDERS = {
    "slice9-study/cases/quora": "cases/quora",
    "slice9-study/cases/adam": "cases/adam",
    "slice9-study/cases/otp": "cases/otp",
}


def main() -> None:
    missing = []
    for src, dst in FILES.items():
        if (ART / src).exists():
            shutil.copy2(ART / src, DATA / dst)
        else:
            missing.append(src)
    for src, dst in FOLDERS.items():
        if (ART / src).exists():
            shutil.copytree(ART / src, DATA / dst, dirs_exist_ok=True)
        else:
            missing.append(src)
    print(f"copied into {DATA}")
    if missing:
        print(
            "MISSING (the bench tasks that need them will fail):", *missing, sep="\n  "
        )


if __name__ == "__main__":
    main()

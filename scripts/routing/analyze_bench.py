"""Read the bench log: accuracy and seconds for each task and model family.

    python -m scripts.routing.analyze_bench table          print every task
    python -m scripts.routing.analyze_bench plan           write the round 2 finalists
    python -m scripts.routing.analyze_bench write          propose a new accuracy.py
    python -m scripts.routing.analyze_bench write --apply  ... and put it in place

Calls no model. Rules for a row, so a network fault never counts as a wrong
answer: a case refused for quota ("limited") or lost to the network is left out;
a case where some calls gave up and others answered is left out (it is a
reliability fact, not an accuracy fact); a call that failed scores 0.

`plan` keeps, for each task: on a simple task, the models within 0.15 of the
best, fastest first, at most 10; on any other task, every model within 0.30 of
the best, every model whose calls hit the stop (it must be judged by its time,
not scored 0), and every model with no clean result yet. LiteRouter takes one
call at a time, so its models go to round 2 only where they are real candidates
(edit LITEROUTER_ROUND_2 below).
"""

from __future__ import annotations

import json
import shutil
import statistics as st
import subprocess
import sys
from collections import defaultdict

from scripts.routing._common import DATA, LLM, LOGS, PROPOSED, read_jsonl

LOG = LOGS / "bench.jsonl"
FINAL_GAP = 0.15
SIMPLE = {"gate", "fresh", "rewrite", "summary", "respond_chat", "merge"}
LITEROUTER_ROUND_2 = {
    "GLM-5.3 Flash": {
        "claims",
        "scan",
        "trace",
        "audit",
        "method",
        "concept",
        "checklist",
        "checklist_audit",
        "skeptic",
        "judge",
        "respond_one",
        "respond_two",
    },
    "MiniMax M3.1 Flash": {"checklist", "skeptic", "judge"},
    "DeepSeek V4 Pro": {"respond_one", "respond_two"},
}


def load():
    cells = defaultdict(list)
    for row in read_jsonl(LOG):
        cells[(row["task"], row["family"])].append(row)
    return cells


def summary(rows):
    lim = sum(1 for r in rows if r.get("limited") or r.get("network"))
    part = [r for r in rows if r.get("gave_up") and r.get("answered")]
    rows = [
        r for r in rows if not (r.get("limited") or r.get("network")) and r not in part
    ]
    if not rows:
        return {
            "acc": 0.0,
            "n": 0,
            "fail": 0,
            "sec": None,
            "wrong_halt": 0,
            "limited": lim,
        }
    scores = [max(0.0, r["score"]) if r["ok"] else 0.0 for r in rows]
    secs = [
        r["seconds"] if r["seconds"] > 0 else r.get("wall", r["seconds"])
        for r in rows
        if r["ok"]
    ]
    return {
        "acc": sum(scores) / len(scores),
        "n": len(rows),
        "fail": sum(not r["ok"] for r in rows),
        "sec": st.median(secs) if secs else None,
        "wrong_halt": sum(r["score"] < 0 for r in rows),
        "limited": lim,
    }


def table():
    by_task = defaultdict(dict)
    for (task, fam), rows in load().items():
        by_task[task][fam] = summary(rows)
    return by_task


def plan(by_task):
    from scripts.routing import bench as B

    cells = load()
    out = {}
    for task in B.RUNNERS:
        fams = by_task.get(task, {})
        best = max((s["acc"] for s in fams.values() if s["n"]), default=0)
        cand = [f for f in B.F if B.tiers_for(f, task)]
        lr = {f for f in cand if B.F[f][1] == "lr"}
        cand = [
            f for f in cand if f not in lr or task in LITEROUTER_ROUND_2.get(f, set())
        ]
        if task in SIMPLE:
            close = [
                f for f, s in fams.items() if s["n"] and s["acc"] >= best - FINAL_GAP
            ]
            out[task] = [
                f
                for f in sorted(close, key=lambda f: fams[f]["sec"] or 999)[:10]
                if f in cand
            ]
            continue
        keep = []
        for f in cand:
            s = fams.get(f)
            stop = B.STOP.get(task, 90)
            hit_stop = any(
                r.get("wall", r["seconds"]) >= stop * 0.95
                for r in cells.get((task, f), [])
            )
            if s is None or not s["n"] or s["acc"] >= best - 0.3 or hit_stop:
                keep.append(f)
        out[task] = keep
    return out


def write(by_task, apply: bool):
    try:
        from labpilot.llm.ratings import RATINGS

        live = {r.family for r in RATINGS.values()}
    except ImportError:  # no ratings table yet: keep every family
        live = None
    lines = [
        '"""Lesson 3 bench results (section 33): for each task, each model family\'s',
        "accuracy 0..1, median seconds and number of cases, measured with the product",
        "prompts and readers on the labelled cases. WRITTEN BY A SCRIPT",
        "(scripts/routing/analyze_bench.py) from the bench log,",
        "artifacts/routing-bench/logs/bench.jsonl.",
        'A family that is not here gets an accuracy guessed from its strength."""',
        "",
        "ACCURACY: dict[str, dict[str, tuple[float, float, int]]] = {",
    ]
    for task in sorted(by_task):
        lines.append(f"    {task!r}: {{")
        for f, s in sorted(by_task[task].items(), key=lambda kv: -kv[1]["acc"]):
            if not s["n"] or (live is not None and f not in live):
                continue
            sec = s["sec"] if s["sec"] is not None else 999.0
            lines.append(f"        {f!r}: ({s['acc']:.2f}, {sec:.1f}, {s['n']}),")
        lines.append("    },")
    lines.append("}")
    target = PROPOSED / "accuracy.py"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    subprocess.run(["ruff", "format", "--quiet", str(target)], check=False)
    print(f"proposed: {target}")
    if apply:
        shutil.copy2(target, LLM / "accuracy.py")
        print(f"applied: {LLM / 'accuracy.py'}  (review the diff, then run the tests)")


def main(argv):
    mode = argv[1] if len(argv) > 1 else "table"
    t = table()
    if mode == "table":
        for task in sorted(t):
            print(f"\n== {task}")
            for f, s in sorted(
                t[task].items(), key=lambda kv: (-kv[1]["acc"], kv[1]["sec"] or 9e9)
            ):
                sec = f"{s['sec']:6.1f}s" if s["sec"] else "    -  "
                print(
                    f"  {s['acc']:.2f}  n{s['n']:2d} fail{s['fail']:2d} {sec}  {f}"
                    + (f"  WRONG HALT x{s['wrong_halt']}" if s["wrong_halt"] else "")
                    + (f"  limited x{s['limited']}" if s["limited"] else "")
                )
    elif mode == "plan":
        out = plan(t)
        (DATA / "r2_plan.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
        for task, fams in out.items():
            print(f"{task:15s} {len(fams):2d}  {', '.join(fams)}")
        print(f"written: {DATA / 'r2_plan.json'}")
    elif mode == "write":
        write(t, apply="--apply" in argv)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)

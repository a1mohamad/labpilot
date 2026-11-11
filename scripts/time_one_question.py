"""Where do the seconds of one question go? (S1, slice 10)

The M33 run took 1,318 s and 37 model calls for a first question, and nobody
could say which step was slow. This runs the REAL ask path (`asking.ask`), turns
on the two clocks of `labpilot.timing`, and prints for every question:

    the steps       each graph node: when it started, how long it ran, and a
                    star when it is on the chain that decided the wall clock
    the calls       the model calls of each step, grouped by tool: how many,
                    total and longest seconds, tiers that failed first
    the gaps        time outside every node (graph build, chat load and save)

    python -m scripts.time_one_question --pair otp --out otp.json

Nothing else may run on the providers while it measures: two measurements at
once slow each other, and a slow moment of a provider looks like a slow step.
The first question is run `--runs-first` times (each from a clean start, with
the saved results of D104 deleted), because one run is one sample.
"""

from __future__ import annotations

import argparse
import json
import secrets
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from dotenv import load_dotenv

from labpilot.api import asking
from labpilot.api.checkpoints import open_saver
from labpilot.api.ingestion import ingest_artifact, ingest_source
from labpilot.llm import LLMClient
from labpilot.sources import open_folder
from labpilot.store import connect, create_schema, database_url
from labpilot.timing import collecting

ROOT = Path(__file__).resolve().parents[1]
FIRST = "Compare these and explain why the results diverge."

# A step starts a moment after the one before it ends (LangGraph's own work),
# so "ended before" allows this much.
HANDOVER = 0.05

PAIRS = {
    "otp": {
        "a": "artifacts/slice9-study/cases/otp/A_rfc_hotp_totp.txt",
        "b": "artifacts/slice9-study/cases/otp/B",
        "follow_ups": {
            "saved": "Explain the first difference you listed in more detail.",
            "chat": "What is HMAC, in two sentences?",
        },
    },
    "quora": {
        "a": "data/samples/quora_siamese/A_paper.md",
        "b": "data/samples/quora_siamese/B_train.py",
        "follow_ups": {
            "saved": "Explain the first difference you listed in more detail.",
            "chat": "What is a siamese network, in two sentences?",
        },
    },
}


# ---- the reading of the two clocks (pure, tested) --------------------------


def critical_path(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The chain of steps that decided the wall clock, first step first.

    It starts from the step that ended last, then goes back: the step before
    it is the one that ended last before it started. Steps that ran beside the
    chain (the planner beside the summaries) end earlier and are not on it.
    This is built from the TIMES, not from the arrows of the graph, so it is an
    estimate; when two steps end almost together, the other one could be named.
    """
    if not steps:
        return []
    path = [max(steps, key=lambda s: s["end"])]
    while True:
        current = path[-1]
        before = [
            s
            for s in steps
            if s is not current and s["end"] <= current["start"] + HANDOVER
        ]
        if not before:
            break
        path.append(max(before, key=lambda s: s["end"]))
    return path[::-1]


def call_table(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The calls grouped by (step, tool), the slowest group first."""
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for call in calls:
        key = (call["step"] or "-", call["tool"] or "text")
        row = groups.setdefault(
            key,
            {
                "step": key[0],
                "tool": key[1],
                "calls": 0,
                "seconds": 0.0,
                "longest": 0.0,
                "failed_tiers": 0,
                "no_answer": 0,
            },
        )
        row["calls"] += 1
        row["seconds"] += call["seconds"]
        row["longest"] = max(row["longest"], call["seconds"])
        row["failed_tiers"] += call["failed"]
        row["no_answer"] += call["tier"] is None
    return sorted(groups.values(), key=lambda r: r["seconds"], reverse=True)


def summarize_run(
    records: list[dict[str, Any]], started: float, ended: float
) -> dict[str, Any]:
    """Everything one question measured, ready to print and to save."""
    steps = [r for r in records if r["kind"] == "step"]
    calls = [r for r in records if r["kind"] == "call"]
    path = critical_path(steps)
    on_path = {id(s) for s in path}
    first = min((s["start"] for s in steps), default=started)
    last = max((s["end"] for s in steps), default=ended)
    return {
        "wall": ended - started,
        "before_graph": first - started,
        "after_graph": ended - last,
        "steps": [
            {
                "name": s["name"],
                "offset": s["start"] - started,
                "seconds": s["seconds"],
                "on_path": id(s) in on_path,
            }
            for s in sorted(steps, key=lambda s: s["start"])
        ],
        "path_seconds": sum(s["seconds"] for s in path),
        "calls": call_table(calls),
        "model_calls": len(calls),
        "model_seconds": sum(c["seconds"] for c in calls),
    }


def render(label: str, run: dict[str, Any]) -> str:
    lines = [
        f"== {label}: {run['wall']:.1f} s, {run['model_calls']} model calls",
        f"   before the first step {run['before_graph']:.1f} s, "
        f"after the last {run['after_graph']:.1f} s "
        "(graph build, chat load and save)",
        f"   {'step':<14}{'starts':>8}{'seconds':>9}",
    ]
    for step in run["steps"]:
        star = " *" if step["on_path"] else ""
        lines.append(
            f"   {step['name']:<14}{step['offset']:>8.1f}{step['seconds']:>9.1f}{star}"
        )
    lines.append(
        f"   * = on the chain that decided the wall clock "
        f"({run['path_seconds']:.1f} s of steps)"
    )
    lines.append(
        f"   {'step / tool':<34}{'calls':>6}{'total s':>9}{'longest':>9}"
        f"{'failed':>8}{'none':>6}"
    )
    for row in run["calls"]:
        name = f"{row['step']} / {row['tool']}"
        lines.append(
            f"   {name:<34}{row['calls']:>6}{row['seconds']:>9.1f}"
            f"{row['longest']:>9.1f}{row['failed_tiers']:>8}{row['no_answer']:>6}"
        )
    lines.append(
        "   (calls of steps that run at the same time overlap, so their seconds "
        "add up to more than the wall clock)"
    )
    return "\n".join(lines)


# ---- the run ----------------------------------------------------------------


def with_search_path(url: str, schema: str) -> str:
    # A libpq STARTUP option survives a pooler reset; a runtime SET does not
    # (tests/conftest.py explains the 2026-09-04 flake).
    parts = urlsplit(url)
    option = quote(f"-c search_path={schema},public", safe="")
    query = f"{parts.query}&options={option}" if parts.query else f"options={option}"
    return urlunsplit(parts._replace(query=query))


def ask_once(conn, a: str, b: str, thread: str, question: str, kind: str) -> dict:
    client = LLMClient()
    with collecting() as collector:
        started = time.time()
        comparison = asking.ask(
            conn, a, b, question=question, client=client, thread_id=thread
        )
        ended = time.time()
    run = summarize_run(collector.records, started, ended)
    run.update(
        kind=kind,
        question=question,
        reused=list(comparison.reused),
        model=comparison.result.model,
        searched=comparison.totals is not None,
        answer_chars=len(comparison.result.text),
    )
    print(render(f"{kind} ({'search' if run['searched'] else 'stuffed'})", run))
    print(f"   answered by {run['model']}; reused {run['reused']}", flush=True)
    return run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--pair", choices=sorted(PAIRS), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--runs-first", type=int, default=1)
    parser.add_argument(
        "--follow-ups", default="saved,chat", help="comma list, or an empty string"
    )
    parser.add_argument(
        "--root", type=Path, default=ROOT, help="where the pair files are"
    )
    args = parser.parse_args()
    pair = PAIRS[args.pair]

    load_dotenv(".env")
    schema = f"labpilot_s1_{secrets.token_hex(3)}"
    base = database_url()
    with connect(base, autocommit=True) as admin:
        admin.execute(f"create schema {schema}")
    runs: list[dict] = []
    try:
        with connect(with_search_path(base, schema), autocommit=True) as conn:
            create_schema(conn)
            open_saver(conn).setup()
            a_path = args.root / pair["a"]
            a = ingest_artifact(
                conn, a_path.read_bytes(), name=a_path.name, side="A"
            ).artifact.id
            b_path = args.root / pair["b"]
            if b_path.is_dir():
                with open_folder(b_path) as source:
                    b = ingest_source(conn, source, side="B").artifact.id
            else:
                b = ingest_artifact(
                    conn, b_path.read_bytes(), name=b_path.name, side="B"
                ).artifact.id

            thread = ""
            for _ in range(args.runs_first):
                # A fresh chat, and no saved results, so each is a FIRST question.
                conn.execute("delete from saved_results")
                thread = f"s1-{secrets.token_hex(3)}"
                runs.append(ask_once(conn, a, b, thread, FIRST, "first"))
                args.out.write_text(json.dumps(runs, indent=1), "utf-8")
            for kind in filter(None, args.follow_ups.split(",")):
                runs.append(
                    ask_once(conn, a, b, thread, pair["follow_ups"][kind], kind)
                )
                args.out.write_text(json.dumps(runs, indent=1), "utf-8")
    finally:
        with connect(base, autocommit=True) as admin:
            admin.execute(f"drop schema {schema} cascade")
        print("schema dropped", schema)


if __name__ == "__main__":
    main()

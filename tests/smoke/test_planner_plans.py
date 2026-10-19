"""THE REAL PLANNER, ON A STORED PAIR, WITH A REAL MODEL.

Why this calls `make_planner` and not the graph: the planner node hides every
failure on purpose. A planner that cannot read the model answer, or that is
rejected by `check_plan`, quietly becomes the default plan, and the answer
still arrives. So a broken planner looks exactly like a working graph. Only the
function itself, called alone, can show that it is broken.

WHAT THIS SPENDS, per run: two ingests of embedder quota and ONE planner call
on whatever tier leads the chain. It needs a live Postgres, so it carries both
gates.

WHAT IT CHECKS: the plan obeys the rules (`problem_with` is None) and is not
empty. It does NOT check that the plan is a good one. Whether the steps and the
queries are sensible is a measurement (M5, M16), not a pass or fail.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from dotenv import load_dotenv

from labpilot.agent import present_sides
from labpilot.agent.plan_check import problem_with
from labpilot.api import ingestion, planning
from labpilot.llm import LLMClient

load_dotenv()

SAMPLES = Path("data/samples/quora_siamese")
QUESTION = "Why does my training code get a lower F1 than the paper reports?"


@pytest.mark.smoke
def test_the_planner_makes_a_plan_the_rules_accept_from_a_stored_pair(db):
    a = ingestion.ingest_artifact(
        db, (SAMPLES / "A_paper.md").read_bytes(), name="A_paper.md", side="A"
    )
    b = ingestion.ingest_artifact(
        db, (SAMPLES / "B_train.py").read_bytes(), name="B_train.py", side="B"
    )
    plan = planning.make_planner(db, LLMClient())(
        QUESTION, a.artifact.id, b.artifact.id
    )

    print(plan)

    sides = present_sides(a.artifact.id, b.artifact.id)
    assert problem_with(plan, sides) is None
    assert plan.steps or plan.queries, (
        "a plan with no steps and no queries does nothing"
    )

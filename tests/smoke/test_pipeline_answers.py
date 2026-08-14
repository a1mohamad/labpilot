from datetime import datetime
from pathlib import Path

import pytest
from dotenv import load_dotenv

from labpilot.ingest import chunk_file
from labpilot.llm import LLMClient
from labpilot.prompts import (
    CORE,
    FULL,
    PROMPT_BUDGET,
    REPORT_MAX_TOKENS,
    build_prompt,
    find_citations,
    reserve,
    resolve,
)
from labpilot.retrieval import select
from labpilot.tokens import estimate_tokens

load_dotenv()

SAMPLES = Path("data/samples/quora_siamese")
ARTIFACTS = Path("artifacts")
QUESTION = "Compare these and explain why the results diverge."
COLUMNS = (
    "version",
    "model",
    "tier",
    "chunks",
    "prompt tokens",
    "citations",
    "resolved",
    "finish",
)

_ROWS: list[str] = []


@pytest.fixture(scope="module", autouse=True)
def comparison():
    _ROWS.clear()
    yield
    if not _ROWS:
        return

    ARTIFACTS.mkdir(exist_ok=True)
    path = ARTIFACTS / f"{_stamp()}_comparison.md"
    header = f"| {' | '.join(COLUMNS)} |\n|{'---|' * len(COLUMNS)}"
    path.write_text("\n".join((header, *_ROWS)) + "\n", encoding="utf-8")
    print(f"\nsaved -> {path}")


@pytest.mark.smoke
@pytest.mark.parametrize("instructions", (FULL, CORE), ids=("full", "core"))
def test_the_pipeline_answers_from_the_sample_pair(instructions):
    chunks = chunk_file(
        SAMPLES / "A_paper.md", side="A", artifact_id="quora"
    ) + chunk_file(SAMPLES / "B_train.py", side="B", artifact_id="quora")

    room = PROMPT_BUDGET - reserve(chunks, question=QUESTION, instructions=instructions)
    picked = select(chunks, budget=room)
    prompt = build_prompt(chunks, picked, question=QUESTION, instructions=instructions)
    result = LLMClient().generate(prompt, max_tokens=REPORT_MAX_TOKENS)

    assert result.text
    _save(prompt, chunks, picked, result, instructions)


def _stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M")


def _save(prompt, chunks, picked, result, instructions):
    ARTIFACTS.mkdir(exist_ok=True)
    model = result.model.replace("/", "-")
    path = ARTIFACTS / f"{_stamp()}_{instructions.name}_{model}.md"

    cited = find_citations(result.text)
    resolved = [pair for pair in cited if resolve(pair[0], pair[1], chunks)]
    failed = [attempt.model for attempt in result.attempts]
    tokens = estimate_tokens(prompt)

    report = (
        f"# {instructions.name} · {result.model} (tier {result.tier})\n\n"
        f"- finish reason: {result.finish_reason}\n"
        f"- chunks sent: {len(picked)} of {len(chunks)}\n"
        f"- prompt tokens: {tokens}\n"
        f"- max output tokens asked for: {REPORT_MAX_TOKENS}\n"
        f"- citations written: {len(cited)}\n"
        f"- citations that resolve: {len(resolved)}\n"
        f"- failed tiers: {failed or 'none'}\n\n"
        f"## Answer\n\n{result.text}\n\n"
        f"## Prompt that produced it\n\n{prompt}\n"
    )
    path.write_text(report, encoding="utf-8")

    _ROWS.append(
        f"| {instructions.name} | {result.model} | {result.tier} "
        f"| {len(picked)}/{len(chunks)} | {tokens} "
        f"| {len(cited)} | {len(resolved)} | {result.finish_reason} |"
    )
    print(f"\nsaved -> {path}")

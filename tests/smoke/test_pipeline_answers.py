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

load_dotenv()

SAMPLES = Path("data/samples/quora_siamese")
ARTIFACTS = Path("artifacts")
QUESTION = "Compare these and explain why the results diverge."


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


def _save(prompt, chunks, picked, result, instructions):
    ARTIFACTS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    model = result.model.replace("/", "-")
    path = ARTIFACTS / f"{stamp}_{instructions.name}_{model}.md"

    cited = find_citations(result.text)
    resolved = [pair for pair in cited if resolve(pair[0], pair[1], chunks)]
    failed = [attempt.model for attempt in result.attempts]

    report = (
        f"# {instructions.name} · {result.model} (tier {result.tier})\n\n"
        f"- chunks sent: {len(picked)} of {len(chunks)}\n"
        f"- prompt characters: {len(prompt)}\n"
        f"- citations written: {len(cited)}\n"
        f"- citations that resolve: {len(resolved)}\n"
        f"- failed tiers: {failed or 'none'}\n\n"
        f"## Answer\n\n{result.text}\n\n"
        f"## Prompt that produced it\n\n{prompt}\n"
    )
    path.write_text(report, encoding="utf-8")
    print(f"\nsaved -> {path}")

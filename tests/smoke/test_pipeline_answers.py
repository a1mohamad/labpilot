from datetime import datetime
from pathlib import Path

import pytest
from dotenv import load_dotenv

from labpilot.ingest import chunk_file
from labpilot.llm import LLMClient
from labpilot.prompts import build_context
from labpilot.retrieval import select

load_dotenv()

SAMPLES = Path("data/samples/quora_siamese")
ARTIFACTS = Path("artifacts")
QUESTION = "Compare these and explain why the results diverge."


@pytest.mark.smoke
def test_the_pipeline_answers_from_the_sample_pair():
    chunks = chunk_file(
        SAMPLES / "A_paper.md", side="A", artifact_id="quora"
    ) + chunk_file(SAMPLES / "B_train.py", side="B", artifact_id="quora")

    picked = select(chunks)
    prompt = f"{build_context(picked)}\n\n{QUESTION}"
    result = LLMClient().generate(prompt, max_tokens=8000)

    assert result.text
    _save(prompt, picked, result)


def _save(prompt, picked, result):
    ARTIFACTS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    path = ARTIFACTS / f"{stamp}_{result.model.replace('/', '-')}.md"

    report = (
        f"# {result.model} (tier {result.tier})\n\n"
        f"- chunks sent: {len(picked)}\n"
        f"- prompt characters: {len(prompt)}\n"
        f"- failed tiers: {[a.model for a in result.attempts] or 'none'}\n\n"
        f"## Answer\n\n{result.text}\n\n"
        f"## Prompt that produced it\n\n{prompt}\n"
    )
    path.write_text(report, encoding="utf-8")
    print(f"\nsaved -> {path}")

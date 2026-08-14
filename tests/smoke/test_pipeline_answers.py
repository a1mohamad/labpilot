from pathlib import Path

import pytest
from dotenv import load_dotenv

from labpilot.ingest import chunk_file
from labpilot.llm import LLMClient
from labpilot.prompts import build_context
from labpilot.retrieval import select

load_dotenv()

SAMPLES = Path("data/samples/quora_siamese")
QUESTION = "Compare these and explain why the results diverge."


@pytest.mark.smoke
def test_pipeline_answers_from_the_sample_pairs():
    chunks = chunk_file(
        SAMPLES / "A_paper.md", side="A", artifact_id="quora"
    ) + chunk_file(SAMPLES / "B_train.py", side="B", artifact_id="quora")

    prompt = f"{build_context(select(chunks))}\n\n{QUESTION}"
    result = LLMClient.generate(prompt, max_tokens=2000)

    assert result.text
    print(f"\n--- answered by {result.model} (tier {result.tier}) ---\n{result.text}")

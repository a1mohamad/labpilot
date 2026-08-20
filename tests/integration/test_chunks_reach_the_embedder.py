from __future__ import annotations

import json
from pathlib import Path

import responses

from labpilot.embed import MAX_BATCH_SIZE, MistralEmbedder
from labpilot.ingest import chunk_file

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / "data" / "samples" / "quora_siamese" / "A_paper.md"
URL = "https://provider.test/v1/embeddings"

EMBEDDER = MistralEmbedder(name="Test Embed", url=URL, model="test-embed", dim=3)


@responses.activate
def test_real_chunks_reach_the_wire_in_order_and_keep_their_headers(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    chunks = chunk_file(PAPER, side="A", artifact_id="paper")
    assert len(chunks) <= MAX_BATCH_SIZE

    responses.add(
        responses.POST,
        URL,
        json={
            "model": "test-embed",
            "data": [
                {"object": "embedding", "index": index, "embedding": [1.0, 0.0, 0.0]}
                for index in range(len(chunks))
            ],
            "usage": {"prompt_tokens": 1},
        },
        status=200,
    )

    batch = EMBEDDER.embed([chunk.embed_text for chunk in chunks])

    sent = json.loads(responses.calls[0].request.body)["input"]

    assert len(batch.vectors) == len(chunks)
    assert sent[0].startswith("[A_paper.md")
    assert all(chunk.text in text for chunk, text in zip(chunks, sent, strict=True))

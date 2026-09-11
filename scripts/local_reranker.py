"""A cross-encoder that runs here, on the CPU, for nothing.

WHY THIS LIVES IN scripts/ AND NOT IN labpilot/
===============================================
CLAUDE.md settled it on 2026-08-11: the local reranker is a DEV dependency and
is deliberately NOT a tier of chain 3. It costs ~120MB resident against a 512MB
Render box that the API and ingest already share, and with four remote tiers
ahead of it, it would almost never be reached in production.

Putting it under labpilot/ would also break a real guard -
test_every_package_labpilot_imports_is_pinned AST-scans the package and demands
every import appear in requirements.txt, including imports nested inside a
function. Satisfying it would ship onnxruntime to that 512MB box. The guard is
right and the module is what should move.

It is still fully usable by the production chain, because `Reranker` is a
PROTOCOL rather than a base class:

    from labpilot.rerank import rerank
    rerank("why", docs, chain=(LOCAL_RERANK,))

That is the payoff of structural typing over inheritance: a tool we refuse to
deploy can still drive the code we do deploy, with no shared import.

WHAT MAKES IT STRUCTURALLY DIFFERENT, NOT MERELY CHEAPER
========================================================
Every API tier takes ONE query per call - measured on all three, three
different refusals (400/400/422). A cross-encoder is pointwise, so N documents
is N independent forward passes, and running the model ourselves means they go
through in ONE batch. No rate limit, no quota, no per-call billing.

That matters at Step 2, where `verify` needs one rerank call per claim: Cohere
gives 1,000 calls a MONTH and Voyage allows one 50-document call per ~70s,
while this has no call count at all.

    pip install onnxruntime tokenizers      (dev only - see requirements-dev)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import requests

from labpilot.rerank import Ranking, RerankError

REPO = "Xenova/ms-marco-MiniLM-L-6-v2"
FILES = {
    "model": "onnx/model_quantized.onnx",
    "tokenizer": "tokenizer.json",
}
CACHE = Path(".cache/models/ms-marco-MiniLM-L-6-v2")

# The model's own ceiling, and unlike an API limit it TRUNCATES silently rather
# than refusing - so the cap is enforced here or it is enforced nowhere.
MAX_SEQUENCE = 512


def _fetch(name: str) -> Path:
    target = CACHE / Path(FILES[name]).name
    if target.exists():
        return target
    CACHE.mkdir(parents=True, exist_ok=True)
    url = f"https://huggingface.co/{REPO}/resolve/main/{FILES[name]}"
    response = requests.get(url, timeout=(10, 300))
    if response.status_code != 200:
        raise RerankError(f"could not download {name}: HTTP {response.status_code}")
    target.write_bytes(response.content)
    return target


@dataclass(slots=True)
class LocalReranker:
    """ms-marco-MiniLM-L-6-v2, int8, ~23MB on disk.

    Mutable and not frozen, unlike every HTTP provider, because it carries a
    loaded ONNX session - an expensive object that must be built once and kept.
    """

    name: str = "MiniLM L6 cross-encoder (local)"
    model: str = "ms-marco-MiniLM-L-6-v2"
    # No API is being called, so the only ceilings are the model's own.
    max_documents: int = 10_000
    max_document_tokens: int = 510
    _session: object | None = field(default=None, repr=False)
    _tokenizer: object | None = field(default=None, repr=False)

    def _load(self) -> tuple[object, object]:
        if self._session is not None and self._tokenizer is not None:
            return self._session, self._tokenizer
        try:
            import onnxruntime
            from tokenizers import Tokenizer
        except ImportError as exc:  # pragma: no cover - environment, not logic
            raise RerankError(
                "the local reranker needs onnxruntime and tokenizers, which are "
                "DEV dependencies and are never deployed: pip install -r "
                "requirements-dev.txt"
            ) from exc

        tokenizer = Tokenizer.from_file(str(_fetch("tokenizer")))
        tokenizer.enable_truncation(max_length=MAX_SEQUENCE)
        # Pad to the LONGEST IN BATCH, and that is measured rather than
        # assumed. score_rerank.py's pointwise check caught this model drifting
        # 3.3e-05 between a 2-document and a 10-document call: the tokenizer
        # output is bit-identical, so the cause is int8 GEMM being sensitive to
        # the batch SHAPE, not to the content.
        #
        # Padding to a fixed 512 was the obvious fix and made it FAR worse -
        # drift 5.6e-02, with one pair's score moving from 0.0003 to 0.72 -
        # because 490 of 512 tokens become padding and this ONNX export's
        # attention mask does not fully neutralise them. Minimal padding is the
        # correct choice; the residual 3e-05 is recorded and tolerated, and
        # score_rerank.py carries a per-model tolerance because of it.
        tokenizer.enable_padding()
        self._tokenizer = tokenizer
        self._session = onnxruntime.InferenceSession(
            str(_fetch("model")), providers=["CPUExecutionProvider"]
        )
        return self._session, self._tokenizer

    def rank(self, query: str, documents, *, top_n: int | None = None) -> Ranking:
        if not query.strip():
            raise ValueError("the rerank query must not be blank")
        documents = list(documents)
        if not documents:
            raise ValueError("there are no documents to rank")
        if top_n is not None and top_n < 1:
            raise ValueError(f"top_n must be positive, got {top_n}")

        session, tokenizer = self._load()

        # THE WHOLE POINT: every (query, document) pair in one forward pass.
        encoded = tokenizer.encode_batch([(query, d) for d in documents])
        feeds = {
            "input_ids": [e.ids for e in encoded],
            "attention_mask": [e.attention_mask for e in encoded],
            "token_type_ids": [e.type_ids for e in encoded],
        }
        wanted = {i.name for i in session.get_inputs()}
        import numpy

        batch = {
            name: numpy.array(value, dtype=numpy.int64)
            for name, value in feeds.items()
            if name in wanted
        }

        logits = session.run(None, batch)[0]
        # One logit per pair. Sigmoid only to put it on 0..1 for a reader - it
        # is monotonic, so it cannot change the ORDER, which is the output.
        scores = [1.0 / (1.0 + math.exp(-float(row[0]))) for row in logits]

        ordered = sorted(range(len(documents)), key=lambda i: (-scores[i], i))
        if top_n is not None:
            ordered = ordered[:top_n]
        return Ranking(
            order=tuple(ordered),
            scores=tuple(scores[i] for i in ordered),
            model=self.model,
        )


LOCAL_RERANK = LocalReranker()

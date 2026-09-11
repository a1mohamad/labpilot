"""Weekly proof that each reranker is alive AND still ranks sensibly.

Cost is 3 calls a week: 1 Cohere of 1,000 a MONTH, 1 Voyage of ~16,000 once,
1 Cloudflare of ~2,840 a day. Cohere's bucket is shared with chat and embed and
is already touched weekly by test_embedders, so this adds ~4 calls a month to a
1,000 ceiling.

It asserts more than aliveness. A reranker that answers 200 with a useless
order is worse than one that fails, because the chain accepts it and the report
quietly loses its evidence.

WHY THE DECOYS EXCLUDE EVERY CLIPPING WORD, measured 2026-09-11. The first
version of this test drew decoys from the top of the file, and two of three
rerankers "failed" - correctly. Chunk 1 holds
`from torch.nn.utils import clip_grad_norm_`, the literal phrase, while the
chunk that really sets `CLIP_NORM = 1.5` never uses the word "gradient" at all
and buries one line in a 42-line config block. Ranking the import higher is
defensible, so the fixture was wrong and the providers were not.

That is a finding, not an inconvenience, and it belongs to the MEASUREMENT
rather than to a liveness check: a cross-encoder answers "where does this
happen", not "what is this set to", exactly as the bi-encoder does. A smoke
test must not encode our hardest open research question as a pass condition.
"""

import dataclasses

import pytest
from dotenv import load_dotenv

from labpilot.ingest import chunk_file
from labpilot.llm.registry import (
    GEMINI_3_1_FLASH_LITE,
    GEMINI_3_5_FLASH_LITE,
    GEMMA_4_31B,
)
from labpilot.rerank import RERANK_CHAIN, LLMReranker
from tests.smoke.test_embedders import SAMPLES

load_dotenv()

QUERY = "gradients are clipped at a global norm"
CLIPPING_WORDS = ("clip", "grad", "norm")

CHUNKS = chunk_file(SAMPLES / "B_train.py", side="B", artifact_id="code")
ANSWER = next(c for c in CHUNKS if "CLIP_NORM = 1.5" in c.text)
DECOYS = [
    c
    for c in CHUNKS
    if c is not ANSWER and not any(word in c.text.lower() for word in CLIPPING_WORDS)
][:4]

DOCUMENTS = [c.embed_text for c in (*DECOYS, ANSWER)]
WANTED = len(DOCUMENTS) - 1


@pytest.mark.smoke
def test_the_fixture_gives_the_answer_the_only_claim_on_the_query():
    """It protects the live tests from grading the wrong thing.

    If a decoy ever mentions clipping again, the three smoke tests below stop
    measuring the providers and start measuring this file.

    It spends no quota, but it still carries the marker: anything unmarked in
    tests/smoke/ runs on EVERY push, which is what the suite rule forbids - and
    this guard only matters on the runs where the live tests actually execute.
    """
    assert len(DECOYS) == 4
    for decoy in DECOYS:
        assert not any(word in decoy.text.lower() for word in CLIPPING_WORDS)


@pytest.mark.smoke
@pytest.mark.parametrize("reranker", RERANK_CHAIN, ids=lambda r: r.model)
def test_every_reranker_is_alive_and_puts_the_real_answer_first(reranker):
    ranking = reranker.rank(QUERY, DOCUMENTS)

    assert ranking.model == reranker.model
    assert len(ranking.order) == len(DOCUMENTS)
    assert set(ranking.order) == set(range(len(DOCUMENTS)))
    assert ranking.order[0] == WANTED, (
        f"{reranker.name} ranked document {ranking.order[0]} above the chunk "
        f"that actually sets CLIP_NORM; scores were {ranking.scores}"
    )


# THE LLM TIERS, which now LEAD chain 3 and had no liveness check at all - the
# four we intend to use most were the only four nobody was watching.
#
# Cost is 4 calls a week against 500/day for each Flash-Lite and 14,400/day for
# each Gemma. Negligible, and it is the only thing that would notice a model
# being withdrawn or its output format changing.
#
# Built here rather than in labpilot/rerank/ because an LLM reranker needs
# llm/, and an adapter may not import another adapter. This three-line binding
# IS the seam - see labpilot/rerank/llm.py.
RANKING_CONFIG = {
    "thinking": None,
    "generation_config": {
        "responseMimeType": "application/json",
        "responseSchema": {"type": "ARRAY", "items": {"type": "INTEGER"}},
    },
}

GEMMA_4_26B = dataclasses.replace(
    GEMMA_4_31B, name="Gemma 4 26B A4B", tier=16, model="gemma-4-26b-a4b-it"
)


def _listwise(provider) -> LLMReranker:
    tuned = dataclasses.replace(provider, **RANKING_CONFIG)
    return LLMReranker(
        complete=lambda prompt, budget: tuned.complete(prompt, max_tokens=budget).text,
        name=tuned.name,
        model=tuned.model,
    )


LLM_TIERS = [
    _listwise(provider)
    for provider in (
        GEMINI_3_5_FLASH_LITE,
        GEMINI_3_1_FLASH_LITE,
        GEMMA_4_26B,
        GEMMA_4_31B,
    )
]


@pytest.mark.smoke
@pytest.mark.parametrize("reranker", LLM_TIERS, ids=lambda r: r.model)
def test_every_llm_tier_is_alive_and_puts_the_real_answer_first(reranker):
    """Same assertion as the cross-encoders, because the same thing can break.

    A model that answers 200 with a useless order is worse than one that
    fails, and an LLM has a second way to go wrong that a cross-encoder does
    not: it can stop producing a parseable ranking at all. `declined` catches
    that - it is invisible in the order itself, because a decline keeps the
    retrieval order and looks exactly like agreement.
    """
    ranking = reranker.rank(QUERY, DOCUMENTS)

    assert reranker.declined == 0, (
        f"{reranker.name} returned no usable ranking - a decline keeps the "
        f"retrieval order, so it is invisible unless counted"
    )
    assert set(ranking.order) == set(range(len(DOCUMENTS)))
    assert ranking.order[0] == WANTED, (
        f"{reranker.name} ranked document {ranking.order[0]} above the chunk "
        f"that actually sets CLIP_NORM"
    )

"""The rerank chain, assembled where both adapters are visible.

No network: every test here replaces GeminiProvider.complete, so the four LLM
tiers are exercised as OBJECTS without a single request. What they pin is
wiring and configuration - the two things that fail silently rather than
loudly, because a mis-wired chain still returns a ranking and a mis-configured
tier still returns an answer.
"""

from __future__ import annotations

import dataclasses

import pytest

from labpilot.api import services
from labpilot.api.reranking import CHAIN, PROVIDERS, RANKING_CONFIG, _listwise, rank
from labpilot.llm import GeminiProvider, LLMResult
from labpilot.rerank import (
    JEV_RERANK,
    LLM_RERANK_ORDER,
    RERANK_CHAIN,
    LLMReranker,
)


@pytest.fixture
def recorded(monkeypatch) -> list[GeminiProvider]:
    """Every provider a reranker actually called, in order.

    The provider itself, not its name - because the failure this guards is a
    tier reporting one name while calling another model.
    """
    seen: list[GeminiProvider] = []

    def fake_complete(self, prompt: str, *, max_tokens: int = 0) -> LLMResult:
        seen.append(self)
        return LLMResult(text="1, 2", model=self.model, tier=0, finish_reason="STOP")

    monkeypatch.setattr(GeminiProvider, "complete", fake_complete)

    return seen


def test_the_llm_tiers_lead_the_chain_in_the_order_rerank_measured():
    """The ORDER belongs to rerank/, and this layer only supplies providers.

    Measured on quora at a 30-document window against vector alone's MRR of
    0.608 - all four beat every purpose-built cross-encoder, so they lead. If
    this layer ever reordered them it would silently overrule a measurement
    with a preference.
    """
    llm = [tier for tier in CHAIN if isinstance(tier, LLMReranker)]

    # EVERY tier appears TWICE from 2026-09-19 - once per Google account - so
    # the order is over DISTINCT models, and the twin must sit next to its
    # original rather than at the end. A spent pool is skipped for free, so the
    # strongest thing left after flash-lite runs out is flash-lite on the other
    # key, not a weaker model.
    distinct = list(dict.fromkeys(tier.model for tier in llm))
    assert distinct == list(LLM_RERANK_ORDER)
    for first, second in zip(llm[::2], llm[1::2], strict=True):
        assert first.model == second.model, "a twin must be ADJACENT to its original"

    assert CHAIN[len(CHAIN) - len(RERANK_CHAIN) :] == RERANK_CHAIN


def test_jev_sits_third_behind_both_flash_lite_keys():
    """A PAID tier must never come before a FREE allowance of a better one.

    Jev measured 0.770 on quora and 0.712 on geo, against flash-lite's 0.799
    and 0.681 - one corpus each, means 0.740 and 0.741. Indistinguishable, so
    the tie-break is budget, which is this project's own rule.

    Position 2 is flash-lite ON THE SECOND GOOGLE ACCOUNT: the same model,
    another free 500 a day. Slotting a billed tier between the two keys would
    spend money while a free allowance sat unused, and would break the reason
    _both_accounts keeps the twins adjacent.
    """
    assert CHAIN[2] is JEV_RERANK, (
        "Jev must sit third - after BOTH flash-lite keys, ahead of everything "
        f"else. The chain now starts {[t.name for t in CHAIN[:4]]}"
    )
    assert CHAIN[0].model == CHAIN[1].model == "gemini-3.5-flash-lite"


def test_jev_is_the_only_tier_that_does_not_depend_on_google():
    """Eight of twelve tiers are Google, and a refused VPN exit has already
    taken every Google endpoint from this project for a week.

    When that happens the rest of the chain is Cohere's 1,000 a MONTH and a
    Voyage that cannot take a 50-document window. Jev is the independent
    capacity, so losing it from the chain is not merely losing a rank.
    """
    google = [tier for tier in CHAIN if isinstance(tier, LLMReranker)]
    assert len(google) == 2 * len(LLM_RERANK_ORDER)
    assert JEV_RERANK in CHAIN
    assert JEV_RERANK.api_key_env == "OPENROUTER_API_KEY"


def test_every_llm_tier_is_tuned_for_ranking_and_not_for_generation(recorded):
    """The configuration is worth more than the choice of model.

    Measured 2026-09-11, same model and same corpus:

        gemini-3.5-flash-lite  TUNED    MRR 0.799
        gemini-3.5-flash-lite  UNTUNED  MRR 0.706

    0.093 apart, which is wider than the gap between flash-lite and Cohere's
    purpose-built cross-encoder. Every Gemini tier SHIPS thinking=MEDIUM for
    generation, so reusing a CHAIN entry unchanged would throw most of the
    gain away - and the ranking would still look plausible.
    """
    for tier in CHAIN:
        if isinstance(tier, LLMReranker):
            tier.rank("q", ["one", "two"])

    assert recorded, "the fixture must have intercepted the calls"
    for provider in recorded:
        assert provider.thinking is None, (
            "MEDIUM costs 3x the latency for the same answer"
        )
        assert provider.generation_config == RANKING_CONFIG["generation_config"]


def test_each_tier_calls_its_own_model_and_not_the_last_one(recorded):
    """THE LATE-BINDING TRAP, and why _listwise is a factory and not a loop body.

    Building the lambdas inline in a comprehension would close over the loop
    VARIABLE, so all four tiers would call whichever provider the loop ended
    on - while each still reported its own name. The chain would look healthy,
    one model would answer everything, and the measured order would be fiction.
    """
    tiers = [tier for tier in CHAIN if isinstance(tier, LLMReranker)]

    for tier in tiers:
        tier.rank("q", ["one", "two"])

    assert [provider.model for provider in recorded] == [tier.model for tier in tiers]


def test_a_tier_is_not_mutated_into_the_shared_registry_entry(recorded):
    """dataclasses.replace must COPY, never edit the provider in place.

    The same objects serve generation. If tuning mutated them, every report
    would silently start running at thinking=None with a JSON schema forced on
    it - a ranking setting leaking into the product's main path.
    """
    shipped = PROVIDERS["gemini-3.5-flash-lite"]

    _listwise(shipped).rank("q", ["one", "two"])

    assert shipped.thinking == "MEDIUM", "the registry entry is untouched"
    assert shipped.generation_config is None


def test_the_ask_path_reaches_the_assembled_chain_and_not_the_bare_one():
    """Step 5 is only half done until something CALLS it.

    `rerank()` defaults to RERANK_CHAIN, which holds only the cross-encoders -
    the four tiers that BEAT them are added here, at the one layer that may see
    both adapters. A chain built and never bound still returns rankings, from
    the weaker half of the measurement, with nothing to report it.
    """
    import inspect

    default = inspect.signature(services._best).parameters["rank"].default

    assert default is rank


def test_the_ranking_config_is_the_two_settings_that_were_measured():
    """Both were measured, and both are load-bearing.

    thinking=None   MEDIUM spent 930 thought tokens and 3x the latency on an
                    IDENTICAL 109-token answer.
    a JSON schema   gemma went 45.5s -> 14.4s, and its reply stopped being
                    prose wrapped around an answer, which a naive parser reads
                    as the model refusing to rank.
    """
    assert RANKING_CONFIG["thinking"] is None
    assert RANKING_CONFIG["generation_config"]["responseMimeType"] == "application/json"
    assert RANKING_CONFIG["generation_config"]["responseSchema"] == {
        "type": "ARRAY",
        "items": {"type": "INTEGER"},
    }


def test_a_tuned_tier_keeps_the_name_and_model_of_the_one_it_came_from():
    """A reranker that renamed itself would make every measurement unreadable."""
    shipped = PROVIDERS["gemma-4-31b-it"]

    tuned = _listwise(shipped)

    assert (tuned.name, tuned.model) == (shipped.name, shipped.model)
    assert dataclasses.replace(shipped, **RANKING_CONFIG).model == shipped.model


def test_every_google_rerank_tier_has_its_second_account():
    """Google bills per PROJECT per model, so a second key is a second allowance.

    The GENERATOR chain has used both keys since 2026-09-11. This one never
    did: all four LLM tiers sat on GOOGLE_API_KEY alone, so the rerank path had
    HALF the budget available to it - 29,800 calls a day where 59,600 were
    there for the taking.

    Found by running into it on 2026-09-19 while measuring RERANK_TOP_N. The
    chain refused with `GenerateRequestsPerDayPerProjectPerModel-FreeTier,
    limit: 500` while the identical model answered 200 on the other key, and
    the measurement fell through to a weaker tier for no reason.

    The same rule `test_every_google_embedder_has_a_second_account_behind_it`
    holds one package over.
    """
    llm = [tier for tier in CHAIN if tier.model in LLM_RERANK_ORDER]
    assert llm, "the LLM rerank tiers must lead the chain"

    for tier in llm:
        if "(key 2)" in tier.name:
            continue
        twin = f"{tier.name} (key 2)"
        assert any(other.name == twin for other in llm), (
            f"{tier.name} has no second-account twin, so half of Google's "
            "rerank budget is unreachable"
        )

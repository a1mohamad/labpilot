from types import SimpleNamespace

from labpilot.api.chains import (
    CLAIMS_FIRST,
    TRACE_FIRST,
    for_claims,
    for_trace,
    lead_with,
)
from labpilot.llm import CHAIN, GEMINI_3_1_FLASH_LITE, GEMINI_3_5_FLASH_LITE, LLMClient


def tier(model, name):
    return SimpleNamespace(model=model, name=name)


CHAIN_OF_FOUR = (
    tier("big", "big 1"),
    tier("lite", "lite 1"),
    tier("big", "big 2"),
    tier("lite", "lite 2"),
)


def names(chain):
    return [provider.name for provider in chain]


def test_the_tiers_of_a_model_move_to_the_front_and_the_rest_keep_their_order():
    led = lead_with(CHAIN_OF_FOUR, ["lite"])

    assert names(led) == ["lite 1", "lite 2", "big 1", "big 2"]


def test_the_models_lead_in_the_order_they_are_named():
    led = lead_with(CHAIN_OF_FOUR, ["lite", "big"])

    assert names(led) == ["lite 1", "lite 2", "big 1", "big 2"]
    assert names(lead_with(CHAIN_OF_FOUR, ["big", "lite"])) == [
        "big 1",
        "big 2",
        "lite 1",
        "lite 2",
    ]


def test_a_model_that_is_not_in_the_chain_moves_nothing():
    assert lead_with(CHAIN_OF_FOUR, ["other"]) == CHAIN_OF_FOUR


def test_nothing_is_added_and_nothing_is_lost():
    led = lead_with(CHAIN, CLAIMS_FIRST)

    assert len(led) == len(CHAIN)
    assert {id(provider) for provider in led} == {id(provider) for provider in CHAIN}


def test_the_real_chain_starts_with_flash_lite_on_every_account():
    led = lead_with(CHAIN, CLAIMS_FIRST)

    models = [provider.model for provider in led[:6]]
    assert (
        models == [GEMINI_3_5_FLASH_LITE.model] * 3 + [GEMINI_3_1_FLASH_LITE.model] * 3
    )


def test_a_client_gets_a_copy_with_the_flash_lite_tiers_first():
    client = LLMClient(chain=CHAIN_OF_FOUR, total_budget=5.0)
    flash = SimpleNamespace(model=GEMINI_3_5_FLASH_LITE.model, name="flash")
    other = LLMClient(chain=(CHAIN_OF_FOUR[0], flash), total_budget=5.0)

    led = for_claims(other)

    assert names(led.chain) == ["flash", "big 1"]
    assert led.total_budget == 5.0
    assert names(other.chain) == ["big 1", "flash"]
    assert for_claims(client).chain == CHAIN_OF_FOUR


def test_a_stand_in_without_a_chain_is_used_as_it_is():
    assert for_claims("client") == "client"


def test_the_trace_chain_starts_with_flash_lite_3_1_on_every_account():
    client = LLMClient(chain=CHAIN, total_budget=5.0)

    led = for_trace(client).chain

    assert TRACE_FIRST == (GEMINI_3_1_FLASH_LITE.model,)
    assert [provider.model for provider in led[:3]] == [GEMINI_3_1_FLASH_LITE.model] * 3
    assert len(led) == len(CHAIN)
    assert for_trace("client") == "client"


def test_the_skeptic_chain_starts_with_glm_5_3_and_keeps_every_tier():
    from labpilot.api.chains import SKEPTIC_FIRST, for_skeptic

    client = LLMClient(chain=CHAIN, total_budget=5.0)

    led = for_skeptic(client).chain

    assert led[0].model in SKEPTIC_FIRST[:2]
    assert len(led) == len(CHAIN)
    assert for_skeptic("client") == "client"


def test_a_dead_tier_of_a_leading_model_stays_at_the_tail():
    from labpilot.api.chains import for_skeptic
    from labpilot.llm import CLINE_GLM_5_3_FLASH, KNOWN_DEAD

    assert CLINE_GLM_5_3_FLASH.name in KNOWN_DEAD
    led = for_skeptic(LLMClient(chain=CHAIN, total_budget=5.0)).chain

    assert led[0].name not in KNOWN_DEAD
    names = [provider.name for provider in led]
    assert names.index(CLINE_GLM_5_3_FLASH.name) > len(led) // 2


def test_a_bounded_client_limits_every_tier_and_the_whole_call():
    from labpilot.api.chains import bounded

    client = LLMClient(chain=CHAIN, total_budget=900.0)

    limited = bounded(client, read=40.0, budget=150.0, retries=0)

    assert {provider.timeout for provider in limited.chain} == {(10.0, 40.0)}
    assert (limited.total_budget, limited.max_retries_per_tier) == (150.0, 0)
    assert [p.name for p in limited.chain] == [p.name for p in CHAIN]
    assert client.total_budget == 900.0
    assert bounded("client", read=1.0, budget=1.0) == "client"


def test_a_dead_tier_is_never_moved_to_the_front():
    from labpilot.llm import CLINE_GLM_5_3_FLASH, KNOWN_DEAD

    led = lead_with(CHAIN, [CLINE_GLM_5_3_FLASH.model])

    assert led[0].name not in KNOWN_DEAD
    assert [p.name for p in led] == [p.name for p in CHAIN]

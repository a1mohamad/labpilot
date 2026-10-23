from types import SimpleNamespace

from labpilot.api.chains import CLAIMS_FIRST, for_claims, lead_with
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

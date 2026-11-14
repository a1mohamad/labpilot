from labpilot.llm import CHAIN, tiers


def test_the_tiers_namespace_is_the_registry():
    assert tiers.CHAIN is CHAIN


def test_a_tier_the_front_door_does_not_export_is_reached_through_the_namespace():
    assert tiers.QWEN_3_8_27B_GROQ.model
    assert tiers.QWEN_3_8_27B_GROQ.name in {p.name for p in CHAIN}

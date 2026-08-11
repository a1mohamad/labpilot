from labpilot.llm import CHAIN


def test_chain_tiers_are_sequential_from_one():
    assert [provider.tier for provider in CHAIN] == list(range(1, len(CHAIN) + 1))


def test_no_two_adjacent_tiers_share_an_api_key():
    pools = [provider.api_key_env for provider in CHAIN]
    adjacent = list(zip(pools, pools[1:], strict=False))

    assert all(first != second for first, second in adjacent), pools

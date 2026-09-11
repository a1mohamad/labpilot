from pathlib import Path

import pytest

from labpilot.embed import MIGRATION
from labpilot.ingest.defaults import MAX_CHUNK_TOKENS

ROOT = Path(__file__).resolve().parents[3]
ENV_EXAMPLE = ROOT / ".env.example"
SMOKE_WORKFLOW = ROOT / ".github" / "workflows" / "smoke.yaml"


def required_env() -> set[str]:
    names = {embedder.api_key_env for embedder in MIGRATION}
    names |= {embedder.account_env for embedder in MIGRATION if embedder.account_env}
    return names


def test_every_embedder_env_var_is_documented_in_env_example():
    documented = ENV_EXAMPLE.read_text(encoding="utf-8")

    missing = sorted(name for name in required_env() if name not in documented)

    assert not missing, missing


def test_every_embedder_env_var_is_mapped_in_the_smoke_workflow():
    workflow = SMOKE_WORKFLOW.read_text(encoding="utf-8")

    missing = sorted(
        name
        for name in required_env()
        if f"{name}: ${{{{ secrets.{name} }}}}" not in workflow
    )

    assert not missing, missing


def test_no_two_embedders_are_the_same_model_on_the_same_key():
    """A model MAY repeat across accounts, and only across accounts.

    Repeating it on one key is dead weight - the same bucket, so the second
    entry is spent the moment the first is. Repeating it on a SECOND account
    is the one true fallback this list has: identical model, identical
    vectors, so a corpus half-ingested on key 1 can be finished on key 2 and
    still be one coherent space. Every other step in MIGRATION means
    re-embedding everything.
    """
    pairs = [(embedder.model, embedder.api_key_env) for embedder in MIGRATION]

    assert len(pairs) == len(set(pairs)), pairs


@pytest.mark.parametrize("model", ["gemini-embedding-001", "gemini-embedding-2"])
def test_every_google_embedder_has_a_second_account_behind_it(model):
    """The second key is the only fallback that does not force a re-embed, so
    losing it turns a Google outage into re-ingesting every corpus."""
    keys = {e.api_key_env for e in MIGRATION if e.model == model}

    assert keys == {"GOOGLE_API_KEY", "GOOGLE_API_KEY_2"}, keys


def test_the_newer_google_embedder_outranks_the_older_one():
    """Ranked on GOOGLE's evidence, not ours - and that is the exception.

    `gemini-embedding-2` is version 2 against version 001 in Google's own model
    listing, MTEB mean-by-task 69.9 against 68.32, and accepts 8,192 input
    tokens against 2,048. It has NEVER been scored on our fixture, which makes
    it the only entry in MIGRATION ordered by somebody else's benchmark.

    The test exists so that stays deliberate: slice 8 owes this model a score,
    and if it loses on our data the order has to move back.
    """
    order = [e.model for e in MIGRATION]

    assert order.index("gemini-embedding-2") < order.index("gemini-embedding-001")


def test_the_newer_google_embedder_lifts_the_chunk_cap_ceiling():
    """001's 2,048-token limit meant our 510-token chunk cap could never rise.

    CLAUDE.md recorded that as permanent - "it removes the option of ever
    raising that cap". embedding-2 accepts 8,192, so the constraint is gone,
    and this is what would notice if a future edit quietly reinstated it.
    """
    newer = next(e for e in MIGRATION if e.model == "gemini-embedding-2")
    older = next(e for e in MIGRATION if e.model == "gemini-embedding-001")

    assert newer.max_input_tokens > older.max_input_tokens
    assert newer.max_input_tokens >= 4 * MAX_CHUNK_TOKENS


def test_the_migration_spans_more_than_one_platform():
    platforms = {embedder.api_key_env for embedder in MIGRATION}

    assert len(platforms) > 1, "one dead provider would stop all ingest"


def test_the_two_best_embedders_do_not_share_a_platform():
    # A migration is not a fallback: recovering means re-embedding the whole
    # corpus by hand. If the top two die together, that manual step is forced
    # onto a model that is unmeasured, blocked, or paid out of the reranker's
    # own monthly bucket.
    first, second = MIGRATION[0], MIGRATION[1]

    assert first.api_key_env != second.api_key_env, (
        f"{first.name} and {second.name} would fail together"
    )


def test_no_single_platform_can_empty_the_migration():
    for platform in {embedder.api_key_env for embedder in MIGRATION}:
        survivors = [e for e in MIGRATION if e.api_key_env != platform]

        assert survivors, f"losing {platform} would leave nothing to embed with"

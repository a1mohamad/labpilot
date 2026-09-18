import math
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


def test_the_measured_google_embedder_outranks_the_one_google_prefers():
    """MEASURED AND MOVED, 2026-09-18 - this test used to assert the reverse.

    `gemini-embedding-2` sat above 001 on GOOGLE's evidence rather than ours:
    version 2 against version 001 in the model listing, MTEB mean-by-task 69.9
    against 68.32. It was the only entry in MIGRATION ordered by somebody
    else's benchmark, and the previous version of this test existed to keep
    that deliberate - "slice 8 owes this model a score, and if it loses on our
    data the order has to move back".

    Slice 8 scored it and it LOST, on 3 of the 4 corpora where both ran:
    websocket 0.530 vs 0.364, requests 0.650 vs 0.559, geo 0.493 vs 0.341, and
    only quora the other way at 0.674 vs 0.702.

    So the order moved back, which is what MIGRATION's own rule requires: order
    by MEASURED recall. The test moved with it, and still guards the same
    property - that this pair's order is a decision somebody took on evidence,
    not an accident of edit history. v2's G21 reached the same verdict and the
    code was never changed, which is exactly the failure this pins.
    """
    order = [e.model for e in MIGRATION]

    assert order.index("gemini-embedding-001") < order.index("gemini-embedding-2")


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


def test_a_model_that_cannot_finish_today_is_skipped_not_attempted():
    """Google counts one TEXT as one request, so a big corpus is impossible.

    ADDED 2026-09-18 after the gap was found by running into it. `Rate` modelled
    a token budget and a call budget, and Google's real limit is neither: a
    96-text batchEmbedContents call spends 96 of the day's 1,000. So
    `embedding_minutes` reported a plausible 163 minutes for a 20,000-chunk
    Google ingest when the truth is twenty DAYS, the walk chose Google, started,
    and died on a 429 part way through. Measured twice that day - a warm failed
    on its SECOND corpus, and 001 exhausted after 943 chunks.

    An inf here is what removes a model from the walk, so this is the
    difference between refusing before the first call and failing half way
    through an ingest that cannot be resumed.
    """
    google = next(e for e in MIGRATION if e.model == "gemini-embedding-001")
    budget = google.rate.daily_text_budget

    assert budget, "Google's per-TEXT daily budget must be modelled"
    assert google.embedding_minutes(tokens=budget * 236, chunks=budget) < math.inf
    assert (
        google.embedding_minutes(tokens=(budget + 1) * 236, chunks=budget + 1)
        == math.inf
    )


def test_the_migration_is_ordered_by_measured_strength():
    """mistral-embed loses to every embedder it has been compared with.

    Measured on the 20-corpus zoo: codestral 0.634 > gemini-001 0.602 > cohere
    0.593 > gemini-2 0.563 > mistral 0.511. Head to head, mistral wins 1 of 7
    against gemini-001, 3 of 13 against cohere, 4 of 11 against gemini-2.

    It sat THIRD until 2026-09-18, above three better models, in a tuple whose
    own comment called it "the strength order". It stays in the list because a
    walk must not dead-end - it is the only model that can ingest 10,000 chunks
    quickly - but it belongs at the back.
    """
    order = [e.model for e in MIGRATION]

    assert order.index("codestral-embed") < order.index("mistral-embed")
    assert order.index("gemini-embedding-001") < order.index("mistral-embed")
    assert order.index("embed-v4.0") < order.index("mistral-embed")

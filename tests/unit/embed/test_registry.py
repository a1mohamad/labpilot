from pathlib import Path

from labpilot.embed import MIGRATION

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


def test_embedder_models_are_unique():
    models = [embedder.model for embedder in MIGRATION]

    assert len(models) == len(set(models))


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

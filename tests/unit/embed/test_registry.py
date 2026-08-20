from pathlib import Path

from labpilot.embed import MIGRATION

ROOT = Path(__file__).resolve().parents[3]
ENV_EXAMPLE = ROOT / ".env.example"
SMOKE_WORKFLOW = ROOT / ".github" / "workflows" / "smoke.yaml"


def test_every_embedder_env_var_is_documented_in_env_example():
    documented = ENV_EXAMPLE.read_text(encoding="utf-8")

    missing = sorted(
        embedder.api_key_env
        for embedder in MIGRATION
        if embedder.api_key_env not in documented
    )

    assert not missing, missing


def test_every_embedder_env_var_is_mapped_in_the_smoke_workflow():
    workflow = SMOKE_WORKFLOW.read_text(encoding="utf-8")

    missing = sorted(
        name
        for name in {embedder.api_key_env for embedder in MIGRATION}
        if f"{name}: ${{{{ secrets.{name} }}}}" not in workflow
    )

    assert not missing, missing


def test_embedder_models_are_unique():
    models = [embedder.model for embedder in MIGRATION]

    assert len(models) == len(set(models))

from __future__ import annotations

import pytest

from labpilot.embed import MAX_BATCH_SIZE, MIGRATION
from labpilot.embed.base import HTTPEmbedder
from labpilot.embed.errors import EmbeddingError

CASES = pytest.mark.parametrize(
    "embedder", MIGRATION, ids=lambda embedder: embedder.model
)


@CASES
def test_every_embedder_shares_the_one_http_template(embedder):
    assert isinstance(embedder, HTTPEmbedder)


@CASES
def test_every_embedder_rejects_an_empty_list_as_a_caller_bug(embedder):
    with pytest.raises(ValueError, match="must not be empty"):
        embedder.embed([])


@CASES
def test_every_embedder_rejects_a_blank_text_as_a_caller_bug(embedder):
    with pytest.raises(ValueError, match="must not be blank"):
        embedder.embed(["good", "   "])


@CASES
def test_every_embedder_rejects_more_than_the_batch_limit(embedder):
    assert MAX_BATCH_SIZE < 97  # premise: fails loudly if the cap is ever raised

    with pytest.raises(ValueError, match="batch limit"):
        embedder.embed(["x"] * 97)


@CASES
def test_every_embedder_refuses_without_credentials_and_costs_no_request(
    embedder, monkeypatch
):
    monkeypatch.delenv(embedder.api_key_env, raising=False)
    if embedder.account_env:
        monkeypatch.delenv(embedder.account_env, raising=False)

    with pytest.raises(EmbeddingError, match="is not set"):
        embedder.embed(["hello"])

"""The worker refuses an embedding provider it does not know.

Read as the default it would ingest with hash vectors (no meaning) into a
collection the API searches with real ones, which no later check catches.
"""

from __future__ import annotations

import pytest

from dw_agent_runtime.registry import ConfigError
from dw_worker.composition import build_embeddings
from dw_worker.settings import WorkerSettings

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("provider", ["tei", "openai"])
def test_an_unknown_embedding_provider_is_refused_not_hashed(provider: str) -> None:
    with pytest.raises(ConfigError) as raised:
        build_embeddings(WorkerSettings(embedding_provider=provider))
    assert raised.value.details == {"embedding_provider": provider}


def test_hash_embeddings_still_build_locally() -> None:
    from dw_knowledge.adapters.hash_embedding import HashEmbeddingAdapter

    assert isinstance(
        build_embeddings(WorkerSettings(embedding_provider="hash")), HashEmbeddingAdapter
    )


def test_a_blank_env_line_means_the_default_as_it_does_in_compose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DW_WORKER_EMBEDDING_PROVIDER", "")
    assert WorkerSettings().embedding_provider == "hash"

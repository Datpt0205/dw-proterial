"""Retrieval stack: embeddings, reranking, vector index.

Each is chosen by configuration and every choice has a working fallback, so a
developer gets a running retrieval path with no external services while a
deployment gets the real one. The fallbacks are not production components and
say so — ``validate_for_profile`` refuses them outside local development.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from dw_agent_runtime.model.profiles import ModelProfileRegistry
from dw_agent_runtime.registry import ConfigError
from dw_api.bootstrap.models import checked_base_url
from dw_api.settings import ApiSettings
from dw_knowledge.ports import EmbeddingPort, RerankPort, VectorIndexPort


def build_embeddings(settings: ApiSettings, profiles: ModelProfileRegistry) -> EmbeddingPort:
    if settings.embedding_provider == "openai_compatible":
        from dw_knowledge.adapters.openai_embedding import OpenAICompatibleEmbeddingAdapter

        # Retrieval must embed the query exactly as ingestion embedded the
        # chunks, so both sides read the same profile route rather than two
        # settings that can drift apart.
        route = profiles.resolve(settings.model_profile).embedding
        if route is None or route.dimensions is None:
            raise ConfigError(
                "model profile declares no embedding route",
                details={"profile_id": settings.model_profile},
            )
        if not settings.openai_base_url or not settings.openai_api_key:
            raise ConfigError(
                "openai_compatible embeddings need OPENAI_BASE_URL and OPENAI_API_KEY"
            )
        return OpenAICompatibleEmbeddingAdapter(
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            model=route.model,
            _dimension=route.dimensions,
            timeout=float(route.timeout_seconds),
        )
    if settings.embedding_provider == "hash":
        # Deterministic hashing. Retrieval "works" and returns stable neighbours,
        # so the plumbing is testable, but the vectors carry no meaning.
        from dw_knowledge.adapters.hash_embedding import HashEmbeddingAdapter

        return HashEmbeddingAdapter()
    # A provider this build does not know (a retired one, a typo) must not
    # quietly become the meaningless hash vectors.
    raise ConfigError(
        "unknown embedding provider; use 'openai_compatible' or 'hash'",
        details={"embedding_provider": settings.embedding_provider},
    )


def build_reranker(settings: ApiSettings) -> RerankPort | None:
    """None means the vector order stands, which is what "none" asks for."""
    if settings.rerank_provider == "none":
        return None
    if settings.rerank_provider == "cohere_compatible":
        if not settings.rerank_base_url or not settings.rerank_api_key:
            raise ConfigError(
                "cohere_compatible reranking needs DW_API_RERANK_BASE_URL and DW_API_RERANK_API_KEY"
            )
        # Checked here, not on the first search: a URL the client cannot use
        # fails every call, and the gateway would turn each failure into a
        # quietly unranked search with only a log line to show for it.
        if settings.is_deployed and urlsplit(settings.rerank_base_url).scheme != "https":
            raise ConfigError(
                "a deployed reranker is reached over https; the key travels in a header",
                details={"scheme": urlsplit(settings.rerank_base_url).scheme or "<none>"},
            )
        base_url = checked_base_url(settings, settings.rerank_base_url)
        from dw_knowledge.adapters.cohere_rerank import CohereCompatibleRerankAdapter

        return CohereCompatibleRerankAdapter(
            base_url=base_url,
            api_key=settings.rerank_api_key,
            model=settings.rerank_model,
            timeout=settings.rerank_timeout_seconds,
        )
    raise ConfigError(
        "unknown rerank provider; use 'cohere_compatible' or 'none'",
        details={"rerank_provider": settings.rerank_provider},
    )


def build_vector_index(settings: ApiSettings) -> VectorIndexPort:
    if settings.qdrant_url:
        from qdrant_client import AsyncQdrantClient

        from dw_knowledge.adapters.qdrant_index import QdrantVectorIndexAdapter

        return QdrantVectorIndexAdapter(
            client=AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key),
            collection=settings.qdrant_collection,
        )
    # In-memory, and therefore never durable: the index dies with the process.
    from dw_knowledge.adapters.memory_index import InMemoryVectorIndexAdapter

    return InMemoryVectorIndexAdapter()

"""Retrieval stack: embeddings, reranking, vector index.

Each is chosen by configuration and every choice has a working fallback, so a
developer gets a running retrieval path with no external services while a
deployment gets the real one. The fallbacks are not production components and
say so — ``validate_for_profile`` refuses them outside local development.
"""

from __future__ import annotations

from dw_agent_runtime.model.profiles import ModelProfileRegistry
from dw_agent_runtime.registry import ConfigError
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
    if settings.embedding_provider == "tei" and settings.embed_url:
        from dw_knowledge.adapters.tei_embedding import TeiEmbeddingAdapter

        return TeiEmbeddingAdapter(base_url=settings.embed_url, _dimension=settings.embed_dimension)
    # Deterministic hashing. Retrieval "works" and returns stable neighbours, so
    # the plumbing is testable, but the vectors carry no meaning.
    from dw_knowledge.adapters.hash_embedding import HashEmbeddingAdapter

    return HashEmbeddingAdapter()


def build_reranker(settings: ApiSettings) -> RerankPort | None:
    if settings.embedding_provider == "tei" and settings.rerank_url:
        from dw_knowledge.adapters.tei_rerank import TeiRerankAdapter

        return TeiRerankAdapter(base_url=settings.rerank_url)
    return None


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

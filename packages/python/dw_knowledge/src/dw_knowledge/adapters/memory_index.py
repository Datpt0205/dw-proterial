"""In-memory vector index (working adapter for local/test without Qdrant).

Implements the SAME trusted-filter semantics as the Qdrant adapter — tenant,
workspace, classification, ACL and domain constraints all apply — and the same
hybrid ranking: cosine and BM25 under that filter, with the BM25 statistics
taken from what the filter admits, fused by reciprocal rank
(`dw_knowledge.hybrid`). The retrieval eval in CI's smoke runs against this
index, so a ranking that differs from Qdrant's would make the eval measure
something nobody serves. Not durable: suitable only for tests and infra-less
local runs (never production).
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from dw_knowledge.contracts import SHARED_DOMAIN
from dw_knowledge.hybrid import (
    bm25_scores,
    prefetch_limit,
    reciprocal_rank_fusion,
    relevance_from_fused,
)
from dw_knowledge.ports import IndexableChunk, TrustedSearchFilter, VectorHit


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass
class InMemoryVectorIndexAdapter:
    """Implements ``VectorIndexPort`` in process memory."""

    _chunks: dict[str, IndexableChunk] = field(default_factory=dict)
    _tombstoned: set[uuid.UUID] = field(default_factory=set)

    async def ensure_ready(self, vector_dimension: int, embedding_model: str) -> None:
        return None

    async def upsert(self, chunks: Sequence[IndexableChunk]) -> None:
        for chunk in chunks:
            self._chunks[str(chunk.chunk_id)] = chunk
            self._tombstoned.discard(chunk.document_id)  # re-index reactivates

    async def delete_document(self, document_id: uuid.UUID) -> None:
        for key in [k for k, c in self._chunks.items() if c.document_id == document_id]:
            del self._chunks[key]
        self._tombstoned.discard(document_id)

    async def tombstone_document(
        self, document_id: uuid.UUID, *, tenant_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> None:
        # As Qdrant's filter does: only that tenant's and workspace's points.
        if any(
            c.document_id == document_id
            and c.tenant_id == tenant_id
            and c.workspace_id == workspace_id
            for c in self._chunks.values()
        ):
            self._tombstoned.add(document_id)

    async def delete_by_tenant(self, tenant_id: uuid.UUID) -> None:
        for key in [k for k, c in self._chunks.items() if c.tenant_id == tenant_id]:
            del self._chunks[key]

    async def search(
        self,
        vector: Sequence[float],
        trusted_filter: TrustedSearchFilter,
        top_k: int,
        extra_filters: Sequence[tuple[str, str]] = (),
        document_ids: Sequence[uuid.UUID] = (),
        *,
        text: str,
    ) -> list[VectorHit]:
        visible = [c for c in self._chunks.values() if self._admits(c, trusted_filter)]
        wanted = set(document_ids)
        # Applied as a conjunction: a business filter can only ever drop a
        # chunk the trusted checks would have allowed.
        retrievable = {
            str(c.chunk_id): c
            for c in visible
            if all(dict(c.extra_payload).get(key) == value for key, value in extra_filters)
            and (not wanted or c.document_id in wanted)
        }
        depth = prefetch_limit(top_k)
        dense = sorted(retrievable, key=lambda key: -_cosine(vector, retrievable[key].vector))
        # Statistics over everything the trusted filter admits (the corpus the
        # Qdrant adapter names), ranks over what the narrowing leaves.
        lexical = bm25_scores(text, [(str(c.chunk_id), c.content) for c in visible])
        words = sorted(
            (key for key in lexical if key in retrievable), key=lambda key: -lexical[key]
        )
        fused = reciprocal_rank_fusion([dense[:depth], words[:depth]])
        return [
            VectorHit(
                chunk_id=retrievable[str(key)].chunk_id,
                document_id=retrievable[str(key)].document_id,
                score=relevance_from_fused(score),
                content=retrievable[str(key)].content,
                classification=retrievable[str(key)].classification,
                source_version=retrievable[str(key)].source_version,
                provenance_hash=retrievable[str(key)].provenance_hash,
            )
            for key, score in fused[:top_k]
        ]

    def _admits(self, chunk: IndexableChunk, trusted_filter: TrustedSearchFilter) -> bool:
        """The trusted filter alone, as the Qdrant adapter builds it."""
        if chunk.document_id in self._tombstoned:
            return False
        # Own tenant+workspace OR a cross-tenant global (legal) document.
        own = (
            chunk.tenant_id == trusted_filter.tenant_id
            and chunk.workspace_id == trusted_filter.workspace_id
        )
        return (
            (own or chunk.scope == "global")
            and chunk.classification in trusted_filter.allowed_classifications
            and bool(set(chunk.acl_principals) & set(trusted_filter.acl_principals))
            and chunk.domain in (trusted_filter.domain, SHARED_DOMAIN)
        )

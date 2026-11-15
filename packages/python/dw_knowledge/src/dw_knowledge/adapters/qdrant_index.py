"""Qdrant vector index adapter (payload multitenancy + tenant index).

Search is impossible without a TrustedSearchFilter — the filter argument is not
optional and the tenant/workspace conditions are always appended here from it,
never from caller-supplied values.

Search is hybrid (Sales ticket 45): the dense vector and BM25 over the chunk
text, each under the same filter, fused by reciprocal rank in one Query API
call. The BM25 statistics are scoped to what that filter admits, because by
default Qdrant computes them over the whole shard, and there another tenant's
words move this tenant's scores (measured on 1.20.1, 2026-11-15: a tenant's
score for one query fell from 2.95 to 1.76 when another tenant added 80 points,
and stayed 2.95 with the corpus scoped). A score that moves with another
tenant's text is also a probe of what that text contains.

The name readers and writers use is an alias. Behind it is a collection named
by the embedding model that filled it (`<alias>__<model>__<build>`), so a
process embedding with another model refuses to search it, and a rebuild
(`scripts/knowledge_reindex.py`) fills a new collection and moves the alias in
one atomic call.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from http import HTTPStatus

from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

from dw_kernel.errors import InfrastructureError
from dw_knowledge.contracts import DEFAULT_COLLECTION, SHARED_DOMAIN
from dw_knowledge.hybrid import RRF_K, prefetch_limit, relevance_from_fused
from dw_knowledge.ports import IndexableChunk, TrustedSearchFilter, VectorHit

__all__ = ["DEFAULT_COLLECTION", "QdrantVectorIndexAdapter", "build_prefix"]

# account_id is indexed alongside the security fields because intel narrows
# nearly every search to one account; an unindexed payload filter costs a full
# scan of the tenant's points.
_KEYWORD_PAYLOAD_INDEXES = (
    "workspace_id",
    "domain",
    "classification",
    "acl_principals",
    "account_id",
    # Every attachment query narrows by it, so an unindexed one would scan the
    # tenant's whole point set on each question about a file.
    "attachment_scope",
    # A search that names documents narrows by it before top-k, as do the
    # per-document delete and tombstone.
    "source_document_id",
    # Every search ORs the caller's own points with global ones by it.
    "scope",
)

# The payload field BM25 ranks: the chunk text, already stored for citation.
_TEXT_FIELD = "content"
# The `word` tokenizer, not `multilingual`: measured on 1.20.1 (2026-11-15),
# `multilingual` drops tokens made only of digits, so `PO-2026-0457` indexed as
# `po` alone and every PO number matched every other. `word` keeps `2026` and
# `0457`; Vietnamese is space-delimited, and Japanese, which `word` leaves as
# whole runs, is the dense leg's to find.
_TEXT_INDEX = models.TextIndexParams(
    type=models.TextIndexType.TEXT,
    tokenizer=models.TokenizerType.WORD,
    lowercase=True,
    scoring=True,
)

# The first collection behind an alias has a fixed build name, so two processes
# starting at once create the same collection rather than two: creating an
# alias that exists silently repoints it (measured, 1.20.1), and two first
# builds would leave one process writing where nobody reads.
FIRST_BUILD = "1"


def build_prefix(alias: str, embedding_model: str) -> str:
    """Every collection built for this alias from this model starts with this."""
    model = re.sub(r"[^a-z0-9]+", "_", embedding_model.lower()).strip("_")
    return f"{alias}__{model}__"


@dataclass
class QdrantVectorIndexAdapter:
    """Implements ``VectorIndexPort``."""

    client: AsyncQdrantClient
    # The alias every read and write goes through (see the module docstring).
    collection: str = DEFAULT_COLLECTION

    async def ensure_ready(self, vector_dimension: int, embedding_model: str) -> None:
        """Serve a collection for this width and model, then reconcile its indexes.

        A mismatch raises instead of recreating. Recreating drops every
        tenant's vectors, and it would be triggered by nothing more than a
        config value: during a rolling deploy, two processes reading different
        settings delete each other's collection in a loop rather than in a
        window. Changing the embedding model is a rebuild into a new collection
        and a move of the alias (`scripts/knowledge_reindex.py`), not a side
        effect of a restart.

        A collection that holds the alias's own name was made before aliases
        and says nothing about its model; only its width is checked.
        """
        served = await self._served()
        if served is None:
            served = await self.create_build(vector_dimension, embedding_model, FIRST_BUILD)
            await self._alias(served)
        existing = await self._dimension_of(served)
        if existing != vector_dimension:
            raise InfrastructureError(
                "Qdrant collection was built for a different embedding width",
                details={
                    "collection": self.collection,
                    "collection_dimension": existing,
                    "embedding_dimension": vector_dimension,
                },
            )
        if served != self.collection and not served.startswith(
            build_prefix(self.collection, embedding_model)
        ):
            raise InfrastructureError(
                "Qdrant collection was built by a different embedding model",
                details={
                    "collection": self.collection,
                    "served": served,
                    "embedding_model": embedding_model,
                },
            )
        # Reconciled on every call, not only after a create: a payload index
        # added to this adapter later would otherwise never exist on a
        # collection that already does, and an unindexed keyword filter is a
        # full scan of the tenant's points. Qdrant builds a new text index from
        # the payload it already holds.
        await self._ensure_payload_indexes(served)

    async def create_build(self, vector_dimension: int, embedding_model: str, build: str) -> str:
        """Create a collection for this alias and model, indexed; returns its name.

        Not served until `serve` points the alias at it, so a rebuild fills it
        while searches still read the one before.
        """
        name = f"{build_prefix(self.collection, embedding_model)}{build}"
        if not await self._exists(name):
            await self._create_collection(name, vector_dimension)
        await self._ensure_payload_indexes(name)
        return name

    async def serve(self, build: str) -> str | None:
        """Point the alias at `build` in one atomic call; returns what it served."""
        previous = await self._served()
        if previous == self.collection:
            raise InfrastructureError(
                "a collection holds the alias name; delete it, then serve the build",
                details={"collection": self.collection, "build": build},
            )
        await self._alias(build)
        return previous

    async def _served(self) -> str | None:
        """The collection behind the name, or None when nothing answers to it."""
        try:
            for alias in (await self.client.get_aliases()).aliases:
                if alias.alias_name == self.collection:
                    return str(alias.collection_name)
            exists = await self.client.collection_exists(self.collection)
        except Exception as exc:
            raise InfrastructureError(
                "failed to read the Qdrant collection",
                details={"collection": self.collection, "error": type(exc).__name__},
            ) from exc
        return self.collection if exists else None

    async def _exists(self, name: str) -> bool:
        try:
            return bool(await self.client.collection_exists(name))
        except Exception as exc:
            raise InfrastructureError(
                "failed to read the Qdrant collection",
                details={"collection": name, "error": type(exc).__name__},
            ) from exc

    async def _alias(self, build: str) -> None:
        """Create or move the alias; Qdrant applies it atomically."""
        try:
            await self.client.update_collection_aliases(
                change_aliases_operations=[
                    models.CreateAliasOperation(
                        create_alias=models.CreateAlias(
                            collection_name=build, alias_name=self.collection
                        )
                    )
                ]
            )
        except Exception as exc:
            raise InfrastructureError(
                "failed to point the Qdrant alias",
                details={"collection": self.collection, "error": type(exc).__name__},
            ) from exc

    async def _dimension_of(self, name: str) -> int | None:
        try:
            info = await self.client.get_collection(name)
            size = getattr(info.config.params.vectors, "size", None)
        except Exception as exc:
            raise InfrastructureError(
                "failed to read the Qdrant collection",
                details={"collection": name, "error": type(exc).__name__},
            ) from exc
        return int(size) if size is not None else None

    async def _create_collection(self, name: str, vector_dimension: int) -> None:
        try:
            await self.client.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=vector_dimension, distance=models.Distance.COSINE
                ),
                # Scalar quantization keeps RAM/latency low on modest hardware.
                quantization_config=models.ScalarQuantization(
                    scalar=models.ScalarQuantizationConfig(
                        type=models.ScalarType.INT8, always_ram=True
                    )
                ),
            )
        except Exception as exc:
            # Another process starting at the same moment created it first.
            if await self._exists(name):
                return
            raise InfrastructureError(
                "failed to create the Qdrant collection",
                details={"collection": name, "error": type(exc).__name__},
            ) from exc

    async def _ensure_payload_indexes(self, name: str) -> None:
        """Idempotent - Qdrant treats a repeated create as an update."""
        try:
            await self.client.create_payload_index(
                name,
                field_name="tenant_id",
                field_schema=models.KeywordIndexParams(
                    type=models.KeywordIndexType.KEYWORD, is_tenant=True
                ),
            )
            for field in _KEYWORD_PAYLOAD_INDEXES:
                await self.client.create_payload_index(
                    name,
                    field_name=field,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
            await self.client.create_payload_index(
                name,
                field_name="is_deleted",
                field_schema=models.PayloadSchemaType.BOOL,
            )
            await self.client.create_payload_index(
                name, field_name=_TEXT_FIELD, field_schema=_TEXT_INDEX
            )
        except Exception as exc:
            raise InfrastructureError(
                "failed to prepare Qdrant payload indexes",
                details={"collection": name, "error": type(exc).__name__},
            ) from exc

    async def upsert(self, chunks: Sequence[IndexableChunk]) -> None:
        if not chunks:
            return
        points = [
            models.PointStruct(
                id=str(chunk.chunk_id),
                vector=list(chunk.vector),
                payload={
                    # Business metadata FIRST so the trusted fields below always
                    # win a key collision. The ingest command also rejects
                    # reserved keys, but a payload built by dict order cannot be
                    # made unsafe by a future caller that skips that path.
                    **dict(chunk.extra_payload),
                    "tenant_id": str(chunk.tenant_id),
                    "workspace_id": str(chunk.workspace_id),
                    "domain": chunk.domain,
                    "resource_id": str(chunk.document_id),
                    "source_document_id": str(chunk.document_id),
                    "chunk_id": str(chunk.chunk_id),
                    "acl_principals": list(chunk.acl_principals),
                    "classification": chunk.classification,
                    "source_version": chunk.source_version,
                    "index_version": chunk.index_version,
                    "provenance_hash": chunk.provenance_hash,
                    "content": chunk.content,
                    "section_path": chunk.section_path,
                    "seq": chunk.seq,
                    "scope": chunk.scope,
                    "is_deleted": False,
                },
            )
            for chunk in chunks
        ]
        try:
            await self.client.upsert(self.collection, points=points, wait=True)
        except Exception as exc:
            raise InfrastructureError(
                "failed to upsert vectors", details={"error": type(exc).__name__}
            ) from exc

    def _document_filter(self, document_id: uuid.UUID) -> models.Filter:
        return models.Filter(
            must=[
                models.FieldCondition(
                    key="source_document_id",
                    match=models.MatchValue(value=str(document_id)),
                )
            ]
        )

    async def delete_document(self, document_id: uuid.UUID) -> None:
        try:
            await self.client.delete(
                self.collection,
                points_selector=models.FilterSelector(filter=self._document_filter(document_id)),
                wait=True,
            )
        except Exception as exc:
            raise InfrastructureError(
                "failed to delete document vectors", details={"error": type(exc).__name__}
            ) from exc

    def _tenant_filter(self, tenant_id: uuid.UUID) -> models.Filter:
        return models.Filter(
            must=[
                models.FieldCondition(
                    key="tenant_id",
                    match=models.MatchValue(value=str(tenant_id)),
                )
            ]
        )

    async def delete_by_tenant(self, tenant_id: uuid.UUID) -> None:
        try:
            await self.client.delete(
                self.collection,
                points_selector=models.FilterSelector(filter=self._tenant_filter(tenant_id)),
                wait=True,
            )
        except Exception as exc:
            raise InfrastructureError(
                "failed to delete tenant vectors", details={"error": type(exc).__name__}
            ) from exc

    async def tombstone_document(
        self, document_id: uuid.UUID, *, tenant_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> None:
        owned = models.Filter(
            must=[
                models.FieldCondition(
                    key="source_document_id", match=models.MatchValue(value=str(document_id))
                ),
                models.FieldCondition(
                    key="tenant_id", match=models.MatchValue(value=str(tenant_id))
                ),
                models.FieldCondition(
                    key="workspace_id", match=models.MatchValue(value=str(workspace_id))
                ),
            ]
        )
        try:
            await self.client.set_payload(
                self.collection,
                payload={"is_deleted": True},
                points=models.FilterSelector(filter=owned),
                wait=True,
            )
        except Exception as exc:
            raise InfrastructureError(
                "failed to tombstone document vectors", details={"error": type(exc).__name__}
            ) from exc

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
        # Business narrowing joins the same `must` list, so it can only ever
        # intersect with the mandatory constraints - never replace one.
        narrowing = [
            models.FieldCondition(key=key, match=models.MatchValue(value=value))
            for key, value in extra_filters
        ]
        # Asking for particular documents is the same kind of narrowing, and it
        # has to happen here rather than on the hits: `limit` below is applied
        # to whatever this filter admits.
        if document_ids:
            narrowing.append(
                models.FieldCondition(
                    key="source_document_id",
                    match=models.MatchAny(any=[str(d) for d in document_ids]),
                )
            )
        retrieval = _visible(trusted_filter, narrowing)
        # The BM25 statistics: everything this caller may read in this domain,
        # and nothing else. Wider than `retrieval` (narrowing to one document
        # should not make every word in it rare), never wider than the trusted
        # filter, so a score is a function of text the caller could read
        # anyway. Set on the prefetch itself: measured on 1.20.1, an `idf` on
        # the outer query's params does not reach the prefetches.
        corpus = _visible(trusted_filter, [])
        depth = prefetch_limit(top_k)
        try:
            response = await self.client.query_points(
                self.collection,
                # Every leg carries the whole filter: a prefetch without it
                # would rank every tenant's points, and the fusion could only
                # filter what it was handed.
                prefetch=[
                    models.Prefetch(query=list(vector), filter=retrieval, limit=depth),
                    models.Prefetch(
                        query=models.TextQuery(text=text),
                        using=_TEXT_FIELD,
                        filter=retrieval,
                        limit=depth,
                        params=models.SearchParams(idf=models.IdfCorpusParams(corpus=corpus)),
                    ),
                ],
                query=models.RrfQuery(rrf=models.Rrf(k=RRF_K)),
                query_filter=retrieval,
                limit=top_k,
                with_payload=True,
            )
        except Exception as exc:
            if await self._is_missing_collection(exc):
                # Nothing has been indexed here yet. That is an empty result,
                # not a broken system: on a fresh install the first question
                # asked before the first upload would otherwise fail the whole
                # turn, because InfrastructureError is not an error the agent is
                # allowed to answer for.
                return []
            raise InfrastructureError(
                "vector search failed", details={"error": type(exc).__name__}
            ) from exc

        hits: list[VectorHit] = []
        for point in response.points:
            payload = point.payload or {}
            hits.append(
                VectorHit(
                    chunk_id=_uuid(payload.get("chunk_id")),
                    document_id=_uuid(payload.get("source_document_id")),
                    score=relevance_from_fused(float(point.score)),
                    content=str(payload.get("content", "")),
                    classification=str(payload.get("classification", "internal")),
                    source_version=str(payload.get("source_version", "1")),
                    provenance_hash=str(payload.get("provenance_hash", "")),
                )
            )
        return hits

    async def _is_missing_collection(self, exc: Exception) -> bool:
        """Whether a failed search failed only because the collection is absent.

        Only the client's typed 404 qualifies, and only once Qdrant confirms
        the collection does not exist: a proxy or a wrong base path also
        answers 404, and every other failure (a timeout, a refused key, a
        malformed filter) read as "nothing there" would reach a person as "no
        evidence" when it is a broken system (pinned qdrant-client 1.14.3
        against Qdrant 1.13.4, measured 2026-11-13: an unknown collection
        raises `UnexpectedResponse` with `status_code` 404; a dead server
        raises `ResponseHandlingException`, which has none).
        """
        if not isinstance(exc, UnexpectedResponse) or exc.status_code != HTTPStatus.NOT_FOUND:
            return False
        try:
            return not await self.client.collection_exists(self.collection)
        except Exception:
            return False


def _visible(
    trusted_filter: TrustedSearchFilter, narrowing: Sequence[models.FieldCondition]
) -> models.Filter:
    """What the trusted filter admits, narrowed further by `narrowing`.

    Mandatory constraints come EXCLUSIVELY from the trusted filter.
    """
    conditions: list[models.FieldCondition] = [
        models.FieldCondition(
            key="classification",
            match=models.MatchAny(any=list(trusted_filter.allowed_classifications)),
        ),
        models.FieldCondition(
            key="acl_principals",
            match=models.MatchAny(any=list(trusted_filter.acl_principals)),
        ),
        # Always emitted. Skipping it when the caller asked for "shared" made
        # that value mean "every domain", so the default query read every corpus
        # the tenant owns - including files a user attached to one CRM record.
        models.FieldCondition(
            key="domain",
            match=models.MatchAny(any=sorted({trusted_filter.domain, SHARED_DOMAIN})),
        ),
        *narrowing,
    ]
    # Tenant isolation OR global (legal) scope: a point is visible if it is in
    # the caller's tenant+workspace, OR it is a cross-tenant global document.
    own_tenant = models.Filter(
        must=[
            models.FieldCondition(
                key="tenant_id",
                match=models.MatchValue(value=str(trusted_filter.tenant_id)),
            ),
            models.FieldCondition(
                key="workspace_id",
                match=models.MatchValue(value=str(trusted_filter.workspace_id)),
            ),
        ]
    )
    return models.Filter(
        must=list(conditions),
        # at least one → (own tenant) OR (global)
        should=[
            own_tenant,
            models.FieldCondition(key="scope", match=models.MatchValue(value="global")),
        ],
        # Soft-deleted / superseded points are never retrieved.
        must_not=[models.FieldCondition(key="is_deleted", match=models.MatchValue(value=True))],
    )


def _uuid(value: object) -> uuid.UUID:
    return uuid.UUID(str(value))

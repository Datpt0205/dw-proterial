"""The examples index in Qdrant (Sales ticket 43; `dw_knowledge.examples`).

Its own collection, as memory has its own: a payload flag between one
customer's documents and another's decided cases would be a poor boundary,
and a separate collection costs nothing. The collection is named by the
embedding model that filled it (`<name>__<model>__1`), so a process embedding
with another model starts an empty collection of its own instead of searching
vectors from a different space, and the index lane fills it again.

A point holds a vector and the filter fields, never text: tenant (the tenant
index, `is_tenant`), workspace, step, subject, group and `decided_at` as epoch
seconds (retention deletes by range). Every search carries tenant, workspace
and step from the gateway's `ExampleFilter`.

Two searches per vector, the subject's own cases and the tenant's, go to
Qdrant as one batch: one round trip on the mail's path, as ADR 0015 decision 7
budgets.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from qdrant_client import AsyncQdrantClient, models

from dw_kernel.errors import InfrastructureError
from dw_knowledge.adapters.qdrant_index import FIRST_BUILD, build_prefix
from dw_knowledge.examples import DEFAULT_EXAMPLES_COLLECTION, ExampleFilter, ExamplePoint

__all__ = ["QdrantExampleIndex"]

_KEYWORDS = ("workspace_id", "step", "subject", "group")
_DECIDED = "decided_at"


def _match(key: str, value: str) -> models.FieldCondition:
    return models.FieldCondition(key=key, match=models.MatchValue(value=value))


@dataclass
class QdrantExampleIndex:
    """Implements `ExampleIndexPort`."""

    client: AsyncQdrantClient
    collection: str = DEFAULT_EXAMPLES_COLLECTION
    _name: str | None = field(default=None, init=False)

    @property
    def name(self) -> str:
        if self._name is None:
            raise InfrastructureError(
                "the examples index was not made ready", details={"collection": self.collection}
            )
        return self._name

    async def ensure_ready(self, vector_dimension: int, embedding_model: str) -> None:
        """Create the model's collection and its payload indexes if absent.

        A width that does not match raises rather than recreating: the
        points are every tenant's, and a rebuild is the index lane's to do
        into a new name, never a side effect of a restart."""
        name = f"{build_prefix(self.collection, embedding_model)}{FIRST_BUILD}"
        try:
            if not await self.client.collection_exists(name):
                try:
                    await self.client.create_collection(
                        collection_name=name,
                        vectors_config=models.VectorParams(
                            size=vector_dimension, distance=models.Distance.COSINE
                        ),
                    )
                except Exception:
                    # Another process created it first.
                    if not await self.client.collection_exists(name):
                        raise
            info = await self.client.get_collection(name)
            size = getattr(info.config.params.vectors, "size", None)
            if size is not None and int(size) != vector_dimension:
                raise InfrastructureError(
                    "the examples collection was built for a different width",
                    details={"collection": name, "width": size, "embedding": vector_dimension},
                )
            await self.client.create_payload_index(
                name,
                field_name="tenant_id",
                field_schema=models.KeywordIndexParams(
                    type=models.KeywordIndexType.KEYWORD, is_tenant=True
                ),
            )
            for key in _KEYWORDS:
                await self.client.create_payload_index(
                    name, field_name=key, field_schema=models.PayloadSchemaType.KEYWORD
                )
            await self.client.create_payload_index(
                name, field_name=_DECIDED, field_schema=models.PayloadSchemaType.FLOAT
            )
        except InfrastructureError:
            raise
        except Exception as exc:
            raise InfrastructureError(
                "failed to prepare the examples collection",
                details={"collection": name, "error": type(exc).__name__},
            ) from exc
        self._name = name

    async def upsert(self, points: Sequence[ExamplePoint]) -> None:
        if not points:
            return
        try:
            await self.client.upsert(
                self.name,
                points=[
                    models.PointStruct(
                        id=str(point.example_id),
                        vector=list(point.vector),
                        payload={
                            "tenant_id": str(point.tenant_id),
                            "workspace_id": str(point.workspace_id),
                            "step": point.step,
                            "subject": point.subject,
                            "group": point.group,
                            _DECIDED: point.decided_at.timestamp(),
                        },
                    )
                    for point in points
                ],
                wait=True,
            )
        except Exception as exc:
            raise InfrastructureError(
                "failed to index examples", details={"error": type(exc).__name__}
            ) from exc

    async def known(self, ids: Sequence[uuid.UUID], *, tenant_id: uuid.UUID) -> set[uuid.UUID]:
        if not ids:
            return set()
        found = await self.client.retrieve(
            self.name, ids=[str(i) for i in ids], with_payload=["tenant_id"], with_vectors=False
        )
        return {
            uuid.UUID(str(point.id))
            for point in found
            if (point.payload or {}).get("tenant_id") == str(tenant_id)
        }

    def _filter(
        self, trusted: ExampleFilter, subject: str | None, exclude_groups: Sequence[str]
    ) -> models.Filter:
        must = [
            _match("tenant_id", str(trusted.tenant_id)),
            _match("workspace_id", str(trusted.workspace_id)),
            _match("step", trusted.step),
        ]
        if subject is not None:
            must.append(_match("subject", subject))
        return models.Filter(
            must=list(must),
            must_not=(
                [
                    models.FieldCondition(
                        key="group", match=models.MatchAny(any=list(exclude_groups))
                    )
                ]
                if exclude_groups
                else None
            ),
        )

    async def nearest(
        self,
        vectors: Sequence[Sequence[float]],
        trusted: ExampleFilter,
        *,
        subject: str | None,
        k: int,
        exclude_groups: Sequence[str],
    ) -> list[list[uuid.UUID]]:
        if not vectors:
            return []
        scopes = [subject, None] if subject is not None else [None]
        requests = [
            models.QueryRequest(
                query=list(vector),
                filter=self._filter(trusted, narrowed, exclude_groups),
                limit=k,
                with_payload=False,
            )
            for vector in vectors
            for narrowed in scopes
        ]
        try:
            responses = await self.client.query_batch_points(self.name, requests=requests)
        except Exception as exc:
            raise InfrastructureError(
                "example search failed", details={"error": type(exc).__name__}
            ) from exc
        found: list[list[uuid.UUID]] = []
        width = len(scopes)
        for index in range(len(vectors)):
            chosen: list[uuid.UUID] = []
            for response in responses[index * width : (index + 1) * width]:
                for point in response.points:
                    example = uuid.UUID(str(point.id))
                    if example not in chosen and len(chosen) < k:
                        chosen.append(example)
            found.append(chosen)
        return found

    async def _collections(self) -> list[str]:
        """Every model's collection of this index, served now or not."""
        prefix = f"{self.collection}__"
        return [
            c.name
            for c in (await self.client.get_collections()).collections
            if c.name.startswith(prefix)
        ]

    async def _delete(self, condition: models.FieldCondition) -> None:
        for name in await self._collections():
            await self.client.delete(
                name,
                points_selector=models.FilterSelector(filter=models.Filter(must=[condition])),
                wait=True,
            )

    async def delete_before(self, cutoff: datetime) -> None:
        """In every model's collection: a vector outlives its case nowhere."""
        await self._delete(
            models.FieldCondition(key=_DECIDED, range=models.Range(lt=cutoff.timestamp()))
        )

    async def delete_by_tenant(self, tenant_id: uuid.UUID) -> None:
        """Every point of one tenant, in every model's collection: a tenant
        offboarded leaves no vector behind in a collection no process serves
        any more."""
        await self._delete(_match("tenant_id", str(tenant_id)))

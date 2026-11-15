"""The examples index: past cases a person decided, found by how alike their
input reads (Sales ticket 43, dw_sales ADR 0015 decision 5).

A step reading a customer's words does better shown the cases most like them
that a person already settled (Liu et al., retrieved over random examples;
`docs/research/2026-11-16-less-human-review.md`). This is where those cases
are found. It is the knowledge gateway's second door, and the same rule holds
at it: the filter that decides whose cases are searched is built here, from
arguments the caller took from the run or the verified context, and never
from anything a request or a model wrote.

**Ids, never text** (`docs/research/2026-11-17-qdrant-review.md` section 3):
the index holds a vector and the fields it is filtered by (tenant, workspace,
step, subject, group, when decided) and no word of the input. A search
returns ids; the context re-reads each case from PostgreSQL under its own RLS.
A filter regression in the index can then cost a tenant a worse example, never
another tenant's words in its prompt: the read refuses an id that is not its.

**Dense only.** The hybrid BM25 leg of `dw_knowledge.hybrid` ranks over text
the index stores, and this index stores none. One vector search per call.

**Same subject first.** A customer's own past cases say most about how that
customer writes, so `nearest` fills from the subject's cases first and only
then from the rest of the tenant's, in one round trip.

**Never retrieves its own group.** A case read again (an eval's held-out case,
the optimiser's replay) excludes the group it belongs to (its PO), or the
measure is a measure of leakage.

Writes are the caller's best effort: a case that is not indexed is not
retrieved, nothing worse. Deletes raise, because retention and offboarding
must know when a vector outlived its case.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final, Protocol

from dw_knowledge.ports import EmbeddingPort

__all__ = [
    "DEFAULT_EXAMPLES_COLLECTION",
    "ExampleFilter",
    "ExampleGateway",
    "ExampleIndexPort",
    "ExamplePoint",
    "ExampleText",
]

DEFAULT_EXAMPLES_COLLECTION: Final = "dw_examples"

# The most nearest cases one text may ask for: a prompt shows a few, and a
# larger k only moves cost onto the mail's path.
MAX_K: Final = 10
# The most texts one call embeds and searches for: a step reads ten lines at
# a time.
MAX_TEXTS: Final = 20


class ExampleText(Protocol):
    """A decided case as the index takes it: its id, the step and subject it
    belongs to, the group it is never retrieved for (its PO), when it was
    decided, and the input it was read from (embedded, never stored)."""

    @property
    def example_id(self) -> uuid.UUID: ...

    @property
    def step(self) -> str: ...

    @property
    def subject(self) -> str | None: ...

    @property
    def group(self) -> str: ...

    @property
    def decided_at(self) -> datetime: ...

    @property
    def text(self) -> str: ...


@dataclass(frozen=True, slots=True)
class ExamplePoint:
    """One indexed case: the vector and the fields searches are filtered by."""

    example_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    step: str
    subject: str | None
    group: str
    decided_at: datetime
    vector: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class ExampleFilter:
    """The constraints every example search runs under. Built only by
    `ExampleGateway`, from the tenant and workspace its caller took from a
    run or a verified context; an adapter searches nothing without one."""

    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    step: str


class ExampleIndexPort(Protocol):
    """The vector store's side of the examples index (Qdrant, or memory)."""

    async def ensure_ready(self, vector_dimension: int, embedding_model: str) -> None: ...

    async def upsert(self, points: Sequence[ExamplePoint]) -> None: ...

    async def known(self, ids: Sequence[uuid.UUID], *, tenant_id: uuid.UUID) -> set[uuid.UUID]:
        """Which of ``ids`` this tenant already has indexed."""
        ...

    async def nearest(
        self,
        vectors: Sequence[Sequence[float]],
        trusted: ExampleFilter,
        *,
        subject: str | None,
        k: int,
        exclude_groups: Sequence[str],
    ) -> list[list[uuid.UUID]]:
        """For each vector, the ``k`` nearest cases ``trusted`` admits, the
        ``subject``'s first, then the rest of the tenant's, none of
        ``exclude_groups``; one round trip for all of them."""
        ...

    async def delete_before(self, cutoff: datetime) -> None:
        """Every point decided before ``cutoff``, every tenant's: retention's."""
        ...

    async def delete_by_tenant(self, tenant_id: uuid.UUID) -> None: ...


@dataclass
class ExampleGateway:
    """Index decided cases and find the ones most like a new input."""

    index: ExampleIndexPort
    embeddings: EmbeddingPort
    # A step reading a mail waits on this at most this long, then reads
    # without examples: the embedder and one vector search, measured in
    # tens of milliseconds where they are healthy.
    timeout_seconds: float = 2.0
    _ready: bool = field(default=False, init=False)

    async def _prepared(self) -> None:
        if not self._ready:
            await self.index.ensure_ready(self.embeddings.dimension, self.embeddings.model)
            self._ready = True

    async def add(
        self,
        examples: Sequence[ExampleText],
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> int:
        """Index the ``examples`` this tenant has not indexed yet, stamped with
        ``tenant_id`` and ``workspace_id``, the caller's own scope and never a
        value an example carries. Returns how many were embedded."""
        if not examples:
            return 0
        await self._prepared()
        known = await self.index.known([e.example_id for e in examples], tenant_id=tenant_id)
        fresh = [e for e in examples if e.example_id not in known]
        if not fresh:
            return 0
        vectors = await self.embeddings.embed([e.text for e in fresh])
        await self.index.upsert(
            [
                ExamplePoint(
                    example_id=example.example_id,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    step=example.step,
                    subject=example.subject,
                    group=example.group,
                    decided_at=example.decided_at,
                    vector=tuple(vector),
                )
                for example, vector in zip(fresh, vectors, strict=True)
            ]
        )
        return len(fresh)

    async def similar(
        self,
        texts: Sequence[str],
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        step: str,
        subject: str | None,
        k: int,
        exclude_groups: Sequence[str] = (),
    ) -> list[list[uuid.UUID]]:
        """For each of ``texts``, the ids of the ``k`` decided cases of
        ``step`` most like it, in this tenant's and workspace's index only,
        ``subject``'s first. One embedding call and one search, bounded by
        `timeout_seconds`; raises on any failure, which the caller turns into
        a reading without examples (an empty answer would read as "none")."""
        if not texts or k <= 0:
            return [[] for _ in texts]
        if len(texts) > MAX_TEXTS:
            raise ValueError("too many texts for one example search")
        trusted = ExampleFilter(tenant_id=tenant_id, workspace_id=workspace_id, step=step)
        async with asyncio.timeout(self.timeout_seconds):
            await self._prepared()
            vectors = await self.embeddings.embed(list(texts))
            return await self.index.nearest(
                vectors,
                trusted,
                subject=subject,
                k=min(k, MAX_K),
                exclude_groups=exclude_groups,
            )

    async def prune(self, cutoff: datetime) -> None:
        """Drop every point decided before ``cutoff``: its case has left the
        store with its month (the labelled cases' retention)."""
        await self.index.delete_before(cutoff)

    async def delete_by_tenant(self, tenant_id: uuid.UUID) -> None:
        await self.index.delete_by_tenant(tenant_id)

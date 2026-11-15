"""In-memory examples index (tests, evals and infra-less local runs).

The same filter and the same order as `QdrantExampleIndex`: tenant, workspace
and step always, the subject's cases first, then the tenant's others, never a
group the caller excluded, cosine order within each. An eval measured against
a cousin of what Qdrant serves would measure nothing anyone runs.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from dw_knowledge.examples import ExampleFilter, ExamplePoint


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


@dataclass
class InMemoryExampleIndex:
    """Implements `ExampleIndexPort` in process memory."""

    points: dict[uuid.UUID, ExamplePoint] = field(default_factory=dict)

    async def ensure_ready(self, vector_dimension: int, embedding_model: str) -> None:
        return None

    async def upsert(self, points: Sequence[ExamplePoint]) -> None:
        for point in points:
            self.points[point.example_id] = point

    async def known(self, ids: Sequence[uuid.UUID], *, tenant_id: uuid.UUID) -> set[uuid.UUID]:
        return {
            i for i in ids if (p := self.points.get(i)) is not None and p.tenant_id == tenant_id
        }

    async def nearest(
        self,
        vectors: Sequence[Sequence[float]],
        trusted: ExampleFilter,
        *,
        subject: str | None,
        k: int,
        exclude_groups: Sequence[str],
    ) -> list[list[uuid.UUID]]:
        excluded = set(exclude_groups)
        admitted = [
            p
            for p in self.points.values()
            if p.tenant_id == trusted.tenant_id
            and p.workspace_id == trusted.workspace_id
            and p.step == trusted.step
            and p.group not in excluded
        ]
        found: list[list[uuid.UUID]] = []
        for vector in vectors:
            ranked = sorted(admitted, key=lambda p: -_cosine(vector, p.vector))
            own = [p.example_id for p in ranked if subject is not None and p.subject == subject]
            chosen = own[:k]
            chosen += [p.example_id for p in ranked if p.example_id not in chosen][
                : k - len(chosen)
            ]
            found.append(chosen)
        return found

    async def delete_before(self, cutoff: datetime) -> None:
        for key in [k for k, p in self.points.items() if p.decided_at < cutoff]:
            del self.points[key]

    async def delete_by_tenant(self, tenant_id: uuid.UUID) -> None:
        for key in [k for k, p in self.points.items() if p.tenant_id == tenant_id]:
            del self.points[key]

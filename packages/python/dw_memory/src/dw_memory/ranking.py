"""Which remembered facts reach the model when there are more than fit.

Recall narrows by tenant, workspace, worker, clearance and validity — five
conditions, each a boundary, each with a negative test. What it could not do is
choose WHICH twelve of ninety live facts about one account are the twelve worth
sending. It ordered by confidence, which answers "what were we surest of", not
"what is this about".

The design decision that matters here is that similarity **ranks** and never
**filters**. The rows are exactly the rows the SQL already returned; the vector
store only says what order to read them in, and anything it has never seen goes
last rather than disappearing. Three consequences, and they are the reason to
build it this way:

- An index that is empty, stale, or poisoned cannot produce a WRONG answer. It
  can only produce a worse ORDER. Every authorization decision stays in the
  query that already has mutation-proven tests.
- Memories written before the index existed still surface. Filtering on ids from
  the store would have made them vanish silently, which is the worst shape a
  regression can take.
- Nothing has to be kept in sync. A superseded memory may well still sit in the
  index; it simply never appears in the rows to be ordered.

So this module is honestly a nice-to-have on top of a correct answer, and it is
built so it can never become load-bearing by accident.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from typing import Protocol

logger = logging.getLogger("dw_memory.ranking")

__all__ = ["MemoryRankerPort", "rank_by"]


class MemoryRankerPort(Protocol):
    """Orders a tenant's memory ids by similarity to a question.

    Tenancy is a parameter and not optional: the store is asked only for one
    tenant's points. That is defence in depth rather than the boundary — the
    boundary is the SQL — but a filter that can be forgotten is one that will be.
    """

    async def nearest(
        self,
        query: str,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        worker_id: str,
        limit: int,
    ) -> tuple[uuid.UUID, ...]: ...


def rank_by[ItemT](
    order: Sequence[uuid.UUID], items: Sequence[tuple[uuid.UUID, ItemT]]
) -> list[ItemT]:
    """Reorder `items` to follow `order`; anything unranked keeps its place, last.

    Stable on purpose, and `sorted` already is: rows the ranker has never seen
    keep the order the query chose — confidence, then recency — which is a
    sensible answer for a fact it has no opinion about. Sorting them among
    themselves would replace a considered order with an arbitrary one.
    """
    position = {memory_id: index for index, memory_id in enumerate(order)}
    unranked = len(position)
    return [value for _, value in sorted(items, key=lambda pair: position.get(pair[0], unranked))]

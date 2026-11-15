"""`DescriptionExamplesPort` in memory, for unit tests and evals (ticket 43).

Holds the SQL reader's contract, not only the happy path: each scope's
decided lines are its own (what RLS gives `SqlDescriptionExamples`), so an id
another scope's index handed back reads as nothing; `after` pages oldest first
from a position, as the keyset query does.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from dw_sales.application.examples import DescriptionExample
from dw_sales.application.ports import SalesScope


@dataclass
class MemoryDescriptionExamples:
    """Implements `DescriptionExamplesPort`."""

    held: dict[SalesScope, list[DescriptionExample]] = field(default_factory=dict)

    def add(self, scope: SalesScope, *examples: DescriptionExample) -> None:
        self.held.setdefault(scope, []).extend(examples)

    async def by_ids(
        self, scope: SalesScope, ids: Sequence[uuid.UUID]
    ) -> Sequence[DescriptionExample]:
        wanted = set(ids)
        return [e for e in self.held.get(scope, []) if e.label_id in wanted]

    async def after(
        self, scope: SalesScope, position: tuple[datetime, uuid.UUID] | None, limit: int
    ) -> Sequence[DescriptionExample]:
        ordered = sorted(self.held.get(scope, []), key=lambda e: (e.decided_at, e.label_id))
        later = [e for e in ordered if position is None or (e.decided_at, e.label_id) > position]
        return later[:limit]

"""`PoBodyExamplesPort` in memory, for unit tests and evals (ticket 43).

Holds the SQL reader's contract: each scope's decided values are its own
(what RLS gives `SqlPoBodyExamples`), one customer's only, newest first.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from dw_sales.application.po_body_examples import PoBodyExample
from dw_sales.application.ports import SalesScope


@dataclass
class MemoryPoBodyExamples:
    """Implements `PoBodyExamplesPort`."""

    held: dict[SalesScope, list[PoBodyExample]] = field(default_factory=dict)

    def add(self, scope: SalesScope, *examples: PoBodyExample) -> None:
        self.held.setdefault(scope, []).extend(examples)

    async def latest(
        self, scope: SalesScope, customer_code: str, limit: int
    ) -> Sequence[PoBodyExample]:
        mine = [e for e in self.held.get(scope, []) if e.customer_code == customer_code]
        return sorted(mine, key=lambda e: (e.decided_at, e.label_id), reverse=True)[:limit]

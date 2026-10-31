"""Adapters: the only layer allowed to know a database or an SDK.

This one keeps requests in memory, which is a real implementation of the port
and not a placeholder — a context with a table replaces it with a SQL repository
and a migration.
"""

from __future__ import annotations

from dw_purchasing.domain.entities import PurchasingRequest


class InMemoryPurchasingSink:
    """Implements this context's `PurchasingSinkPort`."""

    def __init__(self) -> None:
        self.recorded: list[PurchasingRequest] = []

    async def record(self, request: PurchasingRequest) -> None:
        self.recorded.append(request)

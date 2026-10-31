"""Ports this context needs, declared BY the consumer.

The composition root satisfies them. Declaring them here rather than importing a
concrete adapter is what keeps the handler testable without infrastructure.
"""

from __future__ import annotations

from typing import Protocol

from dw_purchasing.domain.entities import PurchasingRequest


class PurchasingSinkPort(Protocol):
    """Where a handled request goes. A real context names its repository here."""

    async def record(self, request: PurchasingRequest) -> None: ...

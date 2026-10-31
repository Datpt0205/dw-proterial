"""Handlers: the only place this context decides anything."""

from __future__ import annotations

from dataclasses import dataclass

from dw_purchasing.application.ports import PurchasingSinkPort
from dw_purchasing.domain.entities import PurchasingRequest


@dataclass(frozen=True)
class HandlePurchasing:
    sink: PurchasingSinkPort

    async def __call__(self, request: PurchasingRequest) -> str:
        await self.sink.record(request)
        return request.summary()

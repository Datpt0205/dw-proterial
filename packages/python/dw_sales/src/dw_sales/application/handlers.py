"""Handlers: the only place this context decides anything."""

from __future__ import annotations

from dataclasses import dataclass

from dw_sales.application.ports import SalesSinkPort
from dw_sales.domain.entities import SalesRequest


@dataclass(frozen=True)
class HandleSales:
    sink: SalesSinkPort

    async def __call__(self, request: SalesRequest) -> str:
        await self.sink.record(request)
        return request.summary()

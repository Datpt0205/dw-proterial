"""`SalesCatalogPort` whose customers carry their compliance as the export-
control results move it (WIV-03-032, 2026-10-28).

Wraps the approved master data at the composition root, so every reader of a
customer (the order checks above all, `missing_noc_esf`) sees one answer:
a NOC received on the export-control page confirms it, an ESF approved there
covers its year, a denial-list match or an escalated red flag holds the
customer's orders. One function decides it (`effective_compliance`); the
export-control page reads the master data underneath and applies the same.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from dw_sales.application.export_control import ExportControlUnitOfWorkFactory
from dw_sales.application.ports import SalesCatalogPort, SalesScope, Snapshot
from dw_sales.domain.catalog import (
    BravoOrder,
    ConvertEntry,
    Customer,
    Item,
    LmeMonth,
    OpenYcbg,
    Quotation,
)
from dw_sales.domain.export_control import ScreeningRecord, effective_compliance


@dataclass(frozen=True)
class ScreenedCatalog:
    """Implements `SalesCatalogPort` over ``inner`` (module docstring)."""

    inner: SalesCatalogPort
    screenings: ExportControlUnitOfWorkFactory

    async def _records(self, scope: SalesScope) -> dict[str, list[ScreeningRecord]]:
        async with self.screenings(scope) as work:
            records = await work.screenings.records()
        held: dict[str, list[ScreeningRecord]] = {}
        for record in records:
            held.setdefault(record.customer_code, []).append(record)
        return held

    async def _one(
        self, scope: SalesScope, found: Snapshot[Customer | None]
    ) -> Snapshot[Customer | None]:
        customer = found.data
        if customer is None:
            return found
        records = (await self._records(scope)).get(customer.code, [])
        return Snapshot(_screened(customer, records), found.as_of)

    async def customer_by_code(self, scope: SalesScope, code: str) -> Snapshot[Customer | None]:
        return await self._one(scope, await self.inner.customer_by_code(scope, code))

    async def customer_by_email_domain(
        self, scope: SalesScope, domain: str
    ) -> Snapshot[Customer | None]:
        return await self._one(scope, await self.inner.customer_by_email_domain(scope, domain))

    async def customers(self, scope: SalesScope) -> Snapshot[Sequence[Customer]]:
        found = await self.inner.customers(scope)
        records = await self._records(scope)
        return Snapshot([_screened(c, records.get(c.code, [])) for c in found.data], found.as_of)

    # ------------------------------------------- everything else, as it is --

    async def items(self, scope: SalesScope) -> Snapshot[Sequence[Item]]:
        return await self.inner.items(scope)

    async def item_by_prv_code(self, scope: SalesScope, prv_code: str) -> Snapshot[Item | None]:
        return await self.inner.item_by_prv_code(scope, prv_code)

    async def convert_entry(
        self, scope: SalesScope, customer_code: str, customer_item_code: str
    ) -> Snapshot[ConvertEntry | None]:
        return await self.inner.convert_entry(scope, customer_code, customer_item_code)

    async def convert_list(self, scope: SalesScope) -> Snapshot[Sequence[ConvertEntry]]:
        return await self.inner.convert_list(scope)

    async def quotations_valid_on(
        self, scope: SalesScope, customer_code: str, prv_code: str, day: date
    ) -> Snapshot[Sequence[Quotation]]:
        return await self.inner.quotations_valid_on(scope, customer_code, prv_code, day)

    async def quotations_for_item(
        self, scope: SalesScope, prv_code: str
    ) -> Snapshot[Sequence[Quotation]]:
        return await self.inner.quotations_for_item(scope, prv_code)

    async def quotations(self, scope: SalesScope) -> Snapshot[Sequence[Quotation]]:
        return await self.inner.quotations(scope)

    async def lme_for_month(self, scope: SalesScope, month: str) -> Snapshot[LmeMonth | None]:
        return await self.inner.lme_for_month(scope, month)

    async def lme_months(self, scope: SalesScope) -> Snapshot[Sequence[LmeMonth]]:
        return await self.inner.lme_months(scope)

    async def orders_for_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> Snapshot[Sequence[BravoOrder]]:
        return await self.inner.orders_for_po(scope, customer_code, po_no)

    async def orders_since(self, scope: SalesScope, since: date) -> Snapshot[Sequence[BravoOrder]]:
        return await self.inner.orders_since(scope, since)

    async def open_ycbg(self, scope: SalesScope) -> Snapshot[Sequence[OpenYcbg]]:
        return await self.inner.open_ycbg(scope)


def _screened(customer: Customer, records: list[ScreeningRecord]) -> Customer:
    if not records:
        return customer
    return customer.model_copy(
        update={"compliance": effective_compliance(customer.compliance, records)}
    )

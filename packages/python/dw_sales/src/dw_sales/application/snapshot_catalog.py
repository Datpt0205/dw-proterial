"""`SalesCatalogPort` over the tenant's approved master-data snapshots, with
the existing source behind it (ticket 41).

Each list Sales maintains by hand (`CatalogList`) is answered from the
workspace's **approved** snapshot of that list where it has one, and from
``fallback`` otherwise: today the fictional mock data, so a tenant keeps
working on it until its own data is imported and approved, list by list. The
ERP's own records (its sales orders and its open YCBG) are always the
fallback's: they come from Bravo, not from a file.

Every lookup keeps the port's meaning: exact, by code or domain, never the
nearest match; a code the snapshot does not hold answers None, whatever the
fallback holds, because a snapshot replaces its list whole. Each read answers
with the ``as_of`` of the list it came from.

The quotation master list a sent quotation is recorded in
(`QuotationLedgerPort`) stays the fallback's: an imported snapshot is never
edited after its approval, and a quotation DW1 sends reaches it with the
next import.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

from dw_sales.application.ports import SalesCatalogPort, SalesScope, Snapshot
from dw_sales.application.quote_ports import QuotationLedgerPort
from dw_sales.domain.catalog import (
    BravoOrder,
    ConvertEntry,
    Customer,
    Item,
    LmeMonth,
    OpenYcbg,
    Quotation,
)
from dw_sales.domain.master_data import CatalogList, CatalogRecord


@dataclass(frozen=True)
class ApprovedList:
    """One approved snapshot of one list, indexed the ways the port asks.

    Built once per snapshot (a snapshot never changes after its parse), so
    an adapter may keep it by snapshot id. The keys are unique by
    construction: the import refused a second row with the same key.
    """

    catalog_list: CatalogList
    snapshot_id: uuid.UUID
    as_of: datetime
    records: tuple[CatalogRecord, ...]
    _by_key: Mapping[object, CatalogRecord] = field(default_factory=dict, repr=False)
    _by_domain: Mapping[str, Customer] = field(default_factory=dict, repr=False)

    @classmethod
    def of(
        cls,
        catalog_list: CatalogList,
        snapshot_id: uuid.UUID,
        as_of: datetime,
        records: Sequence[CatalogRecord],
    ) -> ApprovedList:
        if as_of.utcoffset() is None:
            raise ValueError("as_of needs a timezone")
        by_key: dict[object, CatalogRecord] = {}
        by_domain: dict[str, Customer] = {}
        for record in records:
            match record:
                case Customer():
                    by_key[record.code] = record
                    by_domain |= dict.fromkeys(record.email_domains, record)
                case Item():
                    by_key[record.prv_code] = record
                case ConvertEntry():
                    by_key[(record.customer_code, record.customer_item_code)] = record
                case LmeMonth():
                    by_key[record.month] = record
                case Quotation():
                    pass
        ordered = (
            tuple(sorted(records, key=lambda r: r.month if isinstance(r, LmeMonth) else ""))
            if catalog_list is CatalogList.LME
            else tuple(records)
        )
        return cls(catalog_list, snapshot_id, as_of, ordered, by_key, by_domain)

    def one[T](self, key: object, kind: type[T]) -> T | None:
        found = self._by_key.get(key)
        return found if isinstance(found, kind) else None

    def customer_by_domain(self, domain: str) -> Customer | None:
        return self._by_domain.get(domain)

    def all[T](self, kind: type[T]) -> tuple[T, ...]:
        return tuple(r for r in self.records if isinstance(r, kind))


class ApprovedListsPort(Protocol):
    """The scope's approved snapshot of one list, or None when it has none.
    Bound to the scope's tenant and workspace (RLS), never another's."""

    async def approved(
        self, scope: SalesScope, catalog_list: CatalogList
    ) -> ApprovedList | None: ...


class FallbackCatalogPort(SalesCatalogPort, QuotationLedgerPort, Protocol):
    """What answers a list no snapshot was approved for: the mock today."""


@dataclass(frozen=True)
class SnapshotSalesCatalog:
    """Implements `SalesCatalogPort` and `QuotationLedgerPort` (module docstring)."""

    approved: ApprovedListsPort
    fallback: FallbackCatalogPort

    async def _list(self, scope: SalesScope, catalog_list: CatalogList) -> ApprovedList | None:
        return await self.approved.approved(scope, catalog_list)

    async def customer_by_code(self, scope: SalesScope, code: str) -> Snapshot[Customer | None]:
        own = await self._list(scope, CatalogList.CUSTOMERS)
        if own is None:
            return await self.fallback.customer_by_code(scope, code)
        return Snapshot(own.one(code, Customer), own.as_of)

    async def customer_by_email_domain(
        self, scope: SalesScope, domain: str
    ) -> Snapshot[Customer | None]:
        own = await self._list(scope, CatalogList.CUSTOMERS)
        if own is None:
            return await self.fallback.customer_by_email_domain(scope, domain)
        return Snapshot(own.customer_by_domain(domain.lower()), own.as_of)

    async def customers(self, scope: SalesScope) -> Snapshot[Sequence[Customer]]:
        own = await self._list(scope, CatalogList.CUSTOMERS)
        if own is None:
            return await self.fallback.customers(scope)
        return Snapshot(own.all(Customer), own.as_of)

    async def items(self, scope: SalesScope) -> Snapshot[Sequence[Item]]:
        own = await self._list(scope, CatalogList.ITEMS)
        if own is None:
            return await self.fallback.items(scope)
        return Snapshot(own.all(Item), own.as_of)

    async def item_by_prv_code(self, scope: SalesScope, prv_code: str) -> Snapshot[Item | None]:
        own = await self._list(scope, CatalogList.ITEMS)
        if own is None:
            return await self.fallback.item_by_prv_code(scope, prv_code)
        return Snapshot(own.one(prv_code, Item), own.as_of)

    async def convert_entry(
        self, scope: SalesScope, customer_code: str, customer_item_code: str
    ) -> Snapshot[ConvertEntry | None]:
        own = await self._list(scope, CatalogList.CONVERT_LIST)
        if own is None:
            return await self.fallback.convert_entry(scope, customer_code, customer_item_code)
        return Snapshot(own.one((customer_code, customer_item_code), ConvertEntry), own.as_of)

    async def convert_list(self, scope: SalesScope) -> Snapshot[Sequence[ConvertEntry]]:
        own = await self._list(scope, CatalogList.CONVERT_LIST)
        if own is None:
            return await self.fallback.convert_list(scope)
        return Snapshot(own.all(ConvertEntry), own.as_of)

    async def quotations_valid_on(
        self, scope: SalesScope, customer_code: str, prv_code: str, day: date
    ) -> Snapshot[Sequence[Quotation]]:
        own = await self._list(scope, CatalogList.QUOTATIONS)
        if own is None:
            return await self.fallback.quotations_valid_on(scope, customer_code, prv_code, day)
        return Snapshot(
            tuple(
                q
                for q in own.all(Quotation)
                if q.customer_code == customer_code
                and q.prv_code == prv_code
                and q.is_valid_on(day)
            ),
            own.as_of,
        )

    async def quotations_for_item(
        self, scope: SalesScope, prv_code: str
    ) -> Snapshot[Sequence[Quotation]]:
        own = await self._list(scope, CatalogList.QUOTATIONS)
        if own is None:
            return await self.fallback.quotations_for_item(scope, prv_code)
        return Snapshot(tuple(q for q in own.all(Quotation) if q.prv_code == prv_code), own.as_of)

    async def quotations(self, scope: SalesScope) -> Snapshot[Sequence[Quotation]]:
        own = await self._list(scope, CatalogList.QUOTATIONS)
        if own is None:
            return await self.fallback.quotations(scope)
        return Snapshot(own.all(Quotation), own.as_of)

    async def lme_for_month(self, scope: SalesScope, month: str) -> Snapshot[LmeMonth | None]:
        own = await self._list(scope, CatalogList.LME)
        if own is None:
            return await self.fallback.lme_for_month(scope, month)
        return Snapshot(own.one(month, LmeMonth), own.as_of)

    async def lme_months(self, scope: SalesScope) -> Snapshot[Sequence[LmeMonth]]:
        own = await self._list(scope, CatalogList.LME)
        if own is None:
            return await self.fallback.lme_months(scope)
        return Snapshot(own.all(LmeMonth), own.as_of)

    # The ERP's own records: never imported from a file (module docstring).

    async def orders_for_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> Snapshot[Sequence[BravoOrder]]:
        return await self.fallback.orders_for_po(scope, customer_code, po_no)

    async def orders_since(self, scope: SalesScope, since: date) -> Snapshot[Sequence[BravoOrder]]:
        return await self.fallback.orders_since(scope, since)

    async def open_ycbg(self, scope: SalesScope) -> Snapshot[Sequence[OpenYcbg]]:
        return await self.fallback.open_ycbg(scope)

    async def record(self, scope: SalesScope, rows: Sequence[Quotation]) -> None:
        await self.fallback.record(scope, rows)

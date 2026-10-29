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

A quotation Sales sent and confirmed (`QuotationLedgerPort`, WIV-03-023
step 11) is kept apart (`RecordedQuotationsPort`, the database), because an
imported snapshot is never edited after its approval. Every quotation read
answers the list, approved snapshot or fallback, plus the recorded rows it
does not hold yet, keyed by quote number and item: a PO checked a minute
after its quotation was confirmed finds it, in the API and in the worker
alike, and the next import that carries it shadows the recorded row. A
recorded row whose number the list holds with other terms is refused when it
is recorded, never merged on read.

An item code Sales confirmed for a customer's own code (`learn_convert`,
`RecordedConvertsPort`, the AI list's item 3) is kept the same way: a later
PO line with that code maps through it at once, the list answers first, and
the first confirmation is the one kept.

A sender Sales confirmed as a customer's (`learn_sender`,
`RecordedSendersPort`, the AI list's item 5) is found by `customer_by_sender`
after the customer's own domains: the address, never its domain.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

from dw_kernel.errors import ConflictError
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


class FallbackCatalogPort(SalesCatalogPort, Protocol):
    """What answers a list no snapshot was approved for: the mock today."""


@dataclass(frozen=True)
class RecordedQuotation:
    """A quotation as Sales confirmed it, and when."""

    quotation: Quotation
    recorded_at: datetime


@dataclass(frozen=True)
class RecordedConvert:
    """A customer's item code as Sales confirmed it, and when."""

    entry: ConvertEntry
    recorded_at: datetime


class RecordedConvertsPort(Protocol):
    """The item codes Sales confirmed, in the scope's tenant and workspace
    (RLS), read the same by every process."""

    async def converts(self, scope: SalesScope) -> Sequence[RecordedConvert]: ...

    async def learn(
        self, scope: SalesScope, entry: ConvertEntry, *, by: uuid.UUID, case_id: uuid.UUID
    ) -> None:
        """Keeps ``entry`` unless the customer's code is already kept: the
        first confirmation stays."""
        ...


@dataclass(frozen=True)
class RecordedSender:
    """The customer Sales confirmed a sender's address as, and when."""

    customer_code: str
    recorded_at: datetime


class RecordedSendersPort(Protocol):
    """The senders Sales confirmed as a customer's, in the scope's tenant and
    workspace (RLS), read the same by every process. Addresses lowercase."""

    async def sender(self, scope: SalesScope, address: str) -> RecordedSender | None: ...

    async def learn(
        self, scope: SalesScope, address: str, customer_code: str, *, by: uuid.UUID, message_id: str
    ) -> None:
        """Keeps the address as the customer's unless it is already kept: the
        first confirmation stays."""
        ...


class RecordedQuotationsPort(Protocol):
    """The quotations Sales sent and confirmed, in the scope's tenant and
    workspace (RLS), read the same by every process."""

    async def recorded(self, scope: SalesScope) -> Sequence[RecordedQuotation]: ...

    async def add(self, scope: SalesScope, rows: Sequence[Quotation]) -> None:
        """Appends the rows not held yet, all or none. Idempotent: a row held
        with the same terms is skipped; one held under its quote number and
        item with other terms is a `ConflictError`, and nothing is written."""
        ...


@dataclass(frozen=True)
class SnapshotSalesCatalog:
    """Implements `SalesCatalogPort` and `QuotationLedgerPort` (module docstring)."""

    approved: ApprovedListsPort
    fallback: FallbackCatalogPort
    recorded: RecordedQuotationsPort
    recorded_converts: RecordedConvertsPort
    recorded_senders: RecordedSendersPort

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

    async def customer_by_sender(
        self, scope: SalesScope, address: str
    ) -> Snapshot[Customer | None]:
        """The customer of the sender's domain, else the one Sales confirmed
        the address as."""
        by_domain = await self.customer_by_email_domain(scope, address.rpartition("@")[2])
        if by_domain.data is not None:
            return by_domain
        kept = await self.recorded_senders.sender(scope, address.lower())
        if kept is None:
            return by_domain
        found = await self.customer_by_code(scope, kept.customer_code)
        if found.data is None:
            return by_domain
        return Snapshot(found.data, max(found.as_of, kept.recorded_at))

    async def learn_sender(
        self, scope: SalesScope, address: str, customer_code: str, *, by: uuid.UUID, message_id: str
    ) -> bool:
        """Implements `SenderLedgerPort`: keeps the address as the customer's;
        False when the sender's domain already answers, which it keeps doing."""
        if (await self.customer_by_email_domain(scope, address.rpartition("@")[2])).data:
            return False
        await self.recorded_senders.learn(
            scope, address.lower(), customer_code, by=by, message_id=message_id
        )
        return True

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

    async def _listed_convert(
        self, scope: SalesScope, customer_code: str, customer_item_code: str
    ) -> Snapshot[ConvertEntry | None]:
        own = await self._list(scope, CatalogList.CONVERT_LIST)
        if own is None:
            return await self.fallback.convert_entry(scope, customer_code, customer_item_code)
        return Snapshot(own.one((customer_code, customer_item_code), ConvertEntry), own.as_of)

    async def convert_entry(
        self, scope: SalesScope, customer_code: str, customer_item_code: str
    ) -> Snapshot[ConvertEntry | None]:
        """The list's row for the code, else the one Sales confirmed."""
        listed = await self._listed_convert(scope, customer_code, customer_item_code)
        if listed.data is not None:
            return listed
        for kept in await self.recorded_converts.converts(scope):
            entry = kept.entry
            if (entry.customer_code, entry.customer_item_code) == (
                customer_code,
                customer_item_code,
            ):
                return Snapshot(entry, max(listed.as_of, kept.recorded_at))
        return listed

    async def convert_list(self, scope: SalesScope) -> Snapshot[Sequence[ConvertEntry]]:
        own = await self._list(scope, CatalogList.CONVERT_LIST)
        listed = (
            Snapshot(own.all(ConvertEntry), own.as_of)
            if own is not None
            else await self.fallback.convert_list(scope)
        )
        held = {(e.customer_code, e.customer_item_code) for e in listed.data}
        added = [
            kept
            for kept in await self.recorded_converts.converts(scope)
            if (kept.entry.customer_code, kept.entry.customer_item_code) not in held
        ]
        if not added:
            return listed
        return Snapshot(
            (*listed.data, *(kept.entry for kept in added)),
            max(listed.as_of, *(kept.recorded_at for kept in added)),
        )

    async def learn_convert(
        self, scope: SalesScope, entry: ConvertEntry, *, by: uuid.UUID, case_id: uuid.UUID
    ) -> bool:
        """Implements `ConvertLedgerPort`: keeps what Sales confirmed for a
        customer's code the list does not hold; False when the list already
        answers for that code, which it keeps doing."""
        listed = await self._listed_convert(scope, entry.customer_code, entry.customer_item_code)
        if listed.data is not None:
            return False
        await self.recorded_converts.learn(scope, entry, by=by, case_id=case_id)
        return True

    async def _quotations(self, scope: SalesScope) -> Snapshot[tuple[Quotation, ...]]:
        """The list's quotations, then the recorded ones it does not hold."""
        own = await self._list(scope, CatalogList.QUOTATIONS)
        listed = (
            Snapshot(own.all(Quotation), own.as_of)
            if own is not None
            else await self.fallback.quotations(scope)
        )
        held = {(q.quote_no, q.prv_code) for q in listed.data}
        added = [
            r
            for r in await self.recorded.recorded(scope)
            if (r.quotation.quote_no, r.quotation.prv_code) not in held
        ]
        if not added:
            return Snapshot(tuple(listed.data), listed.as_of)
        return Snapshot(
            (*listed.data, *(r.quotation for r in added)),
            max(listed.as_of, *(r.recorded_at for r in added)),
        )

    async def quotations_valid_on(
        self, scope: SalesScope, customer_code: str, prv_code: str, day: date
    ) -> Snapshot[Sequence[Quotation]]:
        found = await self._quotations(scope)
        return Snapshot(
            tuple(
                q
                for q in found.data
                if q.customer_code == customer_code
                and q.prv_code == prv_code
                and q.is_valid_on(day)
            ),
            found.as_of,
        )

    async def quotations_for_item(
        self, scope: SalesScope, prv_code: str
    ) -> Snapshot[Sequence[Quotation]]:
        found = await self._quotations(scope)
        return Snapshot(tuple(q for q in found.data if q.prv_code == prv_code), found.as_of)

    async def quotations(self, scope: SalesScope) -> Snapshot[Sequence[Quotation]]:
        return await self._quotations(scope)

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
        """Implements `QuotationLedgerPort`: a row the quotations already hold
        is skipped, one whose number they hold with other terms, or for
        another customer, refuses the whole record."""
        held = (await self._quotations(scope)).data
        terms = {(q.quote_no, q.prv_code): q for q in held}
        owners = {q.quote_no: q.customer_code for q in held}
        for row in rows:
            found = terms.get((row.quote_no, row.prv_code))
            if (found is not None and found != row) or owners.get(
                row.quote_no, row.customer_code
            ) != row.customer_code:
                raise ConflictError(
                    "the master list holds this quote number with other terms",
                    details={"quote_no": row.quote_no, "prv_code": row.prv_code},
                )
        await self.recorded.add(
            scope, [row for row in rows if (row.quote_no, row.prv_code) not in terms]
        )

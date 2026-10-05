"""`SalesCatalogPort` over the fictional master data in `data/`."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from datetime import date, datetime
from pathlib import Path

from pydantic import AwareDatetime, BaseModel, ConfigDict

from dw_kernel.errors import ConflictError, PermissionDeniedError
from dw_sales.adapters.mock.fixtures import DATA_DIR, read_records
from dw_sales.application.ports import SalesScope, Snapshot
from dw_sales.domain.catalog import (
    BravoOrder,
    ConvertEntry,
    Customer,
    Item,
    LmeMonth,
    OpenYcbg,
    Quotation,
    month_key,
)


class _SnapshotFixture(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    as_of: AwareDatetime


def _index[KeyT, RecordT](
    records: Iterable[RecordT], key: Callable[[RecordT], KeyT], what: str
) -> dict[KeyT, RecordT]:
    """Records by key, refusing a key that repeats: a lookup with two answers
    would quietly return whichever was loaded last. The key is a record's id,
    which an error may name."""
    indexed: dict[KeyT, RecordT] = {}
    for record in records:
        k = key(record)
        if k in indexed:
            raise ValueError(f"{what} {k!r} appears twice")
        indexed[k] = record
    return indexed


class MockSalesCatalog:
    """Implements `SalesCatalogPort`, and `QuotationLedgerPort`, for a demo deployment.

    Bound to the one scope whose ERP it stands in for: any other scope reads
    an empty catalogue and has its writes refused. A real adapter resolves the
    tenant's own source from the scope; this one has a single source, and
    serving it to every scope would hand one company's customers and prices
    to every tenant of the deployment. The records are validated and
    cross-checked when it is built, so a hand-edited fixture that names a
    missing item fails at startup rather than as a mapping that silently finds
    nothing. Every read answers with the one ``as_of`` the fixture set was
    exported at.

    It is also the demo's quotation master list: a row `record` writes is a
    quotation every later read returns, which is how a sent quotation becomes
    the one a later PO line is checked against. Held in memory only, for the
    life of the process; a production adapter refuses writes until the
    customer grants access to their master list.
    """

    def __init__(
        self,
        *,
        scope: SalesScope,
        as_of: datetime,
        customers: Iterable[Customer],
        items: Iterable[Item],
        convert_list: Iterable[ConvertEntry],
        quotations: Iterable[Quotation],
        lme: Iterable[LmeMonth],
        bravo_orders: Iterable[BravoOrder],
        open_ycbg: Iterable[OpenYcbg],
    ) -> None:
        if as_of.utcoffset() is None:
            raise ValueError("as_of needs a timezone")
        self._scope = scope
        self._as_of = as_of
        self._customers = _index(customers, lambda c: c.code, "customer code")
        self._customer_by_domain: dict[str, Customer] = {}
        for customer in self._customers.values():
            for domain in customer.email_domains:
                owner = self._customer_by_domain.setdefault(domain, customer)
                if owner is not customer:
                    # The domain itself is left out: it is a customer's data.
                    raise ValueError(f"customers {owner.code} and {customer.code} share a domain")
        self._items = _index(items, lambda i: i.prv_code, "PRV code")
        self._convert = _index(
            convert_list, lambda e: (e.customer_code, e.customer_item_code), "convert entry"
        )
        self._quotations = tuple(_index(quotations, lambda q: q.quote_no, "quote no").values())
        self._lme = dict(sorted(_index(lme, lambda m: m.month, "LME month").items()))
        self._orders = tuple(
            sorted(
                _index(bravo_orders, lambda o: o.so_no, "sales order").values(),
                key=lambda o: (o.order_date, o.so_no),
            )
        )
        self._ycbg = tuple(
            sorted(
                _index(open_ycbg, lambda y: y.ycbg_no, "YCBG").values(),
                key=lambda y: (y.issued_on, y.ycbg_no),
            )
        )
        # ``as_of`` is a claim about the data: nothing in a snapshot can be
        # dated after the snapshot was taken. A case stamps it as its check
        # basis, so one that predates its own records would be false evidence.
        taken_on = as_of.date()
        dated = [o.order_date for o in self._orders] + [y.issued_on for y in self._ycbg]
        if any(day > taken_on for day in dated) or any(
            month > month_key(taken_on) for month in self._lme
        ):
            raise ValueError("as_of is earlier than a record the snapshot holds")
        for entry in self._convert.values():
            self._require(
                entry.customer_code, (entry.prv_code,), f"convert entry {entry.customer_item_code}"
            )
        for quotation in self._quotations:
            self._require(
                quotation.customer_code, (quotation.prv_code,), f"quotation {quotation.quote_no}"
            )
        for order in self._orders:
            self._require(
                order.customer_code,
                tuple(line.prv_code for line in order.lines),
                f"sales order {order.so_no}",
            )
        for ycbg in self._ycbg:
            self._require(ycbg.customer_code, (), f"YCBG {ycbg.ycbg_no}")

    @classmethod
    def load(cls, scope: SalesScope, data_dir: Path = DATA_DIR) -> MockSalesCatalog:
        snapshot = _SnapshotFixture.model_validate(
            json.loads((data_dir / "snapshot.json").read_text(encoding="utf-8"))
        )
        return cls(
            scope=scope,
            as_of=snapshot.as_of,
            customers=read_records(data_dir / "customers.json", Customer),
            items=read_records(data_dir / "items.json", Item),
            convert_list=read_records(data_dir / "convert_list.json", ConvertEntry),
            quotations=read_records(data_dir / "quotations.json", Quotation),
            lme=read_records(data_dir / "lme.json", LmeMonth),
            bravo_orders=read_records(data_dir / "bravo_orders.json", BravoOrder),
            open_ycbg=read_records(data_dir / "open_ycbg.json", OpenYcbg),
        )

    def _require(self, customer_code: str, prv_codes: Iterable[str], owner: str) -> None:
        if customer_code not in self._customers:
            raise ValueError(f"{owner} names unknown customer {customer_code!r}")
        for prv_code in prv_codes:
            if prv_code not in self._items:
                raise ValueError(f"{owner} names unknown item {prv_code!r}")

    def _one[T](self, scope: SalesScope, record: T | None) -> Snapshot[T | None]:
        """``record`` for the scope this catalogue is bound to; None for any other."""
        return Snapshot(data=record if scope == self._scope else None, as_of=self._as_of)

    def _many[T](self, scope: SalesScope, records: Sequence[T]) -> Snapshot[Sequence[T]]:
        """``records`` for the scope this catalogue is bound to; none for any other."""
        return Snapshot(data=records if scope == self._scope else (), as_of=self._as_of)

    async def customer_by_code(self, scope: SalesScope, code: str) -> Snapshot[Customer | None]:
        return self._one(scope, self._customers.get(code))

    async def customer_by_email_domain(
        self, scope: SalesScope, domain: str
    ) -> Snapshot[Customer | None]:
        return self._one(scope, self._customer_by_domain.get(domain.lower()))

    async def customers(self, scope: SalesScope) -> Snapshot[Sequence[Customer]]:
        return self._many(scope, tuple(self._customers.values()))

    async def items(self, scope: SalesScope) -> Snapshot[Sequence[Item]]:
        return self._many(scope, tuple(self._items.values()))

    async def item_by_prv_code(self, scope: SalesScope, prv_code: str) -> Snapshot[Item | None]:
        return self._one(scope, self._items.get(prv_code))

    async def convert_entry(
        self, scope: SalesScope, customer_code: str, customer_item_code: str
    ) -> Snapshot[ConvertEntry | None]:
        return self._one(scope, self._convert.get((customer_code, customer_item_code)))

    async def convert_list(self, scope: SalesScope) -> Snapshot[Sequence[ConvertEntry]]:
        return self._many(scope, tuple(self._convert.values()))

    async def quotations_valid_on(
        self, scope: SalesScope, customer_code: str, prv_code: str, day: date
    ) -> Snapshot[Sequence[Quotation]]:
        return self._many(
            scope,
            tuple(
                q
                for q in self._quotations
                if q.customer_code == customer_code
                and q.prv_code == prv_code
                and q.is_valid_on(day)
            ),
        )

    async def quotations_for_item(
        self, scope: SalesScope, prv_code: str
    ) -> Snapshot[Sequence[Quotation]]:
        return self._many(scope, tuple(q for q in self._quotations if q.prv_code == prv_code))

    async def quotations(self, scope: SalesScope) -> Snapshot[Sequence[Quotation]]:
        return self._many(scope, self._quotations)

    async def lme_for_month(self, scope: SalesScope, month: str) -> Snapshot[LmeMonth | None]:
        return self._one(scope, self._lme.get(month))

    async def lme_months(self, scope: SalesScope) -> Snapshot[Sequence[LmeMonth]]:
        return self._many(scope, tuple(self._lme.values()))

    async def orders_for_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> Snapshot[Sequence[BravoOrder]]:
        return self._many(
            scope,
            tuple(
                sorted(
                    (
                        o
                        for o in self._orders
                        if o.customer_code == customer_code and o.po_no == po_no
                    ),
                    key=lambda o: (o.po_revision, o.order_date, o.so_no),
                )
            ),
        )

    async def orders_since(self, scope: SalesScope, since: date) -> Snapshot[Sequence[BravoOrder]]:
        return self._many(scope, tuple(o for o in self._orders if o.order_date >= since))

    async def open_ycbg(self, scope: SalesScope) -> Snapshot[Sequence[OpenYcbg]]:
        return self._many(scope, self._ycbg)

    async def record(self, scope: SalesScope, rows: Sequence[Quotation]) -> None:
        """Adds master-list rows, one per quoted line.

        Idempotent: a row already held is skipped. A row that differs from the
        held one for its quote number and item, or reuses another customer's
        quote number, is refused and nothing is written. So is any write from
        a scope other than the one this master list belongs to.
        """
        if scope != self._scope:
            raise PermissionDeniedError("the master list is not this scope's to write")
        held = {(q.quote_no, q.prv_code): q for q in self._quotations}
        owners = {q.quote_no: q.customer_code for q in self._quotations}
        new: list[Quotation] = []
        for row in rows:
            self._require(row.customer_code, (row.prv_code,), f"quotation {row.quote_no}")
            existing = held.get((row.quote_no, row.prv_code))
            if existing == row:
                continue
            if existing is not None or owners.get(row.quote_no, row.customer_code) != (
                row.customer_code
            ):
                raise ConflictError(
                    "the master list holds this quote number with other terms",
                    details={"quote_no": row.quote_no, "prv_code": row.prv_code},
                )
            held[(row.quote_no, row.prv_code)] = row
            owners[row.quote_no] = row.customer_code
            new.append(row)
        self._quotations = (*self._quotations, *new)

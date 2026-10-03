"""`SalesCatalogPort` over the fictional master data in `data/`."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import date
from pathlib import Path

from dw_sales.adapters.mock.fixtures import DATA_DIR, read_records
from dw_sales.application.ports import SalesScope
from dw_sales.domain.catalog import ConvertEntry, Customer, Item, LmeMonth, Quotation


def _index[KeyT, RecordT](
    records: Iterable[RecordT], key: Callable[[RecordT], KeyT], what: str
) -> dict[KeyT, RecordT]:
    """Records by key, refusing a key that repeats: a lookup with two answers
    would quietly return whichever was loaded last."""
    indexed: dict[KeyT, RecordT] = {}
    for record in records:
        k = key(record)
        if k in indexed:
            raise ValueError(f"{what} {k!r} appears twice")
        indexed[k] = record
    return indexed


class MockSalesCatalog:
    """Implements `SalesCatalogPort` for a demo deployment.

    Serves the same fictional company to every scope: it stands in for one
    tenant's ERP, where a real adapter resolves the tenant's own source from
    the scope. The records are validated and cross-checked when it is built, so
    a hand-edited fixture that names a missing item fails at startup rather
    than as a mapping that silently finds nothing.
    """

    def __init__(
        self,
        *,
        customers: Iterable[Customer],
        items: Iterable[Item],
        convert_list: Iterable[ConvertEntry],
        quotations: Iterable[Quotation],
        lme: Iterable[LmeMonth],
    ) -> None:
        self._customers = _index(customers, lambda c: c.code, "customer code")
        self._customer_by_domain: dict[str, Customer] = {}
        for customer in self._customers.values():
            for domain in customer.email_domains:
                owner = self._customer_by_domain.setdefault(domain, customer)
                if owner is not customer:
                    raise ValueError(
                        f"email domain {domain!r} belongs to {owner.code} and {customer.code}"
                    )
        self._items = _index(items, lambda i: i.prv_code, "PRV code")
        self._convert = _index(
            convert_list, lambda e: (e.customer_code, e.customer_item_code), "convert entry"
        )
        self._quotations = tuple(_index(quotations, lambda q: q.quote_no, "quote no").values())
        self._lme = dict(sorted(_index(lme, lambda m: m.month, "LME month").items()))
        for entry in self._convert.values():
            self._require(
                entry.customer_code, entry.prv_code, f"convert entry {entry.customer_item_code}"
            )
        for quotation in self._quotations:
            self._require(
                quotation.customer_code, quotation.prv_code, f"quotation {quotation.quote_no}"
            )

    @classmethod
    def load(cls, data_dir: Path = DATA_DIR) -> MockSalesCatalog:
        return cls(
            customers=read_records(data_dir / "customers.json", Customer),
            items=read_records(data_dir / "items.json", Item),
            convert_list=read_records(data_dir / "convert_list.json", ConvertEntry),
            quotations=read_records(data_dir / "quotations.json", Quotation),
            lme=read_records(data_dir / "lme.json", LmeMonth),
        )

    def _require(self, customer_code: str, prv_code: str, owner: str) -> None:
        if customer_code not in self._customers:
            raise ValueError(f"{owner} names unknown customer {customer_code!r}")
        if prv_code not in self._items:
            raise ValueError(f"{owner} names unknown item {prv_code!r}")

    async def customer_by_code(self, scope: SalesScope, code: str) -> Customer | None:
        return self._customers.get(code)

    async def customer_by_email_domain(self, scope: SalesScope, domain: str) -> Customer | None:
        return self._customer_by_domain.get(domain.lower())

    async def customers(self, scope: SalesScope) -> Sequence[Customer]:
        return tuple(self._customers.values())

    async def items(self, scope: SalesScope) -> Sequence[Item]:
        return tuple(self._items.values())

    async def item_by_prv_code(self, scope: SalesScope, prv_code: str) -> Item | None:
        return self._items.get(prv_code)

    async def convert_entry(
        self, scope: SalesScope, customer_code: str, customer_item_code: str
    ) -> ConvertEntry | None:
        return self._convert.get((customer_code, customer_item_code))

    async def convert_list(self, scope: SalesScope) -> Sequence[ConvertEntry]:
        return tuple(self._convert.values())

    async def quotations_valid_on(
        self, scope: SalesScope, customer_code: str, prv_code: str, day: date
    ) -> Sequence[Quotation]:
        return tuple(
            q
            for q in self._quotations
            if q.customer_code == customer_code and q.prv_code == prv_code and q.is_valid_on(day)
        )

    async def quotations_for_item(self, scope: SalesScope, prv_code: str) -> Sequence[Quotation]:
        return tuple(q for q in self._quotations if q.prv_code == prv_code)

    async def quotations(self, scope: SalesScope) -> Sequence[Quotation]:
        return self._quotations

    async def lme_for_month(self, scope: SalesScope, month: str) -> LmeMonth | None:
        return self._lme.get(month)

    async def lme_months(self, scope: SalesScope) -> Sequence[LmeMonth]:
        return tuple(self._lme.values())

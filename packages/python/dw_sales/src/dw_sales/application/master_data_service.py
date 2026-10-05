"""Master data, read-only, through `SalesCatalogPort` (spec decision 2).

Every list answers with the snapshot's ``as_of``. Customers' contacts are
personal data and go to `sales.case.read` holders only, like every route
here. The lists that hold prices hold every customer's: a quotation's or an
ERP order line's price goes out only with `sales.price.read` and
`sales.price.other_customers.read` both; an LME figure with
`sales.price.read`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.ports import SalesCatalogPort
from dw_sales.application.views import (
    BravoOrderView,
    ConvertEntryView,
    CustomerView,
    ItemView,
    LmeView,
    MasterDataView,
    OpenYcbgView,
    QuotationRowView,
    bravo_order,
    convert_entry,
    customer,
    item,
    lme_month,
    open_ycbg,
    quotation_row,
)
from dw_sales.domain.catalog import LmeMonth

_RESOURCE = "sales_master_data"
# The ERP export holds 12 months; asking from the epoch asks for all of it.
_EPOCH = date(1970, 1, 1)


@dataclass(frozen=True)
class MasterDataService:
    gate: Gate
    catalog: SalesCatalogPort

    async def customers(self, context: AccessContext) -> MasterDataView[CustomerView]:
        await self._read(context)
        found = await self.catalog.customers(sales_scope(context))
        return MasterDataView(as_of=found.as_of, items=[customer(c) for c in found.data])

    async def items(self, context: AccessContext) -> MasterDataView[ItemView]:
        await self._read(context)
        found = await self.catalog.items(sales_scope(context))
        return MasterDataView(as_of=found.as_of, items=[item(i) for i in found.data])

    async def convert_list(self, context: AccessContext) -> MasterDataView[ConvertEntryView]:
        await self._read(context)
        found = await self.catalog.convert_list(sales_scope(context))
        return MasterDataView(as_of=found.as_of, items=[convert_entry(e) for e in found.data])

    async def quotations(self, context: AccessContext) -> MasterDataView[QuotationRowView]:
        await self._read(context)
        prices = self.gate.prices(context)
        found = await self.catalog.quotations(sales_scope(context))
        return MasterDataView(
            as_of=found.as_of,
            items=[quotation_row(q, prices.other_customers) for q in found.data],
        )

    async def lme(self, context: AccessContext) -> MasterDataView[LmeView]:
        await self._read(context)
        visible = self.gate.prices(context).amounts
        found = await self.catalog.lme_months(sales_scope(context))
        months: list[LmeMonth] = list(found.data)
        return MasterDataView(as_of=found.as_of, items=[lme_month(m, visible) for m in months])

    async def bravo_orders(self, context: AccessContext) -> MasterDataView[BravoOrderView]:
        await self._read(context)
        visible = self.gate.prices(context).other_customers
        found = await self.catalog.orders_since(sales_scope(context), _EPOCH)
        return MasterDataView(
            as_of=found.as_of, items=[bravo_order(o, visible) for o in found.data]
        )

    async def open_ycbg(self, context: AccessContext) -> MasterDataView[OpenYcbgView]:
        await self._read(context)
        found = await self.catalog.open_ycbg(sales_scope(context))
        return MasterDataView(as_of=found.as_of, items=[open_ycbg(y) for y in found.data])

    async def _read(self, context: AccessContext) -> None:
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type=_RESOURCE)

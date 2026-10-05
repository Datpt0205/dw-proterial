"""`MockSalesCatalog`: every fixture record read back through `SalesCatalogPort`."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, Field

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.mock import MockSalesCatalog
from dw_sales.adapters.mock.fixtures import DATA_DIR, read_records
from dw_sales.application.ports import SalesCatalogPort, SalesScope
from dw_sales.domain.catalog import (
    BravoOrder,
    ConvertEntry,
    Customer,
    LmeBand,
    OpenYcbg,
    Quotation,
    fiscal_year,
)

pytestmark = pytest.mark.unit

SCOPE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
# The day the demo's mailbox is read: every PO in it is dated September 2026.
DEMO_DAY = date(2026, 9, 30)
AS_OF = datetime.fromisoformat(
    json.loads((DATA_DIR / "snapshot.json").read_text(encoding="utf-8"))["as_of"]
)


@pytest.fixture(scope="module")
def catalog() -> MockSalesCatalog:
    return MockSalesCatalog.load()


async def _rebuild(catalog: MockSalesCatalog, **overrides: Any) -> MockSalesCatalog:
    """The fixture catalogue built again, with some of its records replaced."""
    records: dict[str, Any] = {
        "as_of": AS_OF,
        "customers": (await catalog.customers(SCOPE)).data,
        "items": (await catalog.items(SCOPE)).data,
        "convert_list": (await catalog.convert_list(SCOPE)).data,
        "quotations": (await catalog.quotations(SCOPE)).data,
        "lme": (await catalog.lme_months(SCOPE)).data,
        "bravo_orders": (await catalog.orders_since(SCOPE, date(2000, 1, 1))).data,
        "open_ycbg": (await catalog.open_ycbg(SCOPE)).data,
    }
    return MockSalesCatalog(**(records | overrides))


def test_the_mock_satisfies_the_port(catalog: MockSalesCatalog) -> None:
    # The check is mypy's: this assignment fails typecheck when a signature drifts.
    port: SalesCatalogPort = catalog
    assert port is catalog


async def test_every_read_returns_the_snapshots_as_of_beside_its_data(
    catalog: MockSalesCatalog,
) -> None:
    """A case stamps it as its check basis, so no read may answer without it."""
    reads = [
        await catalog.customer_by_code(SCOPE, "VLX"),
        await catalog.customer_by_email_domain(SCOPE, "velatrix.example"),
        await catalog.customers(SCOPE),
        await catalog.items(SCOPE),
        await catalog.item_by_prv_code(SCOPE, "HW-1001"),
        await catalog.convert_entry(SCOPE, "VLX", "PN-1001"),
        await catalog.convert_list(SCOPE),
        await catalog.quotations_valid_on(SCOPE, "VLX", "HW-1001", DEMO_DAY),
        await catalog.quotations_for_item(SCOPE, "HW-1001"),
        await catalog.quotations(SCOPE),
        await catalog.lme_for_month(SCOPE, "2026-09"),
        await catalog.lme_months(SCOPE),
        await catalog.orders_for_po(SCOPE, "QRL", "QRL-PO-0918-07"),
        await catalog.orders_since(SCOPE, DEMO_DAY),
        await catalog.open_ycbg(SCOPE),
    ]

    assert {read.as_of for read in reads} == {AS_OF}
    assert AS_OF.utcoffset() is not None


async def test_a_snapshot_without_a_timezone_is_refused(catalog: MockSalesCatalog) -> None:
    with pytest.raises(ValueError, match="timezone"):
        await _rebuild(catalog, as_of=datetime(2026, 10, 2, 18, 0))


@pytest.mark.parametrize(
    ("as_of", "emptied"),
    [
        # The day before the newest open YCBG was issued (2026-10-01); every
        # order and LME month is older.
        (datetime(2026, 9, 30, 23, 59, tzinfo=AS_OF.tzinfo), ()),
        # The day before the newest ERP order (2026-09-19), YCBGs left out.
        (datetime(2026, 9, 18, 12, 0, tzinfo=AS_OF.tzinfo), ("open_ycbg",)),
        # The month before the newest LME month (2026-09), dated records left out.
        (datetime(2026, 8, 31, 12, 0, tzinfo=AS_OF.tzinfo), ("open_ycbg", "bravo_orders")),
    ],
    ids=["before_a_ycbg", "before_an_order", "before_an_lme_month"],
)
async def test_a_snapshot_dated_before_its_own_records_is_refused(
    catalog: MockSalesCatalog, as_of: datetime, emptied: tuple[str, ...]
) -> None:
    """``as_of`` is what a case stamps as its check basis: it must be true of
    the data it comes with, not a constant beside it."""
    with pytest.raises(ValueError, match="earlier than a record"):
        await _rebuild(catalog, as_of=as_of, **dict.fromkeys(emptied, ()))


async def test_the_snapshot_was_taken_on_or_after_its_newest_record(
    catalog: MockSalesCatalog,
) -> None:
    newest = max(
        [o.order_date for o in (await catalog.orders_since(SCOPE, date(2000, 1, 1))).data]
        + [y.issued_on for y in (await catalog.open_ycbg(SCOPE)).data]
    )

    assert AS_OF.date() >= newest
    # Exactly on the newest day is still a true snapshot.
    await _rebuild(catalog, as_of=datetime.combine(newest, datetime.min.time(), AS_OF.tzinfo))


async def test_every_customer_is_found_by_its_code_and_each_of_its_domains(
    catalog: MockSalesCatalog,
) -> None:
    customers = (await catalog.customers(SCOPE)).data

    assert customers
    for customer in customers:
        assert (await catalog.customer_by_code(SCOPE, customer.code)).data == customer
        for domain in customer.email_domains:
            assert (await catalog.customer_by_email_domain(SCOPE, domain)).data == customer
            assert (await catalog.customer_by_email_domain(SCOPE, domain.upper())).data == customer


@pytest.mark.parametrize(
    "domain", ["mail.velatrix.example", "velatrix", "evil.example", "seller.example", ""]
)
async def test_a_domain_no_customer_lists_finds_nobody(
    catalog: MockSalesCatalog, domain: str
) -> None:
    """A subdomain is someone else's mailbox until the customer lists it, and the
    seller's own domain is nobody's customer."""
    assert (await catalog.customer_by_email_domain(SCOPE, domain)).data is None


async def test_every_item_and_convert_entry_is_found_by_its_key(catalog: MockSalesCatalog) -> None:
    items = (await catalog.items(SCOPE)).data
    entries = (await catalog.convert_list(SCOPE)).data

    assert items
    assert entries
    for item in items:
        assert (await catalog.item_by_prv_code(SCOPE, item.prv_code)).data == item
    for entry in entries:
        found = await catalog.convert_entry(SCOPE, entry.customer_code, entry.customer_item_code)
        assert found.data == entry
    assert (await catalog.item_by_prv_code(SCOPE, "HW-9999")).data is None


async def test_a_customer_code_maps_only_within_its_customer(catalog: MockSalesCatalog) -> None:
    vlx = (await catalog.convert_entry(SCOPE, "VLX", "PN-1001")).data
    nrv = (await catalog.convert_entry(SCOPE, "NRV", "PN-1001")).data

    assert vlx is not None
    assert nrv is not None
    assert vlx.prv_code != nrv.prv_code
    assert (await catalog.convert_entry(SCOPE, "KMH", "PN-1001")).data is None
    assert (await catalog.convert_entry(SCOPE, "VLX", "pn-1001")).data is None


async def test_every_quotation_is_found_for_its_item_and_on_exactly_its_days(
    catalog: MockSalesCatalog,
) -> None:
    quotations = (await catalog.quotations(SCOPE)).data

    assert quotations
    for quotation in quotations:
        for_item = (await catalog.quotations_for_item(SCOPE, quotation.prv_code)).data
        assert quotation in for_item
        for day, valid in (
            (quotation.valid_from, True),
            (quotation.valid_to, True),
            (quotation.valid_from - timedelta(days=1), False),
            (quotation.valid_to + timedelta(days=1), False),
        ):
            found = (
                await catalog.quotations_valid_on(
                    SCOPE, quotation.customer_code, quotation.prv_code, day
                )
            ).data
            assert (quotation in found) is valid, (quotation.quote_no, day)
            assert all(q.customer_code == quotation.customer_code for q in found)


async def test_every_lme_month_is_found_and_listed_oldest_first(catalog: MockSalesCatalog) -> None:
    months = (await catalog.lme_months(SCOPE)).data

    assert [m.month for m in months] == [f"2025-{m}" for m in ("10", "11", "12")] + [
        f"2026-{m:02d}" for m in range(1, 10)
    ]
    for month in months:
        assert (await catalog.lme_for_month(SCOPE, month.month)).data == month
    assert (await catalog.lme_for_month(SCOPE, "2026-10")).data is None


async def test_every_erp_order_is_found_by_its_po_and_by_its_date(
    catalog: MockSalesCatalog,
) -> None:
    orders = read_records(DATA_DIR / "bravo_orders.json", BravoOrder)

    assert orders
    for order in orders:
        by_po = (await catalog.orders_for_po(SCOPE, order.customer_code, order.po_no)).data
        assert order in by_po
        assert all(o.customer_code == order.customer_code for o in by_po)
        assert order in (await catalog.orders_since(SCOPE, order.order_date)).data
        assert (
            order
            not in (await catalog.orders_since(SCOPE, order.order_date + timedelta(days=1))).data
        )
    assert (await catalog.orders_for_po(SCOPE, "VLX", "QRL-PO-0918-07")).data == ()


async def test_orders_since_are_listed_oldest_first(catalog: MockSalesCatalog) -> None:
    orders = (await catalog.orders_since(SCOPE, date(2000, 1, 1))).data
    reordered = await _rebuild(catalog, bravo_orders=reversed(orders))

    assert [o.order_date for o in orders] == sorted(o.order_date for o in orders)
    assert (await reordered.orders_since(SCOPE, date(2000, 1, 1))).data == orders


async def test_every_open_ycbg_is_listed_oldest_first(catalog: MockSalesCatalog) -> None:
    listed = (await catalog.open_ycbg(SCOPE)).data

    assert sorted(listed, key=lambda y: y.ycbg_no) == sorted(
        read_records(DATA_DIR / "open_ycbg.json", OpenYcbg), key=lambda y: y.ycbg_no
    )
    assert [y.issued_on for y in listed] == sorted(y.issued_on for y in listed)


async def test_the_fixture_holds_what_the_demo_exercises(catalog: MockSalesCatalog) -> None:
    customers = (await catalog.customers(SCOPE)).data
    quotations = (await catalog.quotations(SCOPE)).data
    # The fiscal year turns where the order rules say; April in the shipped policy.
    current_fy = fiscal_year(DEMO_DAY, start_month=4)

    assert [c.code for c in customers if c.intra_group] == ["CVG"]
    lacking = [
        c.code
        for c in customers
        if not c.compliance.noc_confirmed or c.compliance.esf_fiscal_year != current_fy
    ]
    assert lacking == ["BRN"]
    assert [c.code for c in customers if c.compliance.denial_list_checked_on is None] == ["TZ2609"]
    assert [c.code for c in customers if c.status == "temporary"] == ["TZ2609"]
    assert [c.code for c in customers if c.confirmation_channel == "portal"] == ["NRV"]
    assert all(c.sales_pic is not None for c in customers)
    assert any(not q.is_valid_on(DEMO_DAY) for q in quotations)
    assert any(isinstance(q.copper_basis, LmeBand) for q in quotations)
    valid_prices: dict[tuple[str, str], set[Decimal]] = {}
    for q in quotations:
        if q.is_valid_on(DEMO_DAY):
            valid_prices.setdefault((q.prv_code, q.currency), set()).add(q.unit_price)
    assert any(len(prices) > 1 for prices in valid_prices.values()), (
        "no item is quoted to two customers at different prices"
    )


async def test_a_domain_claimed_by_two_customers_is_refused_without_naming_it(
    catalog: MockSalesCatalog,
) -> None:
    customers = list((await catalog.customers(SCOPE)).data)
    impostor = customers[1].model_copy(
        update={"code": "ZZZ", "email_domains": customers[0].email_domains}
    )

    with pytest.raises(ValueError, match="share a domain") as refused:
        await _rebuild(catalog, customers=[*customers, impostor])

    assert customers[0].email_domains[0] not in str(refused.value)


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        (
            ConvertEntry(customer_code="VLX", customer_item_code="X-1", prv_code="HW-9999"),
            "unknown item",
        ),
        (
            ConvertEntry(customer_code="ZZZ", customer_item_code="X-1", prv_code="HW-1001"),
            "unknown customer",
        ),
        (
            ConvertEntry(customer_code="VLX", customer_item_code="PN-1001", prv_code="HW-1001"),
            "appears twice",
        ),
    ],
)
async def test_a_convert_entry_that_cannot_be_resolved_is_refused(
    catalog: MockSalesCatalog, entry: ConvertEntry, message: str
) -> None:
    """At load, so a mapping never silently finds nothing (or two answers)."""
    with pytest.raises(ValueError, match=message):
        await _rebuild(catalog, convert_list=[*(await catalog.convert_list(SCOPE)).data, entry])


@pytest.mark.parametrize(
    ("update", "message"),
    [({"prv_code": "HW-9999"}, "unknown item"), ({"customer_code": "ZZZ"}, "unknown customer")],
)
async def test_a_quotation_that_names_nothing_in_the_catalogue_is_refused(
    catalog: MockSalesCatalog, update: dict[str, str], message: str
) -> None:
    """At load, so a mistyped code fails at startup rather than as a price that
    no line can ever find."""
    quotations = (await catalog.quotations(SCOPE)).data
    stray = Quotation.model_validate(quotations[0].model_dump() | {"quote_no": "Q99-0001"} | update)

    with pytest.raises(ValueError, match=message):
        await _rebuild(catalog, quotations=[*quotations, stray])


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"so_no": "SO99-0001", "customer_code": "ZZZ"}, "unknown customer"),
        (
            {
                "so_no": "SO99-0001",
                "lines": [
                    {
                        "line_no": 1,
                        "prv_code": "HW-9999",
                        "quantity": "1",
                        "unit_price": "1",
                        "delivery_date": "2026-10-01",
                    }
                ],
            },
            "unknown item",
        ),
        ({}, "appears twice"),
    ],
    ids=["customer", "item", "so_no_twice"],
)
async def test_an_erp_order_that_names_nothing_in_the_catalogue_is_refused(
    catalog: MockSalesCatalog, update: dict[str, Any], message: str
) -> None:
    orders = (await catalog.orders_since(SCOPE, date(2000, 1, 1))).data
    stray = BravoOrder.model_validate(orders[0].model_dump() | update)

    with pytest.raises(ValueError, match=message):
        await _rebuild(catalog, bravo_orders=[*orders, stray])


async def test_an_open_ycbg_for_an_unknown_customer_is_refused(catalog: MockSalesCatalog) -> None:
    ycbg = (await catalog.open_ycbg(SCOPE)).data
    stray = OpenYcbg.model_validate(
        ycbg[0].model_dump() | {"ycbg_no": "YC-0", "customer_code": "ZZZ"}
    )

    with pytest.raises(ValueError, match="unknown customer"):
        await _rebuild(catalog, open_ycbg=[*ycbg, stray])


async def test_lme_months_are_listed_oldest_first_whatever_order_they_are_given_in(
    catalog: MockSalesCatalog,
) -> None:
    """The port's promise rather than the fixture file's, whose months are in order."""
    months = (await catalog.lme_months(SCOPE)).data
    given_newest_first = await _rebuild(catalog, lme=reversed(months))

    assert (await given_newest_first.lme_months(SCOPE)).data == months


class _Unguarded(BaseModel):
    """A fixture model that does not hide its input, as the inbox's and the
    documents' own fixture models do not: `read_records` is their guard."""

    code: str = Field(pattern=r"^[A-Z]{3}$")


@pytest.mark.parametrize("model", [_Unguarded, Customer], ids=["unguarded", "customer"])
def test_a_fixture_record_that_fails_names_its_place_and_field_never_its_value(
    tmp_path: Path, model: type[BaseModel]
) -> None:
    """Spec decision 8: these files stand in for a customer's data."""
    record = json.loads((DATA_DIR / "customers.json").read_text(encoding="utf-8"))[0]
    record["code"] = "secret-code"
    record["sales_pic"] = "secret-pic"
    broken = tmp_path / "customers.json"
    broken.write_text(json.dumps([record]), encoding="utf-8")

    with pytest.raises(ValueError, match=r"customers\.json\[0\]") as refused:
        read_records(broken, model)

    message = str(refused.value)
    assert "code" in message
    assert "secret" not in message
    assert refused.value.__cause__ is None

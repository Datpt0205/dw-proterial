"""`MockSalesCatalog`: every fixture record read back through `SalesCatalogPort`."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.mock import MockSalesCatalog
from dw_sales.application.ports import SalesCatalogPort, SalesScope
from dw_sales.domain.catalog import ConvertEntry, LmeBand, Quotation, fiscal_year

pytestmark = pytest.mark.unit

SCOPE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
# The day the demo's mailbox is read: every PO in it is dated September 2026.
DEMO_DAY = date(2026, 9, 30)


@pytest.fixture(scope="module")
def catalog() -> MockSalesCatalog:
    return MockSalesCatalog.load()


def test_the_mock_satisfies_the_port(catalog: MockSalesCatalog) -> None:
    # The check is mypy's: this assignment fails typecheck when a signature drifts.
    port: SalesCatalogPort = catalog
    assert port is catalog


async def test_every_customer_is_found_by_its_code_and_each_of_its_domains(
    catalog: MockSalesCatalog,
) -> None:
    customers = await catalog.customers(SCOPE)

    assert customers
    for customer in customers:
        assert await catalog.customer_by_code(SCOPE, customer.code) == customer
        for domain in customer.email_domains:
            assert await catalog.customer_by_email_domain(SCOPE, domain) == customer
            assert await catalog.customer_by_email_domain(SCOPE, domain.upper()) == customer


@pytest.mark.parametrize("domain", ["mail.velatrix.example", "velatrix", "evil.example", ""])
async def test_a_domain_no_customer_lists_finds_nobody(
    catalog: MockSalesCatalog, domain: str
) -> None:
    """A subdomain is someone else's mailbox until the customer lists it."""
    assert await catalog.customer_by_email_domain(SCOPE, domain) is None


async def test_every_item_and_convert_entry_is_found_by_its_key(catalog: MockSalesCatalog) -> None:
    items = await catalog.items(SCOPE)
    entries = await catalog.convert_list(SCOPE)

    assert items
    assert entries
    for item in items:
        assert await catalog.item_by_prv_code(SCOPE, item.prv_code) == item
    for entry in entries:
        found = await catalog.convert_entry(SCOPE, entry.customer_code, entry.customer_item_code)
        assert found == entry
    assert await catalog.item_by_prv_code(SCOPE, "HW-9999") is None


async def test_a_customer_code_maps_only_within_its_customer(catalog: MockSalesCatalog) -> None:
    vlx = await catalog.convert_entry(SCOPE, "VLX", "PN-1001")
    nrv = await catalog.convert_entry(SCOPE, "NRV", "PN-1001")

    assert vlx is not None
    assert nrv is not None
    assert vlx.prv_code != nrv.prv_code
    assert await catalog.convert_entry(SCOPE, "KMH", "PN-1001") is None
    assert await catalog.convert_entry(SCOPE, "VLX", "pn-1001") is None


async def test_every_quotation_is_found_for_its_item_and_on_exactly_its_days(
    catalog: MockSalesCatalog,
) -> None:
    quotations = await catalog.quotations(SCOPE)

    assert quotations
    for quotation in quotations:
        for_item = await catalog.quotations_for_item(SCOPE, quotation.prv_code)
        assert quotation in for_item
        for day, valid in (
            (quotation.valid_from, True),
            (quotation.valid_to, True),
            (quotation.valid_from - timedelta(days=1), False),
            (quotation.valid_to + timedelta(days=1), False),
        ):
            found = await catalog.quotations_valid_on(
                SCOPE, quotation.customer_code, quotation.prv_code, day
            )
            assert (quotation in found) is valid, (quotation.quote_no, day)
            assert all(q.customer_code == quotation.customer_code for q in found)


async def test_every_lme_month_is_found_and_listed_oldest_first(catalog: MockSalesCatalog) -> None:
    months = await catalog.lme_months(SCOPE)

    assert [m.month for m in months] == [f"2025-{m}" for m in ("10", "11", "12")] + [
        f"2026-{m:02d}" for m in range(1, 10)
    ]
    for month in months:
        assert await catalog.lme_for_month(SCOPE, month.month) == month
    assert await catalog.lme_for_month(SCOPE, "2026-10") is None


async def test_the_fixture_holds_what_the_demo_exercises(catalog: MockSalesCatalog) -> None:
    customers = await catalog.customers(SCOPE)
    quotations = await catalog.quotations(SCOPE)
    current_fy = fiscal_year(DEMO_DAY)

    assert [c.code for c in customers if c.intra_group] == ["CVG"]
    lacking = [
        c.code
        for c in customers
        if not c.compliance.noc_confirmed or c.compliance.esf_fiscal_year != current_fy
    ]
    assert lacking == ["BRN"]
    assert any(not q.is_valid_on(DEMO_DAY) for q in quotations)
    assert any(isinstance(q.copper_basis, LmeBand) for q in quotations)
    valid_prices: dict[tuple[str, str], set[Decimal]] = {}
    for q in quotations:
        if q.is_valid_on(DEMO_DAY):
            valid_prices.setdefault((q.prv_code, q.currency), set()).add(q.unit_price)
    assert any(len(prices) > 1 for prices in valid_prices.values()), (
        "no item is quoted to two customers at different prices"
    )


async def test_a_domain_claimed_by_two_customers_is_refused(catalog: MockSalesCatalog) -> None:
    customers = list(await catalog.customers(SCOPE))
    impostor = customers[1].model_copy(update={"email_domains": customers[0].email_domains})

    with pytest.raises(ValueError, match="belongs to"):
        MockSalesCatalog(
            customers=[*customers, impostor.model_copy(update={"code": "ZZZ"})],
            items=await catalog.items(SCOPE),
            convert_list=await catalog.convert_list(SCOPE),
            quotations=await catalog.quotations(SCOPE),
            lme=await catalog.lme_months(SCOPE),
        )


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
        MockSalesCatalog(
            customers=await catalog.customers(SCOPE),
            items=await catalog.items(SCOPE),
            convert_list=[*await catalog.convert_list(SCOPE), entry],
            quotations=await catalog.quotations(SCOPE),
            lme=await catalog.lme_months(SCOPE),
        )


@pytest.mark.parametrize(
    ("update", "message"),
    [({"prv_code": "HW-9999"}, "unknown item"), ({"customer_code": "ZZZ"}, "unknown customer")],
)
async def test_a_quotation_that_names_nothing_in_the_catalogue_is_refused(
    catalog: MockSalesCatalog, update: dict[str, str], message: str
) -> None:
    """At load, so a mistyped code fails at startup rather than as a price that
    no line can ever find."""
    quotations = await catalog.quotations(SCOPE)
    stray = Quotation.model_validate(quotations[0].model_dump() | {"quote_no": "Q99-0001"} | update)

    with pytest.raises(ValueError, match=message):
        MockSalesCatalog(
            customers=await catalog.customers(SCOPE),
            items=await catalog.items(SCOPE),
            convert_list=await catalog.convert_list(SCOPE),
            quotations=[*quotations, stray],
            lme=await catalog.lme_months(SCOPE),
        )


async def test_lme_months_are_listed_oldest_first_whatever_order_they_are_given_in(
    catalog: MockSalesCatalog,
) -> None:
    """The port's promise rather than the fixture file's, whose months are in order."""
    months = await catalog.lme_months(SCOPE)
    given_newest_first = MockSalesCatalog(
        customers=await catalog.customers(SCOPE),
        items=await catalog.items(SCOPE),
        convert_list=await catalog.convert_list(SCOPE),
        quotations=await catalog.quotations(SCOPE),
        lme=reversed(months),
    )

    assert await given_newest_first.lme_months(SCOPE) == months

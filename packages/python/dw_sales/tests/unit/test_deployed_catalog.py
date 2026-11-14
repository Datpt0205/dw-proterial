"""Where deployed, nothing fictional answers a check (hardcode audit, finding 1).

`SnapshotSalesCatalog` without a fallback: a list with no approved snapshot,
and the ERP (Bravo) until it is connected, answer `CatalogNotConnectedError`,
never the mock's fiction and never an empty list. A check that can go on
without the source names it on the case among what nobody checked; one that
cannot fails closed. The demo, with the mock behind the lists, is
`test_order_intake.py` and the Sales evals, unchanged.
"""

from __future__ import annotations

import itertools
import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from dw_kernel.ids import TenantId, WorkspaceId
from dw_kernel.ports import FixedClock
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.order_rules import PlatformOrderRules, load_order_rules
from dw_sales.adapters.reader_client import ClientPoReaders, ClientQuoteForms
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.application.message_intent import IntentReader
from dw_sales.application.order_intake import IntakeOutcome, OrderIntake
from dw_sales.application.ports import (
    BRAVO_NOT_CONNECTED,
    CatalogNotConnectedError,
    SalesScope,
)
from dw_sales.application.snapshot_catalog import ApprovedList, SnapshotSalesCatalog
from dw_sales.domain.catalog import Customer
from dw_sales.domain.master_data import CatalogList, CatalogRecord
from dw_sales.domain.orders import FindingCode, OrderCase
from dw_sales.testing.catalog_store import (
    MemoryRecordedConverts,
    MemoryRecordedQuotations,
    MemoryRecordedSenders,
)
from dw_sales.testing.followups import platform_zone

pytestmark = pytest.mark.unit

SCOPE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
RULES = load_order_rules(
    Path(__file__).resolve().parents[5] / "configs" / "policies" / "sales_order_rules@1.6.0.yaml"
)

MOCK = MockSalesCatalog.load(SCOPE)
APPROVED_AT = datetime(2026, 9, 1, tzinfo=UTC)
RECORDED_AT = datetime(2026, 10, 29, tzinfo=UTC)


class NoCases:
    """`OrderCaseLookupPort` holding no case: the message is the first."""

    async def cases_for_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> Sequence[OrderCase]:
        return ()


class Lists:
    """`ApprovedListsPort` holding the lists ``approved`` names, each with the
    sample's rows as if the tenant had imported and approved them."""

    def __init__(self, approved: frozenset[CatalogList]) -> None:
        self.approved_lists = approved

    async def approved(self, scope: SalesScope, catalog_list: CatalogList) -> ApprovedList | None:
        if catalog_list not in self.approved_lists:
            return None
        rows: tuple[CatalogRecord, ...]
        match catalog_list:
            case CatalogList.CUSTOMERS:
                rows = tuple((await MOCK.customers(scope)).data)
            case CatalogList.ITEMS:
                rows = tuple((await MOCK.items(scope)).data)
            case CatalogList.CONVERT_LIST:
                rows = tuple((await MOCK.convert_list(scope)).data)
            case CatalogList.QUOTATIONS:
                rows = tuple((await MOCK.quotations(scope)).data)
            case CatalogList.LME:
                rows = tuple((await MOCK.lme_months(scope)).data)
        return ApprovedList.of(catalog_list, uuid.UUID(int=7), APPROVED_AT, rows)


def _deployed(approved: frozenset[CatalogList] = frozenset(CatalogList)) -> SnapshotSalesCatalog:
    clock = FixedClock(RECORDED_AT)
    return SnapshotSalesCatalog(
        Lists(approved),
        None,
        MemoryRecordedQuotations(clock),
        MemoryRecordedConverts(clock),
        MemoryRecordedSenders(clock),
    )


def _intake(catalog: SnapshotSalesCatalog | MockSalesCatalog) -> OrderIntake:
    ids = itertools.count(1)
    return OrderIntake(
        catalog=catalog,
        inbox=MockInbox.load(SCOPE),
        reader=ClientPoReaders(InProcessReaderTransport()),
        quote_forms=ClientQuoteForms(InProcessReaderTransport()),
        zones=platform_zone(),
        rules=PlatformOrderRules(RULES),
        cases=NoCases(),
        new_case_id=lambda: uuid.UUID(int=next(ids)),
    )


async def _process(
    catalog: SnapshotSalesCatalog | MockSalesCatalog, message_id: str
) -> IntakeOutcome:
    message = await MockInbox.load(SCOPE).get_message(SCOPE, message_id)
    assert message is not None
    return await _intake(catalog).process(SCOPE, message)


@pytest.mark.parametrize("missing", list(CatalogList))
async def test_a_list_with_no_approved_import_is_not_connected_never_the_mock(
    missing: CatalogList,
) -> None:
    catalog = _deployed(frozenset(CatalogList) - {missing})
    reads: dict[CatalogList, Callable[[], Awaitable[object]]] = {
        CatalogList.CUSTOMERS: lambda: catalog.customers(SCOPE),
        CatalogList.ITEMS: lambda: catalog.items(SCOPE),
        CatalogList.CONVERT_LIST: lambda: catalog.convert_list(SCOPE),
        CatalogList.QUOTATIONS: lambda: catalog.quotations(SCOPE),
        CatalogList.LME: lambda: catalog.lme_months(SCOPE),
    }
    with pytest.raises(CatalogNotConnectedError) as refused:
        await reads[missing]()
    assert refused.value.catalog_list is missing
    assert "chưa có danh mục được duyệt" in refused.value.statement


@pytest.mark.parametrize("read", ["orders_for_po", "orders_since", "open_ycbg"])
async def test_the_erp_is_not_connected_never_the_mock_and_never_empty(read: str) -> None:
    catalog = _deployed()
    calls: dict[str, Callable[[], Awaitable[object]]] = {
        "orders_for_po": lambda: catalog.orders_for_po(SCOPE, "VLX", "VLX-PO-2608-0102"),
        "orders_since": lambda: catalog.orders_since(SCOPE, date(2025, 1, 1)),
        "open_ycbg": lambda: catalog.open_ycbg(SCOPE),
    }
    with pytest.raises(CatalogNotConnectedError) as refused:
        await calls[read]()
    assert refused.value.catalog_list is None
    assert refused.value.statement == BRAVO_NOT_CONNECTED


async def test_a_po_bravo_already_holds_is_unchecked_not_passed_where_bravo_is_not_connected() -> (
    None
):
    """M19 repeats an order keyed in Bravo by hand: on the mock it is a
    duplicate of SO26-0919. Deployed, nobody can tell, and the case says so."""
    demo = await _process(MOCK, "M19")
    assert demo.case is not None and demo.case.duplicate_of_so == "SO26-0919"

    deployed = await _process(_deployed(), "M19")

    case = deployed.case
    assert case is not None
    assert case.duplicate_of_so is None
    assert BRAVO_NOT_CONNECTED in case.document.unchecked_regions
    assert case.coverage().regions  # the PO itself was still read
    uncertain = [
        f for f in case.findings if f.code is FindingCode.VALUE_UNCERTAIN and f.line_no is None
    ]
    assert uncertain and "unchecked_region" in (uncertain[0].actual or "")


async def test_a_po_read_against_a_missing_list_names_it_and_raises_findings() -> None:
    """No approved quotations or LME: every line's quotation and band are
    findings, and the PO names both lists among what nobody checked."""
    catalog = _deployed(
        frozenset({CatalogList.CUSTOMERS, CatalogList.ITEMS, CatalogList.CONVERT_LIST})
    )

    outcome = await _process(catalog, "M01")

    case = outcome.case
    assert case is not None
    regions = case.document.unchecked_regions
    assert any("Báo giá" in r for r in regions) and any("LME" in r for r in regions)
    codes = {f.code for f in case.findings}
    assert FindingCode.QUOTATION_MISSING in codes


async def test_with_no_approved_customer_list_processing_fails_closed() -> None:
    catalog = _deployed(frozenset(CatalogList) - {CatalogList.CUSTOMERS})

    with pytest.raises(CatalogNotConnectedError) as refused:
        await _process(catalog, "M01")
    assert refused.value.catalog_list is CatalogList.CUSTOMERS


async def test_a_number_resolves_to_nothing_where_bravo_is_not_connected() -> None:
    """A number Bravo might hold as a YCBG or an order cannot be told apart:
    it resolves to nothing, and the message goes to a person."""
    vlx = (await MOCK.customer_by_code(SCOPE, "VLX")).data
    assert isinstance(vlx, Customer)
    demo = IntentReader(None, MOCK, NoCases())  # type: ignore[arg-type]
    deployed = IntentReader(None, _deployed(), NoCases())  # type: ignore[arg-type]
    number = "VLX-PO-2608-0102"

    assert await demo.resolve(SCOPE, vlx, (number,))
    assert await deployed.resolve(SCOPE, vlx, (number,)) == ()

"""The response mappers leave every amount out unless the caller may see it.

Cases read from the mock mailbox as intake reads them, then mapped for a
caller without `sales.price.read`, with it, and with other customers' prices
too. A hidden amount is `{"hidden": true}`: never a zero, never absent, never
a number in the JSON (spec decision 8, ui-quality §6).
"""

from __future__ import annotations

import itertools
import json
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.order_rules import PlatformOrderRules, load_order_rules
from dw_sales.adapters.policy_files import load_pricing, load_quote_rules
from dw_sales.adapters.readers import mock_po_readers
from dw_sales.adapters.rfq_excel import ExcelDesignReplyReader, ExcelRfqReader
from dw_sales.application.access import PriceView
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.ports import SalesScope
from dw_sales.application.quotation import QuotationService, ReplyAttached
from dw_sales.application.views import (
    HIDDEN,
    bravo_order,
    lme_month,
    order_case,
    order_line,
    quotation_row,
    quote_case,
)
from dw_sales.domain.catalog import LmeBand, LmeMonth
from dw_sales.domain.orders import OrderCase
from dw_sales.domain.quotes import LinePrice, PricingDecision, QuoteCase

pytestmark = pytest.mark.unit

SCOPE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
POLICIES = Path(__file__).resolve().parents[5] / "configs" / "policies"
NONE = PriceView(amounts=False, other_customers=False)
OWN = PriceView(amounts=True, other_customers=False)
ALL = PriceView(amounts=True, other_customers=True)
AT = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
PRICER = uuid.UUID(int=0xD1)


class _Kept:
    """The order cases opened so far: what a revision is recognised against."""

    def __init__(self) -> None:
        self.cases: dict[uuid.UUID, OrderCase] = {}

    async def cases_for_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> Sequence[OrderCase]:
        return [
            c
            for c in self.cases.values()
            if (c.customer_code, c.header.po_no) == (customer_code, po_no)
        ]


class _NoCases:
    async def cases_for_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> Sequence[OrderCase]:
        return ()

    async def cases_for_ycbg(self, scope: SalesScope, ycbg_no: str) -> Sequence[QuoteCase]:
        return [CASES[ycbg_no]] if ycbg_no in CASES else []


CASES: dict[str, QuoteCase] = {}


_IDS = itertools.count(1)


async def _order(message_id: str, kept: _Kept | None = None) -> OrderCase:
    inbox = MockInbox.load(SCOPE)
    intake = OrderIntake(
        catalog=MockSalesCatalog.load(SCOPE),
        inbox=inbox,
        reader=mock_po_readers(),
        rules=PlatformOrderRules(load_order_rules(POLICIES / "sales_order_rules@1.0.0.yaml")),
        cases=kept if kept is not None else _NoCases(),
        new_case_id=lambda: uuid.UUID(int=next(_IDS)),
    )
    message = await inbox.get_message(SCOPE, message_id)
    assert message is not None
    outcome = await intake.process(SCOPE, message)
    assert outcome.case is not None
    if kept is not None:
        kept.cases[outcome.case.case_id] = outcome.case
    return outcome.case


def _numbers(body: object) -> list[object]:
    """Every JSON number in a body: an amount the mapper let through would be one."""
    if isinstance(body, dict):
        return [n for value in body.values() for n in _numbers(value)]
    if isinstance(body, list):
        return [n for value in body for n in _numbers(value)]
    return [body] if isinstance(body, (int, float)) and not isinstance(body, bool) else []


async def test_an_orders_amounts_are_hidden_without_the_price_scope() -> None:
    case = await _order("M04")

    view = order_case(case, assigned_to=None, release_manifest_ref=None, prices=NONE)
    dumped = view.model_dump(mode="json")

    for line in dumped["lines"]:
        assert line["unit_price"] == {"hidden": True}
        assert line["amount"] == {"hidden": True}
        quotation = line["basis"]["quotation"]
        if quotation is not None:
            assert quotation["unit_price"] == {"hidden": True}
    (mismatch,) = [f for f in dumped["findings"] if f["code"] == "price_mismatch"]
    assert (mismatch["expected"], mismatch["actual"]) == ({"hidden": True},) * 2
    # A finding that compares no amount keeps its values.
    (unmapped,) = [f for f in dumped["findings"] if f["code"] == "code_unmapped"]
    assert unmapped["expected"] != {"hidden": True} or unmapped["expected"] is None
    assert "0.658" not in json.dumps(dumped)
    assert _numbers(dumped) == [n for n in _numbers(dumped) if isinstance(n, int)]


async def test_the_same_order_shows_its_amounts_to_a_price_reader() -> None:
    case = await _order("M04")

    dumped = order_case(case, assigned_to=None, release_manifest_ref=None, prices=OWN).model_dump(
        mode="json"
    )

    assert Decimal(dumped["lines"][1]["unit_price"]) == Decimal("0.6580")
    (mismatch,) = [f for f in dumped["findings"] if f["code"] == "price_mismatch"]
    assert mismatch["actual"] != {"hidden": True}


async def test_an_lme_band_and_figure_are_hidden_with_the_prices() -> None:
    case = await _order("M02")

    dumped = order_case(case, assigned_to=None, release_manifest_ref=None, prices=NONE).model_dump(
        mode="json"
    )

    line = next(line for line in dumped["lines"] if line["line_no"] == 11)
    band = line["basis"]["quotation"]["copper_basis"]
    assert band["kind"] == "lme_band"
    assert band["low_usd_per_tonne"] == band["high_usd_per_tonne"] == {"hidden": True}
    assert line["basis"]["lme"]["usd_per_tonne"] == {"hidden": True}
    (finding,) = [f for f in dumped["findings"] if f["code"] == "lme_band_mismatch"]
    assert finding["expected"] == {"hidden": True}


async def test_a_revision_s_changed_prices_are_hidden_and_its_quantities_are_not() -> None:
    cases = _Kept()
    await _order("M04", cases)
    revised = await _order("M07", cases)
    assert revised.changes, "M07 revises M04 in the same case"

    dumped = order_case(
        revised, assigned_to=None, release_manifest_ref=None, prices=NONE
    ).model_dump(mode="json")

    prices = [c for c in dumped["changes"] if c["field"] == "unit_price"]
    assert prices and all(c["before"] == c["after"] == {"hidden": True} for c in prices)
    others = [c for c in dumped["changes"] if c["field"] not in ("unit_price", "amount")]
    assert all(c["before"] != {"hidden": True} or c["before"] is None for c in others)


async def test_master_data_quotations_need_both_price_scopes() -> None:
    quotation = (await MockSalesCatalog.load(SCOPE).quotations(SCOPE)).data[0]

    # The master-data list holds every customer's prices.
    assert quotation_row(quotation, OWN.other_customers).unit_price == HIDDEN
    assert quotation_row(quotation, ALL.other_customers).unit_price == quotation.unit_price


async def test_an_lme_month_and_an_erp_order_line_hide_their_figures() -> None:
    lme = LmeMonth(month="2026-09", usd_per_tonne=Decimal(10870))
    assert lme_month(lme, False).usd_per_tonne == HIDDEN
    assert lme_month(lme, True).usd_per_tonne == Decimal(10870)
    orders = (await MockSalesCatalog.load(SCOPE).orders_since(SCOPE, date(2025, 1, 1))).data
    assert orders
    assert all(line.unit_price == HIDDEN for line in bravo_order(orders[0], False).lines)


async def _m10_priced() -> tuple[QuoteCase, QuotationService]:
    catalog = MockSalesCatalog.load(SCOPE)
    service = QuotationService(
        catalog=catalog,
        inbox=MockInbox.load(SCOPE),
        rfq_reader=ExcelRfqReader(),
        reply_reader=ExcelDesignReplyReader(),
        cases=_NoCases(),
        ledger=catalog,
        rules=load_quote_rules(POLICIES / "sales_quote_rules@1.1.0.yaml"),
        pricing=load_pricing(POLICIES / "sales_pricing@1.0.0.yaml"),
    )
    case = await service.open_case(SCOPE, "M10", uuid.UUID(int=7))
    waiting = case.draft_ycbg().record_ycbg("YCBG-2609-030", by=PRICER, at=AT).send_to_design()
    CASES["YCBG-2609-030"] = waiting
    outcome = await service.take_design_reply(SCOPE, "M25")
    assert isinstance(outcome, ReplyAttached)
    decision = PricingDecision(
        decided_by=PRICER,
        decided_at=AT,
        lme=LmeMonth(month="2026-09", usd_per_tonne=Decimal(10870)),
        lines=(
            LinePrice(
                line_no=1,
                unit_price=Decimal("0.6890"),
                moq=Decimal(3000),
                lead_time_days=45,
                copper_basis=LmeBand(
                    low_usd_per_tonne=Decimal(10500), high_usd_per_tonne=Decimal(11000)
                ),
            ),
        ),
        management_guidance="Giữ dưới 0.70 theo chỉ đạo",
    )
    return await service.decide_price(SCOPE, outcome.case, decision, by=PRICER), service


async def test_a_quote_carries_no_amount_and_no_evidence_without_the_price_scope() -> None:
    case, service = await _m10_priced()
    evidence = await service.price_evidence(SCOPE, case, as_of=date(2026, 10, 2))

    view = quote_case(
        case,
        assigned_to=None,
        release_manifest_ref=None,
        today=date(2026, 10, 2),
        prices=NONE,
        evidence_rows=evidence,
    ).model_dump(mode="json")

    assert view["evidence"] == {"hidden": True}
    assert view["lines"][0]["target_price"] == {"hidden": True}
    assert view["pricing"]["lines"][0]["unit_price"] == {"hidden": True}
    assert view["pricing"]["management_guidance"] == {"hidden": True}
    assert view["pricing"]["lme"]["usd_per_tonne"] == {"hidden": True}
    for finding in view["findings"]:
        assert finding["expected"] in (None, {"hidden": True})
        assert finding["actual"] in (None, {"hidden": True})
    assert "0.6890" not in json.dumps(view) and "0.65" not in json.dumps(view)
    assert all(not isinstance(n, float) for n in _numbers(view))


async def test_another_customers_prices_need_their_own_scope() -> None:
    case, service = await _m10_priced()
    evidence = await service.price_evidence(SCOPE, case, as_of=date(2026, 10, 2))

    own = quote_case(
        case,
        assigned_to=None,
        release_manifest_ref=None,
        today=date(2026, 10, 2),
        prices=OWN,
        evidence_rows=evidence,
    ).model_dump(mode="json")
    every = quote_case(
        case,
        assigned_to=None,
        release_manifest_ref=None,
        today=date(2026, 10, 2),
        prices=ALL,
        evidence_rows=evidence,
    ).model_dump(mode="json")

    (own_line,), (every_line,) = own["evidence"], every["evidence"]
    assert own_line["other_customers"] == {"hidden": True}
    assert own_line["reference_price"] == {"hidden": True}
    assert isinstance(every_line["other_customers"], list) and every_line["other_customers"]
    assert own["pricing"]["lines"][0]["unit_price"] == "0.6890"


async def test_a_zero_price_is_shown_as_zero_and_hidden_as_hidden() -> None:
    case = await _order("M01")
    line = case.lines[0]
    free = line.model_copy(
        update={"po_line": line.po_line.model_copy(update={"unit_price": Decimal(0)})}
    )

    assert order_line(case, free, OWN).unit_price == Decimal(0)
    assert order_line(case, free, NONE).unit_price == HIDDEN

"""Ticket 05: a quote case is mass or pcs, and a pcs case is priced only once
the price GM/BC Manager decided on the cost sheet is recorded (Box B49:
"xin giá pcs từ JP": JP & HQ ask, the GM at PRV decides on a cost sheet of
raw material, manufacturing, transport, SGA, loyalty and profit). The
request to the GM is drafted from the case's facts only: every price cell
blank, never a figure the case does not hold."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from dw_kernel.errors import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from dw_sales.application.quotes_service import PricedLine
from dw_sales.application.views import HIDDEN
from dw_sales.domain.catalog import LmeBand
from dw_sales.domain.quotes import (
    PcsPrice,
    PcsPriceLine,
    QuoteCase,
    pcs_price_request,
)
from dw_sales.evals.graders import CALLERS, DIEU, OUTSIDER, READER
from dw_sales.evals.world import BETA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
AT = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS)


async def _case() -> QuoteCase:
    world = _world()
    seen = await world.process_each(DIEU, ["M10"])
    case_id = seen["M10"][0].case_id
    assert case_id is not None
    return world.quote(case_id)


def _price(case: QuoteCase, price: str = "12.40") -> PcsPrice:
    return PcsPrice(
        lines=tuple(
            PcsPriceLine(line_no=n, unit_price=Decimal(price))
            for n in sorted(case.request.document.line_numbers())
        ),
        recorded_by=DIEU.user_id,
        recorded_at=AT,
    )


async def test_a_case_is_marked_pcs_by_a_person_and_back_to_mass_drops_the_gm_price() -> None:
    case = await _case()
    assert case.production_type is None

    pcs = case.set_production_type("pcs", by=DIEU.user_id, at=AT)
    priced = pcs.record_pcs_price(_price(pcs))
    mass = priced.set_production_type("mass", by=DIEU.user_id, at=AT)

    assert (pcs.production_type, pcs.case_version) == ("pcs", case.case_version + 1)
    assert priced.pcs_price is not None
    assert (mass.production_type, mass.pcs_price) == ("mass", None)


async def test_a_gm_price_is_for_a_pcs_case_and_names_every_line_once() -> None:
    case = await _case()

    with pytest.raises(ConflictError):
        case.record_pcs_price(_price(case))
    pcs = case.set_production_type("pcs", by=DIEU.user_id, at=AT)
    with pytest.raises(DomainError):
        pcs.record_pcs_price(
            PcsPrice(
                lines=(PcsPriceLine(line_no=99, unit_price=Decimal(1)),),
                recorded_by=DIEU.user_id,
                recorded_at=AT,
            )
        )


async def test_a_pcs_case_waits_for_the_gm_price_before_sales_prices_it() -> None:
    """Acceptance 1, at the case."""
    case = (await _case()).set_production_type("pcs", by=DIEU.user_id, at=AT)

    assert case.waits_on_pcs_price
    with pytest.raises(ConflictError, match="GM"):
        case.require_pcs_price()
    assert not case.record_pcs_price(_price(case)).waits_on_pcs_price


async def test_the_request_to_the_gm_holds_the_cases_facts_and_no_figure() -> None:
    """Acceptance 2: every price cell blank; quantities and units are the
    request's own."""
    case = (await _case()).set_production_type("pcs", by=DIEU.user_id, at=AT)

    sheet = pcs_price_request(case)

    items = {item.line_no: item for item in case.request.document.items}
    assert [row.line_no for row in sheet.rows] == sorted(items)
    for row in sheet.rows:
        assert row.description == items[row.line_no].description.value
        assert row.quantity == items[row.line_no].quantity.value
        assert (row.unit_price, row.total) == (None, None)
    assert sheet.cost_lines == (
        "Raw material total",
        "Manufacturing cost",
        "Transportation costs",
        "SGA",
        "Loyalty",
        "Profit",
        "Grand total",
    )
    assert uuid.UUID(int=0) != DIEU.user_id


# ------------------------------------------- through the quote commands --


def _priced_lines(case: QuoteCase) -> list[PricedLine]:
    return [
        PricedLine(
            line_no=item.line_no,
            unit_price=Decimal("12.40"),
            moq=Decimal(3000),
            lead_time_days=45,
            copper_basis=LmeBand(
                kind="lme_band",
                low_usd_per_tonne=Decimal(10500),
                high_usd_per_tonne=Decimal(11000),
            ),
        )
        for item in case.request.document.items
    ]


async def _designed(world: World) -> uuid.UUID:
    """M10 through YCBG and Design's reply (M25): ready to be priced."""
    seen = await world.process_each(DIEU, ["M10"])
    case_id = seen["M10"][0].case_id
    assert case_id is not None
    commands = world.services.quote_commands
    await commands.ycbg(
        DIEU.context(), case_id, case_version=world.quote(case_id).case_version, ycbg_no=None
    )
    await commands.ycbg(
        DIEU.context(),
        case_id,
        case_version=world.quote(case_id).case_version,
        ycbg_no="RFQ260930-030",
    )
    await commands.design_sent(
        DIEU.context(), case_id, case_version=world.quote(case_id).case_version
    )
    await world.process_each(DIEU, ["M25"])
    return case_id


async def test_sales_cannot_price_a_pcs_case_until_the_gm_price_is_recorded() -> None:
    """Acceptance 1, where the change happens: the price command refuses a
    pcs case with no GM price, and accepts it once Sales recorded one."""
    world = _world()
    case_id = await _designed(world)
    commands = world.services.quote_commands

    def version() -> int:
        return world.quote(case_id).case_version

    await commands.production_type(DIEU.context(), case_id, case_version=version(), kind="pcs")
    with pytest.raises(ConflictError, match="GM"):
        await commands.price(
            DIEU.context(),
            case_id,
            case_version=version(),
            lme_month="2026-09",
            lines=_priced_lines(world.quote(case_id)),
            management_guidance=None,
        )
    assert world.quote(case_id).pricing is None

    await commands.pcs_price(
        DIEU.context(),
        case_id,
        case_version=version(),
        lines=[
            PcsPriceLine(line_no=n, unit_price=Decimal("12.40"))
            for n in sorted(world.quote(case_id).request.document.line_numbers())
        ],
    )
    await commands.price(
        DIEU.context(),
        case_id,
        case_version=version(),
        lme_month="2026-09",
        lines=_priced_lines(world.quote(case_id)),
        management_guidance=None,
    )
    case = world.quote(case_id)
    assert case.pricing is not None
    assert case.pcs_price is not None and case.pcs_price.recorded_by == DIEU.user_id


async def test_a_reader_sees_the_request_to_the_gm_but_sets_and_records_nothing() -> None:
    world = _world()
    case_id = await _designed(world)
    commands = world.services.quote_commands
    version = world.quote(case_id).case_version

    with pytest.raises(PermissionDeniedError):
        await commands.production_type(READER.context(), case_id, case_version=version, kind="pcs")
    with pytest.raises(PermissionDeniedError):
        await commands.pcs_price(
            READER.context(),
            case_id,
            case_version=version,
            lines=[PcsPriceLine(line_no=1, unit_price=Decimal(1))],
        )
    sheet = await world.services.quotes.pcs_price_request(READER.context(), case_id)
    assert [row.line_no for row in sheet.rows] == sorted(
        world.quote(case_id).request.document.line_numbers()
    )


async def test_another_tenants_pic_finds_no_case_to_mark_or_ask_about() -> None:
    world = _world()
    case_id = await _designed(world)
    version = world.quote(case_id).case_version

    with pytest.raises(NotFoundError):
        await world.services.quotes.pcs_price_request(OUTSIDER.context(BETA), case_id)
    with pytest.raises(NotFoundError):
        await world.services.quote_commands.production_type(
            OUTSIDER.context(BETA), case_id, case_version=version, kind="pcs"
        )
    assert world.quote(case_id).production_type is None


async def test_the_case_shows_pcs_and_the_wait_and_the_gm_price_only_to_a_price_reader() -> None:
    world = _world()
    case_id = await _designed(world)
    commands = world.services.quote_commands

    def version() -> int:
        return world.quote(case_id).case_version

    await commands.production_type(DIEU.context(), case_id, case_version=version(), kind="pcs")
    waiting = await world.services.quotes.get(READER.context(), case_id)
    assert (waiting.production_type, waiting.waits_on_pcs_price) == ("pcs", True)
    assert waiting.production_type_set is not None
    assert waiting.production_type_set.by == DIEU.user_id

    await commands.pcs_price(
        DIEU.context(),
        case_id,
        case_version=version(),
        lines=[
            PcsPriceLine(line_no=n, unit_price=Decimal("12.40"))
            for n in sorted(world.quote(case_id).request.document.line_numbers())
        ],
    )
    hidden = await world.services.quotes.get(READER.context(), case_id)
    shown = await world.services.quotes.get(DIEU.context(), case_id)
    assert hidden.pcs_price is not None and shown.pcs_price is not None
    assert not hidden.waits_on_pcs_price
    assert {line.unit_price for line in hidden.pcs_price.lines} == {HIDDEN}
    assert {line.unit_price for line in shown.pcs_price.lines} == {Decimal("12.40")}

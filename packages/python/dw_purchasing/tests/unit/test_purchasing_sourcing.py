"""DW02 function 3: RFQs drafted to the suppliers code picks, offers typed or
read from suppliers' replies, compared by code, chosen by a person within
what the approver approved. Over the in-memory world and the mock data."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from dw_agent_runtime.model.interpretation import ModelUnavailableError
from dw_kernel.errors import (
    ConflictError,
    InfrastructureError,
    NotFoundError,
    PermissionDeniedError,
)
from dw_purchasing.application.access import PurchasingScopes
from dw_purchasing.application.sourcing import RFQ_MAIL, SUPPLIER_QUOTE_READING, OfferForm
from dw_purchasing.domain.cases import CaseStatus
from dw_purchasing.domain.offer_reading import parse_lead_time
from dw_purchasing.domain.sourcing import Choice
from dw_purchasing.testing.world import ALPHA, BETA, World, caller, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
INTAKE = json.loads(
    (REPO / "evals/fixtures/cases/purchasing_pr_intake.json").read_text(encoding="utf-8")
)
SOURCING = json.loads(
    (REPO / "evals/fixtures/cases/purchasing_sourcing.json").read_text(encoding="utf-8")
)
HEAD = uuid.UUID(int=0x4EAD)


def _world(*, offers: dict[str, Any] | None = None, words: dict[str, Any] | None = None) -> World:
    world = open_world(REPO, INTAKE["answers"])
    world.model.by_schema = {
        "ModelOffer": SOURCING["answers"] if offers is None else offers,
        "RfqWording": {"PR-2611-004": SOURCING["rfq_words"]["good"]} if words is None else words,
    }
    return world


async def _approved(world: World, message_id: str = "P01") -> uuid.UUID:
    item = await world.service.read_mail(caller(), message_id)
    assert item.case_id is not None
    await world.approvals.submit(caller(), item.case_id, case_version=1)
    case = await world.service.case(caller(), item.case_id)
    assert case.approval is not None
    world.store.decide(
        case.approval.approval_id,
        tenant_id=ALPHA[0],
        workspace_id=ALPHA[1],
        approved=True,
        decided_by=HEAD,
        at=datetime(2026, 11, 2, 9, tzinfo=UTC),
        comment="ok",
    )
    await world.settlement.settle(case.approval.approval_id, caller(principal=HEAD))
    return item.case_id


async def _drafted(world: World) -> uuid.UUID:
    case_id = await _approved(world)
    await world.sourcing.draft_rfq(caller(), case_id, case_version=3)
    return case_id


async def _version(world: World, case_id: uuid.UUID) -> int:
    return (await world.service.case(caller(), case_id)).case_version


# ---------------------------------------------------------------- the RFQ --


async def test_each_supplier_the_master_data_lists_gets_one_draft_for_its_lines() -> None:
    world = _world()
    case_id = await _drafted(world)

    case = await world.service.case(caller(), case_id)
    assert case.status is CaseStatus.RFQ_DRAFTED and case.rfq is not None
    drafts = {d.supplier_code: d for d in case.rfq.drafts}
    assert {code: d.line_nos for code, d in drafts.items()} == {
        "ANPHAT": (1, 3),
        "BAOHO": (2,),
        "KIMURA": (1,),
    }
    # Recipients are the master data's, never a model's.
    assert drafts["KIMURA"].to == ("sales@kimura-tools.example",)
    assert case.rfq.reply_by == date(2026, 11, 5) and case.rfq.unsourced == ()
    # The model's words where every figure is in the facts and no price named.
    words = {d.supplier_code: d.written_by for d in case.rfq.drafts}
    assert words["KIMURA"] == "model"
    prompts = [call[0] for call in world.model.calls]
    assert prompts.count(RFQ_MAIL) == 3


@pytest.mark.parametrize("variant", ["leaks_price", "invents_figure", "names_amount"])
async def test_words_that_name_a_price_or_invent_a_figure_give_way_to_the_template(
    variant: str,
) -> None:
    world = _world(words={"PR-2611-004": SOURCING["rfq_words"][variant]})
    case_id = await _drafted(world)
    case = await world.service.case(caller(), case_id)
    assert case.rfq is not None
    assert {d.written_by for d in case.rfq.drafts} == {"template"}
    kimura = case.rfq.asked("KIMURA")
    assert kimura is not None and "Dao cắt cáp DC-200: 4 cái" in kimura.body
    assert "1.250.000" not in kimura.body and "trước ngày 05/11/2026" in kimura.body


async def test_without_a_model_every_draft_is_the_template() -> None:
    world = _world()
    case_id = await _approved(world)
    world.model.failure = ModelUnavailableError("down")
    await world.sourcing.draft_rfq(caller(), case_id, case_version=3)
    case = await world.service.case(caller(), case_id)
    assert case.rfq is not None and {d.written_by for d in case.rfq.drafts} == {"template"}


async def test_only_an_approved_request_is_sent_to_suppliers_by_who_may() -> None:
    world = _world()
    item = await world.service.read_mail(caller(), "P01")
    assert item.case_id is not None
    with pytest.raises(ConflictError):
        await world.sourcing.draft_rfq(caller(), item.case_id, case_version=1)
    case_id = await _approved(world, "P02")
    no_scope = caller(scopes=frozenset({PurchasingScopes.REQUEST_READ.value}))
    with pytest.raises(PermissionDeniedError):
        await world.sourcing.draft_rfq(no_scope, case_id, case_version=3)
    with pytest.raises(NotFoundError):
        await world.sourcing.draft_rfq(caller(BETA), case_id, case_version=3)


# -------------------------------------------------------------- the offers --


async def test_a_suppliers_reply_is_read_into_offers_for_the_lines_it_was_asked() -> None:
    world = _world()
    case_id = await _drafted(world)
    for message_id in ("Q01", "Q02", "Q03"):
        version = await _version(world, case_id)
        await world.sourcing.read_offer_mail(caller(), case_id, message_id, case_version=version)

    case = await world.service.case(caller(), case_id)
    got = {(o.supplier_code, o.line_no): (o.unit_price, o.lead_time_days) for o in case.offers}
    assert got == {
        ("KIMURA", 1): (Decimal(1_200_000), 7),
        ("ANPHAT", 1): (Decimal(1_290_000), 3),
        ("ANPHAT", 3): (Decimal(37_500), 5),
        ("BAOHO", 2): (Decimal(98_000), 5),
    }
    kimura = next(o for o in case.offers if o.supplier_code == "KIMURA")
    assert (kimura.valid_until, kimura.source, kimura.source_ref) == (
        date(2026, 11, 30),
        "mail",
        "Q01",
    )
    assert SUPPLIER_QUOTE_READING in [call[0] for call in world.model.calls]
    with pytest.raises(ConflictError):  # read once
        await world.sourcing.read_offer_mail(
            caller(), case_id, "Q01", case_version=await _version(world, case_id)
        )


async def test_a_reply_not_from_a_verified_asked_supplier_is_not_read() -> None:
    world = _world()
    case_id = await _drafted(world)
    calls = len(world.model.calls)
    for message_id, rule in (("Q04", "sender_unverified"), ("P01", "sender_not_asked")):
        with pytest.raises(ConflictError) as refused:
            await world.sourcing.read_offer_mail(caller(), case_id, message_id, case_version=4)
        assert refused.value.details["rule"] == rule
    assert len(world.model.calls) == calls


@pytest.mark.parametrize(
    ("variant", "message_id", "rule"),
    [("invented_price", "Q02", "line_unreadable"), ("item_not_asked", "Q03", "item_not_asked")],
)
async def test_a_price_the_mail_does_not_hold_or_an_item_not_asked_is_not_recorded(
    variant: str, message_id: str, rule: str
) -> None:
    world = _world(offers={**SOURCING["answers"], **SOURCING["variants"][variant]})
    case_id = await _drafted(world)
    with pytest.raises(ConflictError) as refused:
        await world.sourcing.read_offer_mail(caller(), case_id, message_id, case_version=4)
    assert refused.value.details["rule"] == rule
    assert (await world.service.case(caller(), case_id)).offers == ()


async def test_no_model_reads_no_reply_and_records_nothing() -> None:
    world = _world()
    case_id = await _drafted(world)
    world.model.failure = ModelUnavailableError("down")
    with pytest.raises(InfrastructureError):
        await world.sourcing.read_offer_mail(caller(), case_id, "Q01", case_version=4)
    assert (await world.service.case(caller(), case_id)).offers == ()


async def test_a_typed_offer_names_a_known_supplier_and_a_line_of_the_request() -> None:
    world = _world()
    case_id = await _drafted(world)
    form = OfferForm(
        supplier_code="NHUAVIET",
        line_no=2,
        unit_price=Decimal(90_000),
        currency="VND",
        lead_time_days=4,
    )
    await world.sourcing.record_offer(caller(), case_id, form, case_version=4)
    for bad in (
        form.model_copy(update={"supplier_code": "NOBODY"}),
        form.model_copy(update={"line_no": 9}),
    ):
        with pytest.raises(NotFoundError):
            await world.sourcing.record_offer(caller(), case_id, bad, case_version=5)


# --------------------------------------------------------- compare, choose --


async def _offered(world: World) -> uuid.UUID:
    case_id = await _drafted(world)
    for message_id in ("Q01", "Q02", "Q03"):
        version = await _version(world, case_id)
        await world.sourcing.read_offer_mail(caller(), case_id, message_id, case_version=version)
    return case_id


async def test_the_comparison_is_cheapest_first_with_the_need_by_checked() -> None:
    world = _world()
    case_id = await _offered(world)
    view = await world.sourcing.comparison(caller(), case_id)
    first = view.lines[0]
    assert [(o.supplier_code, o.total, o.cheapest) for o in first.offers] == [
        ("KIMURA", Decimal(4_800_000), True),
        ("ANPHAT", Decimal(5_160_000), False),
    ]
    assert all(o.meets_need_by for o in first.offers)
    assert view.approved_limit == Decimal(20_000_000)


async def test_a_person_chooses_one_offer_per_line_within_the_approved_limit() -> None:
    world = _world()
    case_id = await _offered(world)
    choices = [
        Choice(line_no=1, supplier_code="KIMURA"),
        Choice(line_no=2, supplier_code="BAOHO"),
        Choice(line_no=3, supplier_code="ANPHAT"),
    ]
    version = await _version(world, case_id)
    with pytest.raises(ConflictError):  # a line left out
        await world.sourcing.select(caller(), case_id, choices[:2], case_version=version)
    with pytest.raises(ConflictError):  # no such offer
        await world.sourcing.select(
            caller(),
            case_id,
            [Choice(line_no=1, supplier_code="BAOHO"), *choices[1:]],
            case_version=version,
        )
    await world.sourcing.select(caller(), case_id, choices, case_version=version)
    case = await world.service.case(caller(), case_id)
    assert case.status is CaseStatus.SUPPLIER_SELECTED and case.selection is not None
    assert case.selection.total == Decimal(4_800_000 + 4_900_000 + 4_500_000)


async def test_a_choice_past_what_the_approver_approved_is_refused() -> None:
    world = _world()
    case_id = await _offered(world)
    version = await _version(world, case_id)
    pricey = OfferForm(
        supplier_code="NHUAVIET",
        line_no=1,
        unit_price=Decimal(5_000_000),
        currency="VND",
        lead_time_days=2,
    )
    await world.sourcing.record_offer(caller(), case_id, pricey, case_version=version)
    with pytest.raises(ConflictError) as refused:
        await world.sourcing.select(
            caller(),
            case_id,
            [
                Choice(line_no=1, supplier_code="NHUAVIET"),
                Choice(line_no=2, supplier_code="BAOHO"),
                Choice(line_no=3, supplier_code="ANPHAT"),
            ],
            case_version=version + 1,
        )
    assert refused.value.details["rule"] == "exceeds_approved_limit"


async def test_an_expired_or_foreign_currency_offer_is_neither_compared_nor_chosen() -> None:
    world = _world()
    case_id = await _drafted(world)
    for offer in (
        OfferForm(
            supplier_code="KIMURA",
            line_no=1,
            unit_price=Decimal(1),
            currency="VND",
            lead_time_days=1,
            valid_until=date(2026, 11, 1),
        ),
        OfferForm(
            supplier_code="ANPHAT",
            line_no=1,
            unit_price=Decimal(1),
            currency="USD",
            lead_time_days=1,
        ),
    ):
        await world.sourcing.record_offer(
            caller(), case_id, offer, case_version=await _version(world, case_id)
        )
    view = await world.sourcing.comparison(caller(), case_id)
    assert view.lines[0].offers == ()


@pytest.mark.parametrize(
    ("span", "days"), [("7 ngày", 7), ("10 days", 10), ("2 tuần", 14), ("3 ngày, 2 tuần", None)]
)
def test_a_lead_time_is_days_or_weeks_as_written(span: str, days: int | None) -> None:
    assert parse_lead_time(span) == days


def test_at_most_the_rules_number_of_known_suppliers_is_asked_per_line() -> None:
    from dw_purchasing.domain.checks import MasterData, Supplier, SupplierQuote
    from dw_purchasing.domain.requests import PrLine, PurchaseRequest
    from dw_purchasing.domain.sourcing import suppliers_for

    def supplier(code: str) -> Supplier:
        return Supplier(
            code=code,
            name=code,
            domains=frozenset({"x.example"}),
            contacts=("a@x.example",),
            items=frozenset({"IT-1"}),
        )

    master = MasterData(
        suppliers=(supplier("S1"), supplier("S2"), supplier("S3")),
        quotes=(
            SupplierQuote(
                item_code="IT-1",
                supplier_code="GHOST",
                unit_price=Decimal(1),
                currency="VND",
                valid_until=date(2027, 1, 1),
                lead_time_days=1,
            ),
        ),
    )
    request = PurchaseRequest(
        pr_no="PR-1",
        department="Kho",
        requester="An",
        currency="VND",
        lines=(
            PrLine(line_no=1, item_code="IT-1", description="x", quantity=Decimal(1), unit="c"),
            PrLine(line_no=2, item_code="IT-9", description="y", quantity=Decimal(1), unit="c"),
        ),
    )
    asked, unsourced = suppliers_for(request, master, most=2)
    # By code, the first two; a supplier the master data does not list is never asked.
    assert asked == {"S1": [1], "S2": [1]} and unsourced == [2]


async def test_a_sourcing_state_holds_an_approved_decision_only() -> None:
    from pydantic import ValidationError

    world = _world()
    case_id = await _drafted(world)
    case = await world.service.case(caller(), case_id)
    assert case.decision is not None
    rejected = case.decision.model_copy(update={"approved": False})
    with pytest.raises(ValidationError):
        type(case).model_validate({**case.model_dump(), "decision": rejected})

"""Why a requested line of a quotation went the way it did (ticket 62): every
state change has its step, each says who decided, no amount is on it, and it
is read only by whoever may read the case."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import BaseModel

from dw_kernel.errors import NotFoundError
from dw_sales.application.line_trail import QuoteTrailKind
from dw_sales.application.quote_line_trail import quote_line_trail
from dw_sales.domain.activity import StepOutcome
from dw_sales.domain.catalog import FixedCopper
from dw_sales.domain.description_reading import DescriptionReading
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.orders import FlaggedValue
from dw_sales.domain.quotes import (
    Approval,
    Decline,
    DeclineReason,
    DesignCheck,
    DesignCheckLine,
    DesignReply,
    DesignReplyDocument,
    DesignReplyLine,
    FindingAccepted,
    FromOrder,
    LinePrice,
    PcsPrice,
    PcsPriceLine,
    PricingDecision,
    QuoteCase,
    QuoteFinding,
    QuoteFindingCode,
    RequestedItem,
    RequestReading,
    Return,
    SignedCopy,
    Sourced,
    Stamp,
    Submission,
    ValueConfirmation,
    YcbgRecord,
)
from dw_sales.evals.graders import CALLERS, DIEU, GIANG, OUTSIDER
from dw_sales.evals.world import BETA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
AT = datetime(2026, 11, 2, 3, 0, tzinfo=UTC)
PERSON = DIEU.user_id
PRICE = Decimal("12.3456")
PCS_PRICE = Decimal("98.7654")
TARGET = Decimal("45.6789")


def _partial[M: BaseModel](model: type[M], **fields: Any) -> M:
    """Only the fields the trail reads, copied in unvalidated: no real case
    holds every step at once."""
    return model.model_construct(**fields)


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS)


async def _m10(world: World) -> QuoteCase:
    seen = await world.process_each(DIEU, ["M10"])
    case_id = seen["M10"][0].case_id
    assert case_id is not None
    return world.quote(case_id)


def _everything_on(case: QuoteCase, no: int) -> tuple[QuoteCase, list[StepOutcome]]:
    """``case`` with every step a requested line can take set on line ``no``.

    Copied, not validated: no real case holds a decline and an approval at
    once, and the trail must still show each one it is given."""
    request = case.request
    item = request.document.item(no)
    read = item.model_copy(
        update={
            "flags": (FlaggedValue(field="quantity", flag="model_read", confidence=0.9),),
            "candidates": ("PRV-1", "PRV-2"),
            "unsettled": ("needed_by",),
            "target_price": _partial(Sourced, value=TARGET),
            "description_reading": DescriptionReading(
                prompt="sales.description_attributes@1.0.0",
                model_profile="default",
                route="local",
                outcome="unavailable",
            ),
        }
    )
    document = request.document.model_copy(
        update={"items": tuple(read if i.line_no == no else i for i in request.document.items)}
    )
    request = request.model_copy(
        update={
            "document": document,
            "reading": RequestReading(
                prompt="sales.rfq_reading@1.0.0",
                model_profile="default",
                route="local",
                rules="sales_quote_rules@1.0.0",
                calls=1,
            ),
        }
    )
    finding = _partial(
        QuoteFinding,
        code=QuoteFindingCode.VALUE_UNCERTAIN,
        blocking=True,
        line_no=no,
        flagged=("quantity",),
        confirmed=(
            ValueConfirmation(field="quantity", read="1000", value="1000", by=PERSON, at=AT),
        ),
        expected=str(TARGET),
        actual=str(PRICE),
        rule_versions=("sales_quote_rules@1.0.0",),
        disposition=FindingAccepted(by=GIANG.user_id, at=AT, reason="Đã xem"),
    )
    pricing = _partial(
        PricingDecision,
        decided_by=PERSON,
        decided_at=AT,
        lme=None,
        # A decision prices every requested line.
        lines=tuple(
            _partial(
                LinePrice,
                line_no=i.line_no,
                unit_price=PRICE,
                moq=Decimal(1),
                lead_time_days=28,
                copper_basis=FixedCopper(kind="fixed"),
            )
            for i in document.items
        ),
    )
    reply = _partial(
        DesignReply,
        message_id="D01",
        received_at=AT,
        confirmed_by=PERSON,
        document=_partial(
            DesignReplyDocument,
            lines=(
                _partial(DesignReplyLine, line_no=no, bp_code=_partial(Sourced, value="BP000001")),
            ),
        ),
    )
    updated = case.model_copy(
        update={
            "request": request,
            "findings": (finding,),
            "ycbg": YcbgRecord(ycbg_no="RFQ261102-001", recorded_by=PERSON, recorded_at=AT),
            "production_type": "pcs",
            "production_type_set": Stamp(by=PERSON, at=AT),
            "design_replies": (reply,),
            "design_check": _partial(
                DesignCheck,
                ycbg_no="RFQ261102-001",
                read_at=AT,
                read_by=PERSON,
                lines=(_partial(DesignCheckLine, line_no=no, verdict="quote", bp_code="BP1"),),
            ),
            "pricing": pricing,
            "earlier_pricing": (pricing,),
            "pcs_price": _partial(
                PcsPrice,
                lines=(_partial(PcsPriceLine, line_no=no, unit_price=PCS_PRICE),),
                recorded_by=PERSON,
                recorded_at=AT,
            ),
            "submission": _partial(Submission, submitted_by=PERSON, submitted_at=AT),
            "returns": (
                _partial(
                    Return,
                    returned_by=GIANG.user_id,
                    returned_at=AT,
                    reason="Sửa giá",
                    case_version=3,
                ),
            ),
            "approval": _partial(Approval, approved_by=GIANG.user_id, approved_at=AT),
            "sent": Stamp(by=PERSON, at=AT),
            "master_list": Stamp(by=PERSON, at=AT),
            "signed_copy": _partial(SignedCopy, uploaded_by=PERSON, uploaded_at=AT),
            "decline": _partial(
                Decline, declined_by=PERSON, declined_at=AT, reason=DeclineReason.COMMERCIAL
            ),
            "from_order": FromOrder(case_id=uuid.uuid4(), po_no="PO-1"),
        }
    )
    outcome = StepOutcome(
        outcome_id=uuid.uuid4(),
        occurred_at=AT,
        message_id="M10",
        lane=CaseKind.QUOTE,
        case_id=case.case_id,
        line_no=no,
        step=ModelStep.DESCRIPTION_ATTRIBUTES,
        result="accepted",
        automatic=True,
        reason_code=None,
        refusals={},
        prompt="sales.description_attributes@1.0.0",
        model_profile="default",
        model=None,
        calls=1,
        duration_ms=10,
    )
    return updated, [outcome]


async def test_a_line_with_every_step_has_a_step_for_each() -> None:
    case = await _m10(_world())
    updated, outcomes = _everything_on(case, 1)
    trail = quote_line_trail(updated, 1, outcomes)
    by_kind = {s.kind: s for s in trail.steps}
    assert set(by_kind) == set(get_args(QuoteTrailKind))
    assert by_kind["read"].decided_by == "model" and by_kind["read"].value == "quantity"
    assert by_kind["candidates"].value == "PRV-1,PRV-2"
    assert by_kind["value_confirmed"].actor_user_id == PERSON
    assert by_kind["finding_decided"].actor_user_id == GIANG.user_id
    assert by_kind["design_check"].outcome == "quote"
    assert [s.kind for s in trail.steps].count("priced") == 2
    # Design is outside DW: its decisions name no DW user; every other
    # person's step does.
    design = {"design_reply", "design_check"}
    assert all(
        s.actor_user_id is not None
        for s in trail.steps
        if s.decided_by == "person" and s.kind not in design
    )


async def test_another_lines_steps_are_not_on_this_line() -> None:
    case = await _m10(_world())
    # M10 requests one line: a second, copied, carries nothing of line 1's.
    document = case.request.document
    second = document.item(1).model_copy(update={"line_no": 2})
    case = case.model_copy(
        update={
            "request": case.request.model_copy(
                update={
                    "document": document.model_copy(update={"items": (*document.items, second)})
                }
            )
        }
    )
    updated, outcomes = _everything_on(case, 1)
    other = {s.kind for s in quote_line_trail(updated, 2, outcomes).steps}
    assert not other & {"finding", "design_reply", "design_check", "pcs_priced", "candidates"}
    assert "priced" in other  # a decision prices every line


async def test_a_fresh_request_says_it_was_read_and_nobody_decided_yet() -> None:
    case = await _m10(_world())
    trail = quote_line_trail(case, 1, [])
    assert trail.steps[0].kind == "read"
    assert {s.decided_by for s in trail.steps} <= {"rule", "model"}


def test_every_field_of_a_case_and_a_requested_line_is_covered_by_the_trail() -> None:
    """A field added without a step here makes this red: the trail would then
    omit a state change (acceptance 1). Each other entry says why it is not a
    step of its own."""
    case_fields = {
        "case_id": "identity",
        "case_version": "identity",
        "request": "read",
        "rules_version": "stamp: the rules the case opened under",
        "catalog_as_of": "stamp: the master data it opened with",
        "status": "follows from the steps",
        "findings": "finding",
        "ycbg": "ycbg_recorded",
        "design_replies": "design_reply",
        "design_check": "design_check",
        "pricing": "priced",
        "earlier_pricing": "priced",
        "returns": "returned",
        "submission": "submitted",
        "approval": "approved",
        "sent": "quote_sent",
        "master_list": "master_listed",
        "decline": "declined",
        "signed_copy": "signed_copy",
        "from_order": "read",
        "production_type": "production_type",
        "production_type_set": "production_type",
        "pcs_price": "pcs_priced",
    }
    line_fields = {
        "line_no": "identity",
        "customer_item_code": "read",
        "description": "read",
        "quantity": "read",
        "uom": "read",
        "needed_by": "read",
        "flags": "read",
        "target_price": "an amount: never on a step",
        "stated_target_price": "an amount: never on a step",
        "candidates": "candidates",
        "description_reading": "model_reading",
        "unsettled": "unsettled",
    }
    assert set(QuoteCase.model_fields) == set(case_fields)
    assert set(RequestedItem.model_fields) == set(line_fields)


async def test_no_amount_reaches_a_step() -> None:
    world = _world()
    case = await _m10(world)
    updated, outcomes = _everything_on(case, 1)
    text = quote_line_trail(updated, 1, outcomes).model_dump_json()
    text += (
        await world.services.quotes.line_trail(GIANG.context(), case.case_id, 1)
    ).model_dump_json()
    for amount in (PRICE, PCS_PRICE, TARGET):
        assert str(amount) not in text
    for item in case.request.document.items:
        for price in (item.target_price, item.stated_target_price):
            if price is not None:
                assert str(price.value) not in text


async def test_the_trail_is_read_through_the_cases_own_gate() -> None:
    world = _world()
    case = await _m10(world)
    trail = await world.services.quotes.line_trail(DIEU.context(), case.case_id, 1)
    assert trail.line_no == 1 and trail.steps[0].kind == "read"
    # Another tenant names the case and line: not found, nothing else.
    with pytest.raises(NotFoundError):
        await world.services.quotes.line_trail(OUTSIDER.context(BETA), case.case_id, 1)
    # A person who may not see the case in a restricted tenant: not found.
    restricted = GIANG.context().model_copy(
        update={
            "record_visibility": "restricted",
            "visible_owners": frozenset({uuid.UUID(int=0xFEED)}),
        }
    )
    await world.services.assignment.reassign(
        GIANG.context(),
        CaseKind.QUOTE,
        case.case_id,
        assignee=DIEU.user_id,
        case_version=case.case_version,
    )
    with pytest.raises(NotFoundError):
        await world.services.quotes.line_trail(restricted, case.case_id, 1)
    # A line the request does not have.
    with pytest.raises(NotFoundError):
        await world.services.quotes.line_trail(DIEU.context(), case.case_id, 99)

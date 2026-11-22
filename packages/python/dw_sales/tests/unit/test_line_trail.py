"""Why a PO line went the way it did (ticket 62): every state change has its
step, each says who decided, no amount is on it, and it is read only by
whoever may read the case."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import get_args

import pytest

from dw_kernel.errors import NotFoundError
from dw_sales.application.autonomy import applied_by
from dw_sales.application.bravo_line_writes import BravoLineWrite
from dw_sales.application.line_trail import OrderTrailKind, line_trail
from dw_sales.domain.activity import StepOutcome
from dw_sales.domain.description_reading import DescriptionReading
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.orders import (
    Accepted,
    AppliedChange,
    DesignRequest,
    FindingCode,
    LineMapping,
    MappingStatus,
    OrderCase,
    OrderLine,
    PcAnswer,
    PcDelivery,
    PcRequest,
    ValueCorrection,
)
from dw_sales.evals.graders import AN, CALLERS, GIANG, OUTSIDER
from dw_sales.evals.world import ALPHA, BETA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
AT = datetime(2026, 11, 2, 3, 0, tzinfo=UTC)
PERSON = AN.user_id


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS)


async def _m06(world: World) -> OrderCase:
    """M06: line 3 is requested before its lead time allows."""
    ((_, case),) = (await world.process_each(AN, ["M06"])).values()
    assert isinstance(case, OrderCase)
    return world.order(case.case_id)


def _everything_on(case: OrderCase, no: int) -> tuple[OrderCase, list[StepOutcome]]:
    """``case`` with every decision a line can carry set on line ``no``."""
    line = case.line(no)
    code = line.mapping.checked_against or line.basis.convert_prv_code or "PRV-1"
    decided = line.model_copy(
        update={
            "mapping": LineMapping(
                status=MappingStatus.CANDIDATE_CONFIRMED,
                prv_code=code,
                candidates=(code,),
                confirmed_by=PERSON,
                confirmed_at=AT,
            ),
            "basis": line.basis.model_copy(update={"convert_prv_code": code}),
            "corrections": (ValueCorrection(field="quantity", value="12", by=PERSON, at=AT),),
            "changes": (
                AppliedChange(
                    field="requested_date",
                    value="2026-12-01",
                    request_id=uuid.uuid4(),
                    by=PERSON,
                    at=AT,
                ),
            ),
            "pc_confirmed_by": PERSON,
            "pc_confirmed_at": AT,
            "pc_answer": PcAnswer(
                deliveries=(
                    PcDelivery(
                        quantity=line.po_line.quantity,
                        first_date=date(2026, 12, 1),
                        date=date(2026, 12, 1),
                    ),
                ),
                by=PERSON,
                at=AT,
            ),
            "confirmed_delivery_dates": (date(2026, 12, 1),),
        }
    )
    # A model was asked to read the description and gave no usable answer:
    # a reading of its own, whatever the sample's lines hold.
    reading = DescriptionReading(
        prompt="sales.description_attributes@1.0.0",
        model_profile="default",
        route="local",
        outcome="unavailable",
    )
    decided = decided.model_copy(
        update={"basis": decided.basis.model_copy(update={"description_reading": reading})}
    )
    findings = tuple(
        f.model_copy(update={"disposition": Accepted(reason="Khách đồng ý", by=PERSON, at=AT)})
        if f.line_no == no
        else f
        for f in case.findings
    )
    updated = case.model_copy(
        update={
            "lines": tuple(decided if x.po_line.line_no == no else x for x in case.lines),
            "findings": findings,
            "pc_request": PcRequest(lines=(no,), by=PERSON, at=AT),
            "design_requests": (DesignRequest(line_no=no, by=PERSON, at=AT),),
            "bravo_so_no": "SO2611-000001",
            "bravo_recorded_by": PERSON,
            "bravo_recorded_at": AT,
            "cross_checked_by": GIANG.user_id,
            "cross_checked_at": AT,
            "confirmed_by": PERSON,
            "confirmed_at": AT,
        }
    )
    outcome = StepOutcome(
        outcome_id=uuid.uuid4(),
        occurred_at=AT,
        message_id="M06",
        lane=CaseKind.ORDER,
        case_id=case.case_id,
        line_no=no,
        step=ModelStep.SALESORDER_SKILL,
        result="accepted",
        automatic=True,
        reason_code=None,
        refusals={},
        prompt="sales.salesorder_fill@1.0.0",
        model_profile="default",
        model=None,
        calls=1,
        duration_ms=10,
    )
    return updated, [outcome]


def _written(case: OrderCase, no: int) -> BravoLineWrite:
    """A confirmed date written into Bravo for line ``no`` (ticket 53)."""
    return BravoLineWrite(
        approval_id=uuid.uuid4(),
        case_id=case.case_id,
        line_no=no,
        so_no="SO2611-000001",
        item_code="PRV-1",
        field="confirmed_date",
        before=None,
        after="2026-12-01",
        kind="so.line.set_confirmed_date@1",
        command={},
        content_hash="0" * 64,
        status="written",
        proposed_by=PERSON,
        proposed_at=AT,
        decided_by=GIANG.user_id,
        settled_at=AT,
    )


async def test_a_line_with_every_decision_has_a_step_for_each() -> None:
    world = _world()
    case = await _m06(world)
    updated, outcomes = _everything_on(case, 3)
    trail = line_trail(updated, 3, outcomes, [_written(case, 3), _written(case, 1)])
    kinds = {s.kind for s in trail.steps}
    assert kinds == set(get_args(OrderTrailKind))
    writes = [s for s in trail.steps if s.kind == "bravo_write"]
    assert [(s.outcome, s.actor_user_id) for s in writes] == [
        ("proposed", PERSON),
        ("written", GIANG.user_id),
    ]
    by_kind = {s.kind: s for s in trail.steps}
    assert by_kind["read"].decided_by == "rule"
    assert by_kind["convert"].decided_by == "rule"
    assert by_kind["model_reading"].decided_by == "model"
    assert by_kind["finding"].code == FindingCode.REQUESTED_DATE_SHORT_LT.value
    assert by_kind["finding_decided"].actor_user_id == PERSON
    assert by_kind["cross_checked"].actor_user_id == GIANG.user_id
    assert all(s.actor_user_id is not None for s in trail.steps if s.decided_by == "person")


async def test_the_order_page_reads_a_lines_bravo_writes_from_where_they_are_kept() -> None:
    world = _world()
    case = await _m06(world)
    write = _written(case, 3)
    world.store.state(ALPHA).bravo_writes[write.approval_id] = write
    trail = await world.services.orders.line_trail(AN.context(), case.case_id, 3)
    assert [s.outcome for s in trail.steps if s.kind == "bravo_write"] == ["proposed", "written"]
    other = await world.services.orders.line_trail(AN.context(), case.case_id, 1)
    assert "bravo_write" not in {s.kind for s in other.steps}


async def test_a_plain_line_says_rule_read_and_checked_it_and_nobody_decided_yet() -> None:
    world = _world()
    case = await _m06(world)
    trail = line_trail(case, 1, [])
    assert trail.steps[0].kind == "read"
    assert {s.decided_by for s in trail.steps} <= {"rule", "model"}
    assert "checks" in {s.kind for s in trail.steps}


def test_every_field_of_a_line_is_covered_by_the_trail() -> None:
    """A field added to `OrderLine` without a step here makes this red: the
    trail would then omit a state change (acceptance 1)."""
    covered = {
        "po_line": "read",
        "mapping": "mapping",
        "basis": "checks",
        "suggested_delivery_date": "checks",
        "confirmed_delivery_dates": "confirmed",
        "pc_confirmed_by": "pc_short_lead",
        "pc_confirmed_at": "pc_short_lead",
        "corrections": "correction",
        "changes": "change",
        "pc_answer": "pc_answer",
    }
    assert set(OrderLine.model_fields) == set(covered)


async def test_a_code_dw_applied_by_itself_reads_as_dw() -> None:
    world = _world()
    case = await _m06(world)
    line = case.line(1)
    code = line.mapping.checked_against or "PRV-1"
    applied = line.model_copy(
        update={
            "mapping": LineMapping(
                status=MappingStatus.CANDIDATE_CONFIRMED,
                prv_code=code,
                candidates=(code,),
                confirmed_by=applied_by(),
                confirmed_at=AT,
            )
        }
    )
    updated = case.model_copy(update={"lines": (applied, *case.lines[1:])})
    mapping = next(s for s in line_trail(updated, 1, []).steps if s.kind == "mapping")
    assert mapping.decided_by == "dw" and mapping.actor_user_id is None


async def test_no_amount_reaches_a_step_even_for_a_price_reader() -> None:
    world = _world()
    case = await _m06(world)
    updated, outcomes = _everything_on(case, 3)
    trail = await world.services.orders.line_trail(GIANG.context(), case.case_id, 3)
    text = trail.model_dump_json() + line_trail(updated, 3, outcomes).model_dump_json()
    for line in case.lines:
        for amount in (line.po_line.unit_price, line.po_line.amount):
            if amount != Decimal(0):
                assert f'"{amount}"' not in text and f":{amount}," not in text
        quotation = line.basis.quotation
        if quotation is not None:
            assert str(quotation.unit_price) not in text
    for finding in case.findings:
        for compared in (finding.expected, finding.actual):
            if compared:
                assert compared not in text


async def test_the_trail_is_read_through_the_cases_own_gate() -> None:
    world = _world()
    case = await _m06(world)
    trail = await world.services.orders.line_trail(AN.context(), case.case_id, 3)
    assert trail.line_no == 3 and trail.steps[0].kind == "read"
    # Another tenant names the case and line: not found, nothing else.
    with pytest.raises(NotFoundError):
        await world.services.orders.line_trail(OUTSIDER.context(BETA), case.case_id, 3)
    # A person who may not see the case in a restricted tenant: not found.
    restricted = GIANG.context().model_copy(
        update={
            "record_visibility": "restricted",
            "visible_owners": frozenset({uuid.UUID(int=0xFEED)}),
        }
    )
    await world.services.assignment.reassign(
        GIANG.context(),
        CaseKind.ORDER,
        case.case_id,
        assignee=AN.user_id,
        case_version=case.case_version,
    )
    with pytest.raises(NotFoundError):
        await world.services.orders.line_trail(restricted, case.case_id, 3)
    # A line the case does not have.
    with pytest.raises(NotFoundError):
        await world.services.orders.line_trail(AN.context(), case.case_id, 99)

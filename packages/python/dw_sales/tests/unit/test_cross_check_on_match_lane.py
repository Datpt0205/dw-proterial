"""Ticket 81: the lane that reads an order in Bravo back and passes its
cross-check where the tenant's rules say so and Bravo holds exactly the paste
sheet (dw_sales ADR 0016, Proposed).

DW1 over its in-memory stores and the real runner and approval flow
(`open_world`), as the worker composes the lane; Bravo is a fake gateway
answering what a test says. Acceptance A: a match does not reach the
cross-checker; a difference, an exception or the audit sample does, and so
does every order until the people's decisions certify the step.
"""

from __future__ import annotations

import dataclasses
import uuid
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from dw_kernel.errors import ConflictError, PermissionDeniedError
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.domain.audit import system_actor
from dw_sales.application.access import SalesScopes
from dw_sales.application.bravo_line_writes import BravoUnreachableError
from dw_sales.application.bravo_sales_orders import prepared_rows
from dw_sales.application.cross_check_on_match import (
    CROSS_CHECK_ON_MATCH_LANE,
    CrossCheckOnMatchLane,
    CrossCheckRoute,
    tally,
)
from dw_sales.application.ports import SalesScope
from dw_sales.application.rules import RuleKey
from dw_sales.application.runs import subject_of
from dw_sales.domain import autonomy
from dw_sales.domain.autonomy import cases_needed
from dw_sales.domain.bravo_sales_orders import BravoSalesOrder, BravoSoRow
from dw_sales.domain.cross_check_on_match import ON_MATCH_BASIS, OnMatchException
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import OrderCase, OrderStatus
from dw_sales.evals.graders import AN as _AN
from dw_sales.evals.graders import CALLERS, DIEU, GIANG
from dw_sales.evals.world import ALPHA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
T0 = datetime(2026, 11, 27, 3, tzinfo=UTC)
DIGEST = "e" * 64
AN = replace(_AN, scopes=_AN.scopes | {SalesScopes.RULES_PROPOSE})
LANE = system_actor(CROSS_CHECK_ON_MATCH_LANE).value


@dataclasses.dataclass
class _Bravo:
    """The gateway's read of a customer's PO: the case's own rows, unless a
    test changes one, or no answer at all."""

    case: OrderCase | None = None
    quantity: int | None = None
    so_no: str = "SO26-1001"
    down: bool = False
    asked: int = 0

    async def by_customer_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> tuple[BravoSalesOrder, str] | None:
        self.asked += 1
        if self.down:
            raise BravoUnreachableError("no answer")
        assert self.case is not None
        rows = [
            BravoSoRow(
                row=n,
                so_no=self.so_no,
                customer_code=customer_code,
                po_no=r.po_no,
                po_line=r.line_no,
                item_code=r.prv_code,
                quantity=r.quantity if self.quantity is None or n > 1 else self.quantity,
                unit_price=r.unit_price,
                requested_date=r.requested_date,
                confirmed_date=r.confirmed_date,
            )
            for n, r in enumerate(prepared_rows(self.case), start=1)
        ]
        return BravoSalesOrder(customer_code=customer_code, po_no=po_no, rows=tuple(rows)), DIGEST


async def _switched_on(world: World) -> None:
    """The tenant's own order rules say a matching read-back passes."""
    rules = world.policies.order_rules.model_dump(mode="json", by_alias=True)
    proposed = await world.services.rules.propose(
        AN.context(),
        RuleKey.ORDER_RULES,
        {**rules, "policy_version": "9.0.81", "cross_check_on_match": True},
    )
    await world.decide_rules(GIANG, proposed.version_id, approve=True, comment="Đồng ý")


async def _uploaded(*, on: bool = True) -> tuple[World, uuid.UUID]:
    """M01, which raises no finding, prepared and entered in Bravo by An."""
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    if on:
        await _switched_on(world)
    seen = await world.process_each(DIEU, ["M01"])
    case_id = seen["M01"][0].case_id
    assert case_id is not None
    await world.walk_to_uploaded(AN, case_id)
    assert world.order(case_id).cross_check_on_match is on
    return world, case_id


async def _certified(world: World) -> None:
    """The people's decisions on as many eligible orders as certify 2%."""
    async with world.services.read_backs.sales(ALPHA) as work:
        for _ in range(cases_needed(0.02)):
            await work.cross_check_routes.add(
                CrossCheckRoute(
                    case_id=uuid.uuid4(),
                    case_version=5,
                    basis=ON_MATCH_BASIS,
                    route="person",
                    exceptions=(),
                    outcome="kept",
                    routed_at=T0,
                    decided_at=T0,
                )
            )
        await work.commit()


def _lane(world: World, bravo: _Bravo) -> CrossCheckOnMatchLane:
    backs = world.services.read_backs
    return CrossCheckOnMatchLane(
        uow=backs.sales,
        read_backs=backs.uow,
        bravo=bravo,
        decisions=world.runs,
        rules=world.intake.rules,
        clock=FixedClock(T0),
        ids=Uuid4Generator(),
    )


async def _pending(world: World, case_id: uuid.UUID) -> uuid.UUID | None:
    return await world.runs.pending(AN.context(), subject_of(CaseKind.ORDER, case_id))


async def _route(world: World, case_id: uuid.UUID) -> CrossCheckRoute | None:
    async with world.services.read_backs.sales(ALPHA) as work:
        return await work.cross_check_routes.get(case_id, world.order(case_id).case_version)


@pytest.fixture
def unsampled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(autonomy, "in_audit_sample", lambda key, share: False)


# ---------------------------------------------------------------- a match --


@pytest.mark.usefixtures("unsampled")
async def test_a_certified_match_passes_by_dw_and_never_reaches_the_cross_checker() -> None:
    world, case_id = await _uploaded()
    await _certified(world)
    version = world.order(case_id).case_version
    assert await _pending(world, case_id) is not None
    bravo = _Bravo(world.order(case_id))

    done = await _lane(world, bravo).tick(ALPHA)

    case = world.order(case_id)
    assert (done.routed, done.passed) == ({"applied": 1}, 1)
    assert case.status is OrderStatus.CROSS_CHECKED
    assert (case.cross_checked_by, case.cross_checked_on_read_back) == (LANE, DIGEST)
    assert await _pending(world, case_id) is None
    async with world.services.read_backs.sales(ALPHA) as work:
        route = await work.cross_check_routes.get(case_id, version)
    assert route is not None and (route.route, route.exceptions) == ("applied", ())
    # The read-back is Bravo's own, stored and audited as the lane.
    async with world.bravo_store(ALPHA) as backs:
        stored = await backs.read_backs.get(case_id)
    assert stored is not None and (stored.source, stored.read_by) == ("gateway", LANE)
    (read,) = [
        e for e in world.bravo_store.audit.events if e.action == "sales.order.bravo_read_back"
    ]
    assert read.actor_id.value == LANE
    assert read.details["actor"] == f"system:{CROSS_CHECK_ON_MATCH_LANE}"
    # The pass and the approval it withdrew read as the lane too (ADR 0011).
    label = f"system:{CROSS_CHECK_ON_MATCH_LANE}"
    passed = [e for e in world.audit() if e.details.get("to_status") == "cross_checked"]
    assert [(e.actor_id.value, e.details["actor"]) for e in passed] == [(LANE, label)]
    withdrawn = [e for e in world.runtime.audit.events if e.action == "approval.withdrawn"]
    assert [(e.actor_id.value, e.details["actor"]) for e in withdrawn] == [(LANE, label)]


async def test_an_uncertified_step_leaves_the_match_to_the_cross_checker_and_learns() -> None:
    world, case_id = await _uploaded()
    version = world.order(case_id).case_version

    await _lane(world, _Bravo(world.order(case_id))).tick(ALPHA)

    assert world.order(case_id).status is OrderStatus.UPLOADED_TO_BRAVO
    assert await _pending(world, case_id) is not None
    route = await _route(world, case_id)
    assert route is not None and (route.route, route.exceptions) == ("person", ())
    # The cross-checker's decision is the measure's case.
    await world.cross_check(GIANG, case_id)
    async with world.services.read_backs.sales(ALPHA) as work:
        decided = await work.cross_check_routes.get(case_id, version)
        measured = tally(await work.cross_check_routes.outcomes(ON_MATCH_BASIS))
    assert decided is not None and decided.outcome == "kept"
    assert (measured.cases, measured.errors) == (1, 0)


async def test_a_sampled_match_goes_to_the_cross_checker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(autonomy, "in_audit_sample", lambda key, share: True)
    world, case_id = await _uploaded()
    await _certified(world)

    await _lane(world, _Bravo(world.order(case_id))).tick(ALPHA)

    assert world.order(case_id).status is OrderStatus.UPLOADED_TO_BRAVO
    assert await _pending(world, case_id) is not None
    route = await _route(world, case_id)
    assert route is not None and route.route == "audit"
    # The sample is unannounced: the cross-checker is not told why it is theirs.
    view = await world.services.orders.get(GIANG.context(), case_id)
    assert view.cross_check_on_match_exceptions is None


@pytest.mark.usefixtures("unsampled")
async def test_a_difference_goes_to_the_cross_checker_with_its_reason() -> None:
    world, case_id = await _uploaded()
    await _certified(world)

    await _lane(world, _Bravo(world.order(case_id), quantity=1)).tick(ALPHA)

    assert world.order(case_id).status is OrderStatus.UPLOADED_TO_BRAVO
    assert await _pending(world, case_id) is not None
    route = await _route(world, case_id)
    assert route is not None and route.exceptions == (OnMatchException.DIFFERS,)
    # The cross-checker reads why on the order (ticket 81 review).
    view = await world.services.orders.get(GIANG.context(), case_id)
    assert view.cross_check_on_match_exceptions == [OnMatchException.DIFFERS]


@pytest.mark.usefixtures("unsampled")
async def test_bravo_holding_the_po_under_another_so_number_goes_to_the_cross_checker() -> None:
    """The SO number the PIC typed is what the confirmation prints: rows that
    match under another number in Bravo do not vouch for it."""
    world, case_id = await _uploaded()
    await _certified(world)
    assert world.order(case_id).bravo_so_no == "SO26-1001"

    await _lane(world, _Bravo(world.order(case_id), so_no="SO26-9999")).tick(ALPHA)

    assert world.order(case_id).status is OrderStatus.UPLOADED_TO_BRAVO
    assert await _pending(world, case_id) is not None
    route = await _route(world, case_id)
    assert route is not None and route.exceptions == (OnMatchException.SO_NO_DIFFERS,)


# ------------------------------------------------------------ what it reads --


async def test_rules_that_do_not_say_so_read_nothing_from_bravo() -> None:
    world, case_id = await _uploaded(on=False)
    bravo = _Bravo(world.order(case_id))

    done = await _lane(world, bravo).tick(ALPHA)

    assert (done.routed, bravo.asked) == ({}, 0)
    assert await _route(world, case_id) is None


async def test_each_version_is_read_once_and_an_unanswered_read_is_tried_again() -> None:
    world, case_id = await _uploaded()
    bravo = _Bravo(world.order(case_id), down=True)
    lane = _lane(world, bravo)

    await lane.tick(ALPHA)
    assert (bravo.asked, await _route(world, case_id)) == (1, None)
    bravo.down = False
    await lane.tick(ALPHA)
    await lane.tick(ALPHA)

    assert bravo.asked == 2
    assert await _route(world, case_id) is not None


# ------------------------------------------------------------ taking back --


@pytest.mark.usefixtures("unsampled")
async def test_a_non_maker_takes_the_pass_back_and_it_counts_as_an_error() -> None:
    world, case_id = await _uploaded()
    await _certified(world)
    await _lane(world, _Bravo(world.order(case_id))).tick(ALPHA)
    passed = world.order(case_id)
    reopening = world.services.cross_check_reopening

    with pytest.raises(ConflictError) as refused:
        await reopening.reopen(AN.context(), case_id, case_version=passed.case_version)
    assert refused.value.details["rule"] == "maker_checker"
    await reopening.reopen(GIANG.context(), case_id, case_version=passed.case_version)

    case = world.order(case_id)
    assert case.status is OrderStatus.UPLOADED_TO_BRAVO and case.awaits_cross_check
    assert (case.cross_checked_by, case.cross_check_on_match) == (None, False)
    async with world.services.read_backs.sales(ALPHA) as work:
        measured = tally(await work.cross_check_routes.outcomes(ON_MATCH_BASIS))
    assert (measured.audits, measured.audit_errors) == (1, 1)
    # Its next version is never DW's to pass again.
    bravo = _Bravo(case)
    await _lane(world, bravo).tick(ALPHA)
    assert bravo.asked == 0


@pytest.mark.usefixtures("unsampled")
async def test_someone_who_may_not_cross_check_does_not_take_the_pass_back() -> None:
    """Asked of the service itself, not only of the route: a non-maker
    without `sales.order.cross_check` is refused, and the pass stands."""
    world, case_id = await _uploaded()
    await _certified(world)
    await _lane(world, _Bravo(world.order(case_id))).tick(ALPHA)
    passed = world.order(case_id)
    no_scope = replace(GIANG, scopes=GIANG.scopes - {SalesScopes.ORDER_CROSS_CHECK})
    assert no_scope.user_id not in passed.makers

    with pytest.raises(PermissionDeniedError):
        await world.services.cross_check_reopening.reopen(
            no_scope.context(), case_id, case_version=passed.case_version
        )

    assert world.order(case_id) == passed


# ------------------------------------------------- what a pass reads as --


@pytest.mark.usefixtures("unsampled")
async def test_a_pass_by_dw_never_reads_as_a_persons_check() -> None:
    """ui-quality section 7: the line's trail says DW decided it, and the
    confirmation names no person as its checker."""
    import email
    from email.message import EmailMessage
    from email.policy import default

    world, case_id = await _uploaded()
    await _certified(world)
    await _lane(world, _Bravo(world.order(case_id))).tick(ALPHA)
    case = world.order(case_id)

    trail = await world.services.orders.line_trail(DIEU.context(), case_id, 1)
    (step,) = [s for s in trail.steps if s.kind == "cross_checked"]
    assert (step.decided_by, step.actor_user_id) == ("dw", None)

    held = date(2026, 12, 15)
    await world.services.confirmations.sent(
        AN.context(),
        case_id,
        case_version=case.case_version,
        delivery_dates={x.line_no: [held] * x.deliveries for x in case.lines},
    )
    case = world.order(case_id)
    artifacts = world.services.artifacts
    (view,) = await artifacts.render_order(
        AN.context(), case_id, kind="confirmation_draft", case_version=case.case_version
    )
    data = (await artifacts.order_artifact(AN.context(), case_id, view.artifact_id)).data
    message = email.message_from_bytes(data, policy=default)
    assert isinstance(message, EmailMessage)
    part = message.get_body(("plain",))
    assert part is not None
    body = str(part.get_content())
    assert "(đối chiếu tự động với hệ thống)" in body
    assert "Hoàng Thị Diệu" not in body and "Giang" not in body

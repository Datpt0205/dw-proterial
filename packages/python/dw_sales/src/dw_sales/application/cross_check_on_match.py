"""The cross-check passed on a matching read-back, by DW (dw_sales ticket 81,
ADR 0016, Proposed; off unless the tenant's order rules say
`cross_check_on_match`).

**The lane** (`CrossCheckOnMatchLane`, the worker's
``sales_cross_check_on_match``) visits every workspace's orders in Bravo whose
rules stamped the switch (`OrderCaseStorePort.awaiting_on_match`). It reads
each case version once (`CrossCheckRoutesPort.get`): Bravo is not polled for
an order it has already read at that version. It reads the sales order
through the gateway (`BravoCustomerPoPort`) as itself, never as a person,
stores the read-back as `gateway` with the lane's audit row (ADR 0011), and
asks the case its verdict (`OrderCase.on_match_exceptions`). An order with an
exception stays the cross-checker's, its exceptions recorded. An eligible one
is routed by the measured gate (`measured_route`), at the tenant's hand-off
error and audit share (`OrderRules.autonomy`), over what people decided on
the same basis (`CrossCheckRoutesPort.tally`): a person's until that
certifies, then applied, sampled for audit, or shadow once its audits stop it.

**Applied**: the pending cross-check is withdrawn first, so nobody decides
it, then the case passes (`OrderCase.cross_checked_on_match`, which asks the
verdict again) in the same transaction as its route. If a person decided
meanwhile, the save meets their version and the lane's pass is dropped; if
the save fails otherwise, the order awaits a cross-check with none raised,
and the case says so ("Gửi kiểm chéo lại", ticket 14).

**Measured**: a cross-checker's decision on a routed version records
`kept` or `returned` (`CaseDecisions`), and a pass taken back `undone`
(`OrderCase.reopen_cross_check`). Those are the only counts the gate reads.

Nothing here runs unless the switch is on, the gateway is composed and the
case's own verdict passes; with any of them missing every order is a
person's, as before.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from dw_kernel.errors import ConflictError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import system_actor
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.bravo_line_writes import BravoUnreachableError
from dw_sales.application.bravo_sales_orders import (
    BravoCustomerPoPort,
    ReadBackUnitOfWorkFactory,
    prepared_rows,
    store_read_back,
)
from dw_sales.application.case_store import CaseEvent, EventActor, SalesUnitOfWorkFactory
from dw_sales.application.ports import SalesScope
from dw_sales.application.runs import PendingDecisionsPort, subject_of
from dw_sales.application.support import (
    DW1_WORKER_ID,
    DW1_WORKER_VERSION,
    decided,
    person_event,
    same_version,
    save_order,
    stored_order,
)
from dw_sales.application.views import CaseChangeView, order_change
from dw_sales.domain.autonomy import OutcomeTally, measured_route
from dw_sales.domain.bravo_sales_orders import compare
from dw_sales.domain.cross_check_on_match import (
    EXCEPTION_ORDER,
    ON_MATCH_BASIS,
    OnMatchException,
    ReadBackFacts,
)
from dw_sales.domain.description_reading import GateRoute
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.order_checks import OrderRules
from dw_sales.domain.orders import Actor, OrderCase

logger = logging.getLogger("dw_sales.cross_check_on_match")

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# The worker's registry name: the actor every read and pass is the lane's.
CROSS_CHECK_ON_MATCH_LANE: Final = "sales_cross_check_on_match"

Outcome = Literal["kept", "returned", "undone"]


class CrossCheckRoute(BaseModel):
    """What the lane did with one case version, and what a person decided."""

    model_config = _FROZEN

    case_id: uuid.UUID
    case_version: int = Field(ge=1)
    basis: str = Field(min_length=1, max_length=64)
    route: GateRoute
    # Why it stayed a person's; empty: eligible, routed by the gate.
    exceptions: tuple[OnMatchException, ...]
    outcome: Outcome | None = None
    routed_at: AwareDatetime
    decided_at: AwareDatetime | None = None

    @property
    def eligible(self) -> bool:
        return not self.exceptions


class CrossCheckRoutesPort(Protocol):
    """The workspace's routes inside a unit of work (RLS-bound)."""

    async def get(self, case_id: uuid.UUID, case_version: int) -> CrossCheckRoute | None: ...

    async def add(self, route: CrossCheckRoute) -> None:
        """A version's route; refused (409) when that version has one."""
        ...

    async def decide(
        self, case_id: uuid.UUID, case_version: int, outcome: Outcome, at: datetime
    ) -> bool:
        """The decision on that version's route, once: False when it has no
        route or one already decided."""
        ...

    async def passed(self, case_id: uuid.UUID) -> CrossCheckRoute | None:
        """The case's route DW applied that nobody has decided: what taking
        the pass back decides."""
        ...

    async def outcomes(self, basis: str) -> Iterable[CrossCheckRoute]:
        """Every decided route on ``basis``: what the measure counts."""
        ...


def tally(routes: Iterable[CrossCheckRoute]) -> OutcomeTally:
    """The measure of decided routes (`measured_route`): the people's
    decisions on eligible versions the lane did not apply are its cases, a
    return their error; decisions on what was sampled or applied are its
    audits, a return or an undo their error."""
    cases = errors = audits = audit_errors = 0
    for route in routes:
        if route.outcome is None or not route.eligible:
            continue
        wrong = route.outcome != "kept"
        if route.route != "applied":
            cases += 1
            errors += wrong
        if route.route in ("audit", "applied"):
            audits += 1
            audit_errors += wrong
    return OutcomeTally(cases, errors, audits, audit_errors)


class CaseRulesPort(Protocol):
    """An order rules version by its stamp (`RuleBookOrderRules.rules_at`):
    the hand-off error and audit share a case is routed at are those it was
    checked under."""

    async def rules_at(self, scope: SalesScope, ref: str) -> OrderRules | None: ...


def lane_context(scope: SalesScope) -> AccessContext:
    """The lane in ``scope``: its own actor, no scope at all."""
    return AccessContext(
        tenant_id=scope.tenant_id.value,
        workspace_id=scope.workspace_id.value,
        principal_id=system_actor(CROSS_CHECK_ON_MATCH_LANE).value,
        roles=frozenset(),
        scopes=frozenset(),
        plan_id="background",
    )


@dataclass(frozen=True, slots=True)
class OnMatchTick:
    """How many orders one tick routed each way, and passed."""

    routed: dict[str, int]
    passed: int = 0


@dataclass(frozen=True)
class CrossCheckOnMatchLane:
    """One tick in one workspace (module docstring)."""

    uow: SalesUnitOfWorkFactory
    read_backs: ReadBackUnitOfWorkFactory
    bravo: BravoCustomerPoPort
    decisions: PendingDecisionsPort
    rules: CaseRulesPort
    clock: UtcClock
    ids: IdGenerator

    async def tick(self, scope: SalesScope) -> OnMatchTick:
        context = lane_context(scope)
        async with self.uow(scope) as work:
            waiting = [s.case for s in await work.orders.awaiting_on_match()]
            unread = [
                case
                for case in waiting
                if await work.cross_check_routes.get(case.case_id, case.case_version) is None
            ]
        routed: dict[str, int] = {}
        passed = 0
        for case in unread:
            route = await self._one(scope, context, case)
            if route is None:
                continue
            routed[route] = routed.get(route, 0) + 1
            passed += route == "applied"
        return OnMatchTick(routed, passed)

    async def _one(
        self, scope: SalesScope, context: AccessContext, case: OrderCase
    ) -> GateRoute | None:
        """The case read back and routed; None when Bravo did not answer (it
        is read again next tick) or someone moved the case meanwhile."""
        try:
            found = await self.bravo.by_customer_po(scope, case.customer_code, case.header.po_no)
        except BravoUnreachableError:
            return None
        now = self.clock.now()
        exceptions: tuple[OnMatchException, ...]
        digest: str | None = None
        facts: ReadBackFacts | None = None
        if found is None or found[0].so_no is None:
            # No SO, or several: nothing compared, the cross-checker's.
            exceptions = (OnMatchException.DIFFERS,)
        else:
            order, digest = found
            differences = compare(prepared_rows(case), order, confirmed_dates=True)
            stored = await store_read_back(
                self.read_backs,
                self.ids,
                self.clock,
                context,
                case,
                order,
                differences,
                digest,
                source="gateway",
                lane=CROSS_CHECK_ON_MATCH_LANE,
            )
            facts = stored.facts
            exceptions = case.on_match_exceptions(facts)
        route: GateRoute = "person"
        stamped = case.rules_version
        rules = None if stamped is None else await self.rules.rules_at(scope, stamped)
        if rules is None:
            # Rules this process no longer holds say nothing: off.
            off = {*exceptions, OnMatchException.RULES_OFF}
            exceptions = tuple(e for e in EXCEPTION_ORDER if e in off)
        if not exceptions and rules is not None:
            async with self.uow(scope) as work:
                measured = tally(await work.cross_check_routes.outcomes(ON_MATCH_BASIS))
            route = measured_route(
                measured,
                rules.autonomy.hand_off_error,
                item_key=f"{scope.tenant_id.value}:{case.case_id}:{case.case_version}",
                audit_share=rules.autonomy.audit_share,
            )
        record = CrossCheckRoute(
            case_id=case.case_id,
            case_version=case.case_version,
            basis=ON_MATCH_BASIS,
            route=route,
            exceptions=exceptions,
            routed_at=now,
        )
        if route == "applied":
            assert digest is not None and facts is not None
            # Withdrawn first, so nobody decides it while the case passes.
            await self.decisions.withdraw(context, subject_of(CaseKind.ORDER, case.case_id))
        try:
            async with self.uow(scope) as work:
                await work.cross_check_routes.add(record)
                if route == "applied":
                    assert digest is not None and facts is not None
                    actor = Actor(user_id=context.principal_id)
                    after = case.cross_checked_on_match(facts, digest, actor, now)
                    event = CaseEvent(
                        action="order.cross_checked_on_match",
                        actor=EventActor.worker(
                            DW1_WORKER_ID, DW1_WORKER_VERSION, initiated_by=None
                        ),
                        reason_code="read_back_matches",
                        occurred_at=now,
                    )
                    await save_order(work, context, self.ids, case, after, event)
                await work.commit()
        except ConflictError:
            logger.info("sales_cross_check_on_match: the case moved on before it was routed")
            return None
        return route


@dataclass(frozen=True)
class CrossCheckReopening:
    """A cross-check DW passed on Bravo's read-back, taken back ("Mở lại kiểm
    chéo", ticket 81): by a holder of `sales.order.cross_check` who made none
    of the order, before its confirmation left. The pass is measured as
    undone, and the order awaits a person's cross-check with none raised: the
    order page and "Việc của tôi" offer whoever recorded the Bravo entry (or
    the head) "Gửi kiểm chéo lại" (ticket 14), the one path that raises it."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator

    async def reopen(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int
    ) -> CaseChangeView:
        await self.gate.require(
            context,
            SalesScopes.ORDER_CROSS_CHECK,
            resource_type="sales_order_case",
            resource_id=str(case_id),
        )
        now = self.clock.now()
        async with self.uow(sales_scope(context)) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            passed = await work.cross_check_routes.passed(case_id)
            after = decided(lambda: case.reopen_cross_check(Actor(user_id=context.principal_id)))
            event = person_event("order.cross_check_reopened", context, now)
            await save_order(work, context, self.ids, case, after, event)
            if passed is not None:
                await work.cross_check_routes.decide(case_id, passed.case_version, "undone", now)
            await work.commit()
        return order_change(after)

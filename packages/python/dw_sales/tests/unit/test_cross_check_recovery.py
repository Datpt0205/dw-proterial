"""An order whose cross-check decision failed to apply can be cross-checked again
(ticket 14).

The decision is checked twice: by the guard before the platform records it,
and by the run when it resumes and applies it. Anything that bumps the case
version in between (here: the export-control PIC acknowledging NOC/ESF) makes
the apply refuse, the run fail, and the approval stay decided. Before ticket 14
the order was then stuck at `uploaded_to_bravo` with nothing left to decide.

The real runner, approval flow and DW1 graph over in-memory stores
(`open_world`), as the API composes them.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dw_agent_runtime.adapters.run_store import RunStatus
from dw_agent_runtime.approval_flow import ApprovalDecisionGuard, ProposedDecision
from dw_kernel.errors import ConflictError, PermissionDeniedError
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.approval import ApprovalRequest, ApprovalStatus
from dw_sales.application.rules import RuleKey
from dw_sales.application.runs import APPROVAL_PREFIX, subject_of
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import Actor
from dw_sales.evals.graders import AN, CALLERS, DIEU, GIANG
from dw_sales.evals.world import Caller, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
NOC = "missing_noc_esf:-"


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS)


async def _uploaded(world: World) -> uuid.UUID:
    """M03 prepared and recorded in Bravo by An, NOC/ESF still open: its
    acknowledgement is allowed while the order waits on its cross-check."""
    seen = await world.process_each(AN, ["M03"])
    case_id = seen["M03"][0].case_id
    assert case_id is not None
    await world.services.order_commands.dispose(
        AN.context(),
        case_id,
        "quotation_missing:2",
        case_version=world.order(case_id).case_version,
        disposition="accepted",
        reason="Giá theo báo giá gia hạn qua thư",
    )
    await world.walk_to_uploaded(AN, case_id)
    return case_id


class _BumpAfterCheck:
    """The guard, then a version bump before the run resumes: An acknowledges
    NOC/ESF in the instant between the decision and its apply."""

    def __init__(self, world: World, inner: ApprovalDecisionGuard, case_id: uuid.UUID) -> None:
        self.world, self.inner, self.case_id = world, inner, case_id

    async def check(
        self, request: ApprovalRequest, decision: ProposedDecision, context: AccessContext
    ) -> None:
        await self.inner.check(request, decision, context)
        await self.world.services.order_commands.dispose(
            AN.context(),
            self.case_id,
            NOC,
            case_version=self.world.order(self.case_id).case_version,
            disposition="accepted",
            reason="Khách đã gửi NOC năm nay",
        )


async def _decided_but_not_applied(world: World) -> uuid.UUID:
    case_id = await _uploaded(world)
    guards = world.runtime.approval_flow.decision_guards
    inner = guards[APPROVAL_PREFIX]
    guards[APPROVAL_PREFIX] = _BumpAfterCheck(world, inner, case_id)
    try:
        with pytest.raises(ConflictError):
            await world.cross_check(DIEU, case_id)
    finally:
        guards[APPROVAL_PREFIX] = inner
    return case_id


def _approvals(world: World, status: ApprovalStatus) -> list[ApprovalRequest]:
    return [r for r in world.runtime.approvals.rows.values() if r.status is status]


# -------------------------------------------------------- 1. reproduce --


async def test_a_decision_that_failed_to_apply_no_longer_strands_the_order() -> None:
    world = _world()
    case_id = await _decided_but_not_applied(world)

    # The stuck state, as it was found on 2026-10-12.
    assert world.order(case_id).status.value == "uploaded_to_bravo"
    (decided,) = _approvals(world, ApprovalStatus.APPROVED)
    assert await world.runs.pending(AN.context(), subject_of(CaseKind.ORDER, case_id)) is None
    failed = [r for r in world.runtime.runs.rows.values() if r.status is RunStatus.FAILED]
    assert len(failed) == 1

    # The way out: the Bravo recorder raises the cross-check again...
    await world.services.dw1.resend_cross_check(
        AN.context(), case_id, case_version=world.order(case_id).case_version
    )
    (pending,) = _approvals(world, ApprovalStatus.PENDING)
    assert pending.id != decided.id
    # ...and whoever decided the failed one decides again, at the version now.
    await world.cross_check(DIEU, case_id)
    case = world.order(case_id)
    assert case.status.value == "cross_checked"
    assert case.cross_checked_by == DIEU.user_id


# ---------------------------------------------- 3. a trace, ids only --


async def test_the_failed_apply_leaves_an_audit_row_naming_run_approval_and_reason() -> None:
    world = _world()
    case_id = await _decided_but_not_applied(world)
    (decided,) = _approvals(world, ApprovalStatus.APPROVED)
    (failed,) = [i for i, r in world.runtime.runs.rows.items() if r.status is RunStatus.FAILED]

    (row,) = [e for e in world.audit() if e.action == "sales.order.decision_not_applied"]
    assert row.resource_id == str(case_id)
    assert row.run_id == failed
    assert row.details["approval_id"] == str(decided.id)
    assert row.details["reason_code"] == "stale_case_version"
    # Ids, codes and versions only: no comment, no amount.
    assert set(row.details) <= {
        "case_kind",
        "case_version",
        "from_status",
        "to_status",
        "actor_kind",
        "worker_id",
        "worker_version",
        "reason_code",
        "approval_id",
    }

    view = await world.services.orders.get(AN.context(), case_id)
    assert view.cross_check_stalled is True
    assert view.unapplied_decision is not None
    assert view.unapplied_decision.reason_code == "stale_case_version"
    assert view.unapplied_decision.approval_id == decided.id
    assert view.unapplied_decision.decided_by == DIEU.user_id


async def test_an_order_that_moves_on_no_longer_names_the_decision_not_applied() -> None:
    world = _world()
    case_id = await _decided_but_not_applied(world)
    stuck = world.order(case_id)
    assert stuck.unapplied_decision is not None

    returned = stuck.return_from_cross_check(
        "Sai số SO", Actor(user_id=DIEU.user_id), datetime.now(UTC)
    )

    assert returned.status.value == "in_review"
    assert returned.unapplied_decision is None


# ---------------------------------------- 2. who may, and only once --


async def test_the_head_may_raise_it_again_and_a_pic_who_made_none_of_it_may_not() -> None:
    world = _world()
    case_id = await _decided_but_not_applied(world)
    version = world.order(case_id).case_version

    with pytest.raises(PermissionDeniedError):
        await world.services.dw1.resend_cross_check(DIEU.context(), case_id, case_version=version)
    assert _approvals(world, ApprovalStatus.PENDING) == []

    await world.services.dw1.resend_cross_check(GIANG.context(), case_id, case_version=version)
    assert len(_approvals(world, ApprovalStatus.PENDING)) == 1


async def test_raising_it_again_while_one_is_pending_is_refused() -> None:
    world = _world()
    case_id = await _uploaded(world)

    with pytest.raises(ConflictError) as refused:
        await world.services.dw1.resend_cross_check(
            AN.context(), case_id, case_version=world.order(case_id).case_version
        )
    assert refused.value.details["rule"] == "cross_check_pending"
    assert len(_approvals(world, ApprovalStatus.PENDING)) == 1


async def test_raising_it_again_while_a_run_is_unfinished_is_refused() -> None:
    world = _world()
    case_id = await _decided_but_not_applied(world)
    # A DW1 run about the order that has not finished (it would raise its
    # own approval when it pauses).
    (failed,) = [r for r in world.runtime.runs.rows.values() if r.status is RunStatus.FAILED]
    failed.status = RunStatus.RUNNING

    with pytest.raises(ConflictError) as refused:
        await world.services.dw1.resend_cross_check(
            AN.context(), case_id, case_version=world.order(case_id).case_version
        )
    assert refused.value.details["rule"] == "dw1_running"
    assert _approvals(world, ApprovalStatus.PENDING) == []


async def test_the_bravo_entry_door_does_not_raise_it_again() -> None:
    """`bravo-entry` on an order already in Bravo is refused before it withdraws
    anything: otherwise it would cancel a pending cross-check, or raise a second
    one past the checks above."""
    world = _world()
    case_id = await _uploaded(world)

    with pytest.raises(ConflictError):
        await world.services.dw1.record_bravo_entry(
            AN.context(),
            case_id,
            case_version=world.order(case_id).case_version,
            so_no=None,
            entry_compared=True,
        )
    (pending,) = _approvals(world, ApprovalStatus.PENDING)
    assert pending.status is ApprovalStatus.PENDING


# ------------------------------------------------- 4. maker / checker --


async def test_the_new_approval_names_the_same_makers() -> None:
    world = _world()
    case_id = await _decided_but_not_applied(world)
    (decided,) = _approvals(world, ApprovalStatus.APPROVED)

    await world.services.dw1.resend_cross_check(
        AN.context(), case_id, case_version=world.order(case_id).case_version
    )

    (pending,) = _approvals(world, ApprovalStatus.PENDING)
    assert pending.makers == decided.makers == {AN.user_id}
    await world.open_sources(AN, case_id)
    with pytest.raises(ConflictError) as refused:
        await world.decide(AN, CaseKind.ORDER, case_id, approve=True, comment="ok")
    assert refused.value.details["rule"] == "maker_checker"


# ------------------------------------------------------- 5. my work --


async def _actions(world: World, caller: Caller, case_id: uuid.UUID) -> set[str]:
    items = (await world.services.overview.my_work(caller.context())).items
    return {i.action for i in items if i.id == str(case_id)}


async def test_my_work_offers_the_cross_check_while_one_is_pending() -> None:
    world = _world()
    case_id = await _uploaded(world)

    assert await _actions(world, DIEU, case_id) == {"cross_check"}
    assert await _actions(world, AN, case_id) == set()


async def test_my_work_offers_the_maker_to_raise_it_again_once_stalled() -> None:
    world = _world()
    case_id = await _decided_but_not_applied(world)

    assert await _actions(world, DIEU, case_id) == set()
    assert await _actions(world, AN, case_id) == {"resend_cross_check"}


async def test_my_work_offers_no_cross_check_when_the_rules_need_none() -> None:
    """The tenant's rules need no cross-check: the order waits on its
    confirmation, which is its PIC's, and no cross-checker is handed it."""
    world = _world()
    rules = world.policies.order_rules.model_dump(mode="json", by_alias=True)
    proposed = await world.services.rules.propose(
        AN.context(),
        RuleKey.ORDER_RULES,
        {**rules, "policy_version": "9.0.1", "cross_check_required": False},
    )
    await world.decide_rules(GIANG, proposed.version_id, approve=True, comment="Đồng ý")
    case_id = await _uploaded(world)
    assert world.order(case_id).cross_check_required is False

    assert await _actions(world, DIEU, case_id) == set()
    assert await _actions(world, AN, case_id) == {"confirm"}

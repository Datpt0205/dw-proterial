"""DW02 function 2 on PostgreSQL: a request sent for approval, decided on the
platform's approvals as the composition root wires them (`purchasing.` strict,
`RequestDecisions` the guard), and carried out from the approval row.

As `dw_app` under RLS. The approval flow here is the platform's own
`ApproveAndResumeService`; a run-less approval never reaches its runner, so
none is built.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from purchasing_harness import Tenancy
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_agent_runtime.approval_flow import ApproveAndResumeService
from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.adapters.persistence.repositories import (
    SqlApprovalRepository,
    SqlAuditRepository,
)
from dw_platform.adapters.persistence.rule_versions import SqlRuleVersionLookup
from dw_platform.adapters.persistence.uow import SqlPlatformUnitOfWorkFactory
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.domain.approval import APPROVALS_DECIDE
from dw_purchasing.adapters.assembly import request_decisions, request_settlement
from dw_purchasing.adapters.mock.inbox import MockInbox
from dw_purchasing.adapters.mock.master_data import MockMasterData
from dw_purchasing.adapters.persistence.store import SqlPurchasingStore
from dw_purchasing.adapters.policy_files import PolicyFiles
from dw_purchasing.application.access import Gate
from dw_purchasing.application.approvals import (
    APPROVAL_PREFIX,
    REQUEST_DECIDED,
    RequestApprovals,
)
from dw_purchasing.application.intake import PurchaseRequests, Worker
from dw_purchasing.application.rules import released_book
from dw_purchasing.domain.cases import CaseStatus
from dw_purchasing.testing.world import BUYER, Authz, ScriptedModel, caller

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[5]
NOW = datetime(2026, 11, 2, 1, 0, tzinfo=UTC)
ANSWERS = json.loads(
    (REPO / "evals/fixtures/cases/purchasing_pr_intake.json").read_text(encoding="utf-8")
)["answers"]
HEAD = uuid.UUID(int=0x4EAD)


def _services(
    sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy
) -> tuple[PurchaseRequests, RequestApprovals, ApproveAndResumeService]:
    files = PolicyFiles.load(REPO / "configs/policies")
    store = SqlPurchasingStore(sessions, SqlAuditRepository, SqlApprovalRepository)
    book = released_book(files.current(), files.by_ref, SqlRuleVersionLookup(sessions))
    clock, ids = FixedClock(NOW), Uuid4Generator()
    intake = PurchaseRequests(
        uow=store,
        gate=Gate(Authz()),
        rules=book,
        inbox=MockInbox.load(tenant_id=tenancy.alpha[0], workspace_id=tenancy.alpha[1]),
        model=ScriptedModel(ANSWERS),
        worker=Worker("purchasing-dw2", "1.0.0"),
        clock=clock,
        ids=ids,
    )
    approvals = RequestApprovals(
        uow=store,
        gate=Gate(Authz()),
        rules=book,
        master=MockMasterData.load(tenant_id=tenancy.alpha[0], workspace_id=tenancy.alpha[1]),
        clock=clock,
        ids=ids,
    )
    flow = ApproveAndResumeService(
        uow_factory=SqlPlatformUnitOfWorkFactory(sessions),
        runner=None,  # type: ignore[arg-type]  # a run-less approval resumes nothing
        run_store=None,  # type: ignore[arg-type]
        clock=clock,
        id_generator=ids,
    )
    # As `build_purchasing_mount` wires it.
    flow.strict_approval_prefixes |= {APPROVAL_PREFIX}
    flow.decision_guards[APPROVAL_PREFIX] = request_decisions(
        sessions, SqlAuditRepository, SqlApprovalRepository
    )
    return intake, approvals, flow


def _approver(tenancy: Tenancy, *scopes: str, who: uuid.UUID = HEAD):  # type: ignore[no-untyped-def]
    return caller(tenancy.alpha, principal=who, scopes=frozenset({APPROVALS_DECIDE, *scopes}))


async def test_a_request_goes_to_its_tier_is_decided_by_it_and_carried_out(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy
) -> None:
    intake, approvals, flow = _services(app_sessions, tenancy)
    me = caller(tenancy.alpha)
    case_id = (await intake.read_mail(me, "P01")).case_id
    assert case_id is not None
    await approvals.submit(me, case_id, case_version=1)
    case = await intake.case(me, case_id)
    assert case.approval is not None
    approval_id = case.approval.approval_id
    authz = ScopeAuthorizationService()

    # Who sent it never decides it; a decision needs its reason written.
    with pytest.raises((ConflictError, PermissionDeniedError)):
        await flow.decide(
            approval_id=approval_id,
            approve=True,
            comment="tự duyệt",
            context=_approver(tenancy, "purchasing.approve.tier1", who=BUYER),
            authorization=authz,
        )
    with pytest.raises(ConflictError):
        await flow.decide(
            approval_id=approval_id,
            approve=True,
            comment=" ",
            context=_approver(tenancy, "purchasing.approve.tier1"),
            authorization=authz,
        )
    # A holder of another tier is not this approval's decider: it is absent.
    with pytest.raises(NotFoundError):
        await flow.decide(
            approval_id=approval_id,
            approve=True,
            comment="ok",
            context=_approver(tenancy, "purchasing.approve.tier2"),
            authorization=authz,
        )
    # A decision on a version the approver no longer sees is refused by the guard.
    with pytest.raises(ConflictError):
        await flow.decide(
            approval_id=approval_id,
            approve=True,
            comment="ok",
            context=_approver(tenancy, "purchasing.approve.tier1"),
            authorization=authz,
            subject_version=1,
        )

    await flow.decide(
        approval_id=approval_id,
        approve=True,
        comment="Đồng ý theo báo giá",
        context=_approver(tenancy, "purchasing.approve.tier1"),
        authorization=authz,
        subject_version=2,
    )
    async with app_sessions() as session, session.begin():
        await session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenancy.alpha[0])}
        )
        events = (
            (
                await session.execute(
                    sa.text("SELECT event_type FROM platform.outbox_events WHERE event_type = :e"),
                    {"e": REQUEST_DECIDED},
                )
            )
            .scalars()
            .all()
        )
    assert list(events) == [REQUEST_DECIDED]

    # The worker's handler: the decider from the event's envelope, no scope.
    settlement = request_settlement(
        app_sessions, SqlAuditRepository, SqlApprovalRepository, FixedClock(NOW), Uuid4Generator()
    )
    decider = caller(tenancy.alpha, principal=HEAD, scopes=frozenset())
    await settlement.settle(approval_id, decider)
    await settlement.settle(approval_id, decider)  # a redelivery writes nothing
    decided = await intake.case(me, case_id)
    assert decided.status is CaseStatus.APPROVED and decided.case_version == 3
    assert decided.decision is not None and decided.decision.comment == "Đồng ý theo báo giá"

    # Another tenant's decider finds nothing to carry out.
    with pytest.raises(NotFoundError):
        await settlement.settle(approval_id, caller(tenancy.beta, principal=HEAD))


async def test_one_approval_decides_one_case_and_a_sent_case_holds_its_approval(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy, migrator: object
) -> None:
    intake, approvals, _ = _services(app_sessions, tenancy)
    me = caller(tenancy.alpha)
    case_id = (await intake.read_mail(me, "P02")).case_id
    assert case_id is not None
    await approvals.submit(me, case_id, case_version=1)
    store = SqlPurchasingStore(app_sessions, SqlAuditRepository, SqlApprovalRepository)
    async with store(me) as work:
        session = work.cases._session  # the scoped transaction
        with pytest.raises(sa.exc.DBAPIError, match="ck_cases_sent"):
            async with session.begin_nested():
                await session.execute(
                    sa.text("UPDATE purchasing.cases SET status = 'received' WHERE id = :i"),
                    {"i": case_id},
                )
        with pytest.raises(sa.exc.DBAPIError, match="ck_cases_sent"):
            async with session.begin_nested():
                await session.execute(
                    sa.text("UPDATE purchasing.cases SET status = 'approved' WHERE id = :i"),
                    {"i": case_id},
                )

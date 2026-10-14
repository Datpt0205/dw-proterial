"""The demo tenant's own order rules, through the route a customer's would
take (ticket 19): proposed by its Sales PIC, approved by its Sales head.

The sample set holds the version (`adapters/mock/data/policies/`). It reaches
the database the way any tenant's version does: proposed through
`SalesRulesService`, which opens its `sales.rules` approval, decided on that
approval by the platform's `ApproveAndResumeService` with the Sales guard, and
carried out by `RuleSettlement` as the worker carries it out (ticket 38), each
step as a person whose access context is resolved from their membership. So
the demo exercises the maker/checker rule and the audit trail instead of a row
written around them. Re-running is a no-op once that version is in force.

Local and test profiles only (`demo_reset`, the API's integration suite).
"""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from dw_agent_runtime.adapters.run_store import SqlWorkerRunStore
from dw_agent_runtime.approval_flow import ApproveAndResumeService
from dw_agent_runtime.contracts import RunContext
from dw_kernel.ports import SystemClock, Uuid7Generator
from dw_platform.adapters.persistence.membership_lookup import SqlMembershipLookup
from dw_platform.adapters.persistence.repositories import (
    SqlApprovalRepository,
    SqlAuditRepository,
)
from dw_platform.adapters.persistence.uow import SqlPlatformUnitOfWorkFactory
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.application.identity import context_from
from dw_platform.testing.seed_env import sid
from dw_sales.adapters.mock.fixtures import DATA_DIR
from dw_sales.adapters.order_rules import load_tenant_order_rules
from dw_sales.adapters.persistence.rule_versions import SqlRuleVersionLookup
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.adapters.policy_files import load_sales_policies, rule_book
from dw_sales.application.access import Gate, sales_scope
from dw_sales.application.rules import (
    RULES_APPROVAL,
    RuleDecisions,
    RuleKey,
    RuleSettlement,
    SalesRulesService,
)

DEMO_TENANT = "tenant-alpha"
PROPOSER = "dev|an.nguyen"  # Sales PIC
APPROVER = "dev|giang.do"  # Sales head
_CONFIGS = Path(__file__).resolve().parents[6] / "configs"
# Long enough that no run of the seed's own counts as stale: it starts none.
_STALE_AFTER_SECONDS = 3600


class _NoRuns:
    """`WorkflowRunnerPort` for a process that decides run-less approvals
    only: a `sales.rules` approval has no run to resume, so nothing here is
    called, and a call is a defect rather than a silent no-op."""

    def hosts(self, *, worker_id: str, worker_version: str, graph_version: str) -> bool:
        raise NotImplementedError("not exercised by a run-less approval")

    async def start(
        self, *, run_context: RunContext, input_payload: dict[str, object]
    ) -> uuid.UUID:
        raise NotImplementedError("not exercised by a run-less approval")

    async def resume(
        self, *, run_context: RunContext, run_id: uuid.UUID, resume_payload: dict[str, object]
    ) -> None:
        raise NotImplementedError("not exercised by a run-less approval")

    async def withdraw(self, *, run_context: RunContext, run_id: uuid.UUID) -> None:
        raise NotImplementedError("not exercised by a run-less approval")


async def _context(sessions: async_sessionmaker[AsyncSession], subject: str) -> AccessContext:
    access = await SqlMembershipLookup(sessions).find_access(
        subject=subject,
        issuer="dev",
        tenant_id=sid("tenant", DEMO_TENANT),
        workspace_id=sid("workspace", f"{DEMO_TENANT}:main"),
    )
    if access is None:
        raise LookupError(f"{subject} has no membership in {DEMO_TENANT}: seed the personas first")
    return context_from(access)


async def seed_demo_rules(database_url: str) -> str | None:
    """Propose and approve the demo tenant's own order rules; the version in
    force afterwards, or None when the sample set holds none."""
    own = load_tenant_order_rules(DATA_DIR / "policies")
    if own is None:
        return None
    engine = create_async_engine(database_url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        lookup = SqlRuleVersionLookup(sessions)
        pic = await _context(sessions, PROPOSER)
        head = await _context(sessions, APPROVER)
        scope = sales_scope(pic)
        current = await lookup.approved(scope, RuleKey.ORDER_RULES)
        if current is not None and current.version == own.policy_version:
            return current.ref
        uow = SqlSalesUnitOfWorkFactory(
            sessions, audit=SqlAuditRepository, approvals=SqlApprovalRepository
        )
        book = rule_book(load_sales_policies(_CONFIGS / "policies", _CONFIGS / "copy"), lookup)
        clock, ids = SystemClock(), Uuid7Generator()
        service = SalesRulesService(uow, Gate(ScopeAuthorizationService()), book, clock, ids)
        stored = await lookup.find(scope, RuleKey.ORDER_RULES, own.policy_version)
        if stored is None or stored.status != "proposed" or stored.approval_id is None:
            document = own.model_dump(mode="json", by_alias=True)
            stored = await lookup.find(
                scope,
                RuleKey.ORDER_RULES,
                (await service.propose(pic, RuleKey.ORDER_RULES, document)).version,
            )
        assert stored is not None and stored.approval_id is not None
        flow = ApproveAndResumeService(
            uow_factory=SqlPlatformUnitOfWorkFactory(sessions),
            runner=_NoRuns(),
            run_store=SqlWorkerRunStore(sessions, stale_run_after_seconds=_STALE_AFTER_SECONDS),
            clock=clock,
            id_generator=ids,
            strict_approval_prefixes=frozenset({"sales."}),
            decision_guards={RULES_APPROVAL: RuleDecisions(uow, book)},
        )
        await flow.decide(
            approval_id=stored.approval_id,
            approve=True,
            comment="Bộ quy tắc demo của khách",
            context=head,
            authorization=ScopeAuthorizationService(),
        )
        # What the worker does with the `sales.rules.decided` event, done here so
        # the version is in force when the seed returns; the worker's own
        # delivery of the event then finds it settled and writes nothing.
        decided = await RuleSettlement(uow, book, clock, ids).settle(stored.approval_id, head)
        return decided.ref
    finally:
        await engine.dispose()

"""The demo tenant's own order rules, through the route a customer's would
take (ticket 19): proposed by its Sales PIC, approved by its Sales head.

The sample set holds the version (`adapters/mock/data/policies/`). It reaches
the database the way any tenant's version does, through `SalesRulesService`
with each person's access context resolved from their membership, so the
demo exercises the maker/checker rule and the audit trail instead of a row
written around them. Re-running is a no-op once that version is in force.

Local and test profiles only (`demo_reset`, the API's integration suite).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from dw_kernel.ports import SystemClock, Uuid7Generator
from dw_platform.adapters.persistence.membership_lookup import SqlMembershipLookup
from dw_platform.adapters.persistence.repositories import (
    SqlApprovalRepository,
    SqlAuditRepository,
)
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
from dw_sales.application.rules import RuleDecision, RuleKey, SalesRulesService

DEMO_TENANT = "tenant-alpha"
PROPOSER = "dev|an.nguyen"  # Sales PIC
APPROVER = "dev|giang.do"  # Sales head
_CONFIGS = Path(__file__).resolve().parents[6] / "configs"


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
        service = SalesRulesService(
            SqlSalesUnitOfWorkFactory(
                sessions, audit=SqlAuditRepository, approvals=SqlApprovalRepository
            ),
            Gate(ScopeAuthorizationService()),
            rule_book(load_sales_policies(_CONFIGS / "policies", _CONFIGS / "copy"), lookup),
            SystemClock(),
            Uuid7Generator(),
        )
        stored = await lookup.find(scope, RuleKey.ORDER_RULES, own.policy_version)
        if stored is not None and stored.status == "proposed":
            version_id = stored.version_id
        else:
            document = own.model_dump(mode="json", by_alias=True)
            version_id = (await service.propose(pic, RuleKey.ORDER_RULES, document)).version_id
        decided = await service.decide(
            head, version_id, RuleDecision(approve=True, comment="Bộ quy tắc demo của khách")
        )
        return decided.ref
    finally:
        await engine.dispose()

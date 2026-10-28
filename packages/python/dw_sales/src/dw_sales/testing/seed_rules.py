"""The demo tenant's own order rules, through the route a customer's would
take: applied by its Sales head, whose own version is in force at once
(2026-10-28, migration 40266fbc98bf: a PIC proposes nothing, the head applies
directly, and only an admin's proposal waits on the head's approval).

The sample set holds the version (`adapters/mock/data/policies/`). It reaches
the database the way any tenant's version does, through `SalesRulesService`
as a person whose access context is resolved from their membership, so the
audit trail records it as the head's. Re-running is a no-op once that version
is in force.

Which version is the caller's to name, because a version that turns a model
step on is refused unless the step's live eval met its bar for the model
DW1's profile routes it to (dw_sales ADR 0005, addendum of 2026-10-23):

- `DEMO_POLICIES`, `sales_order_rules@1.5.3`, every model step off: what
  `make demo-reset` installs. The mock demo runs with no model server (none is
  composed without `DW_ONPREM_MODEL_BASE_URL`) and records no measurement, a
  measurement being what a live run says, not what a seed asserts; so the
  tenant's own rules (the NOC/ESF hold, the price tolerance) are in force and
  nothing is refused. A developer with a local model attests the steps
  (`run_evals.py --live onprem --attest`) and proposes a version that turns
  them on, through the same route.
- `MODEL_STEP_POLICIES`, `sales_order_rules@1.5.2`, all six on: the API's
  integration suite, whose test database no live run reaches, records
  stand-in measurements first (`seed_test_measurements`, through the lane's
  own write path) and seeds this one, so the model steps run through the
  gate, not around it.

Local and test profiles only (`demo_reset`, the API's integration suite).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from dw_agent_runtime.registry import parse_worker_file
from dw_kernel.ports import SystemClock, Uuid7Generator
from dw_platform.adapters.persistence.directory import SqlWorkspaceDirectory
from dw_platform.adapters.persistence.membership_lookup import SqlMembershipLookup
from dw_platform.adapters.persistence.repositories import (
    SqlApprovalRepository,
    SqlAuditRepository,
)
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.application.identity import context_from
from dw_platform.testing.seed_env import sid
from dw_sales.adapters.assembly import model_readiness, step_model
from dw_sales.adapters.mock.fixtures import DATA_DIR
from dw_sales.adapters.order_rules import load_tenant_order_rules
from dw_sales.adapters.persistence.measurements import SqlMeasurementLog
from dw_sales.adapters.persistence.rule_versions import SqlRuleVersionLookup
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.adapters.policy_files import load_sales_policies, rule_book
from dw_sales.application.access import Gate, sales_scope
from dw_sales.application.model_readiness import BARS, ModelAttestation
from dw_sales.application.rules import (
    RuleKey,
    SalesRulesService,
)

DEMO_TENANT = "tenant-alpha"
# The demo tenant's version with every model step off (`make demo-reset`), and
# the sample set's own with all six on (tests over seeded measurements).
DEMO_POLICIES = DATA_DIR / "policies" / "no_model"
MODEL_STEP_POLICIES = DATA_DIR / "policies"
HEAD = "dev|giang.do"  # Sales head
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


async def seed_demo_rules(database_url: str, policies: Path) -> str | None:
    """Apply the demo tenant's own order rules, the version ``policies``
    holds (`DEMO_POLICIES` or `MODEL_STEP_POLICIES`), as its Sales head; the
    version in force afterwards, or None when ``policies`` holds none."""
    own = load_tenant_order_rules(policies)
    if own is None:
        return None
    engine = create_async_engine(database_url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        lookup = SqlRuleVersionLookup(sessions)
        head = await _context(sessions, HEAD)
        current = await lookup.approved(sales_scope(head), RuleKey.ORDER_RULES)
        if current is not None and current.version == own.policy_version:
            return current.ref
        uow = SqlSalesUnitOfWorkFactory(
            sessions, audit=SqlAuditRepository, approvals=SqlApprovalRepository
        )
        book = rule_book(load_sales_policies(_CONFIGS / "policies", _CONFIGS / "copy"), lookup)
        service = SalesRulesService(
            uow,
            Gate(ScopeAuthorizationService()),
            book,
            SystemClock(),
            Uuid7Generator(),
            SqlWorkspaceDirectory(sessions),
            model_readiness(_CONFIGS, sessions),
        )
        document = own.model_dump(mode="json", by_alias=True)
        return (await service.propose(head, RuleKey.ORDER_RULES, document)).ref
    finally:
        await engine.dispose()


async def seed_test_measurements(database_url: str) -> None:
    """For a test database only: a measurement at its bar of every model step
    for the demo tenant, on the model DW1's profile routes it to, written as
    the attesting lane writes one (`ModelAttestation`, audited). A stand-in
    for the live run a test database cannot have, so the suite exercises the
    model steps `MODEL_STEP_POLICIES` (1.5.2) turns on through the gate, not
    around it. Never called by `make demo-reset`."""
    engine = create_async_engine(database_url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        scope = sales_scope(await _context(sessions, HEAD))
        worker, _ = parse_worker_file(_CONFIGS / "workers" / "sales.yaml")
        model = step_model(_CONFIGS, worker.default_model_profile).model_for(scope.tenant_id.value)
        attest = ModelAttestation(
            SqlMeasurementLog(sessions, audit=SqlAuditRepository), SystemClock(), Uuid7Generator()
        )
        for step, owner in BARS.items():
            await attest.attest(
                scope,
                step,
                model=model,
                value=owner.bar,
                held=True,
                dataset=f"{owner.dataset}@1.0.0",
            )
    finally:
        await engine.dispose()

"""DW02 function 1 on PostgreSQL, as `dw_app` under RLS (migration 2d0c58dc3806).

The SQL store keeps what the in-memory one promises; each tenant and each
workspace sees only its own cases and mail outcomes, with no WHERE of its own
and none at all for a session that never scoped itself; an outcome is written
once and never rewritten; the catalog's CHECKs hold the domain's values; the
roles hold what they should and no platform role holds a `purchasing.*` scope;
and the service, end to end on the database, writes its audit row and reads a
tenant's own rules from the platform's override store.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from purchasing_harness import Tenancy
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_kernel.errors import ConflictError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.adapters.persistence.policy_overrides import SqlPolicyOverrideRepository
from dw_platform.adapters.persistence.repositories import (
    SqlApprovalRepository,
    SqlAuditRepository,
)
from dw_platform.domain.audit import AuditEvent
from dw_purchasing.adapters.mock.inbox import MockInbox
from dw_purchasing.adapters.persistence.store import SqlPurchasingStore
from dw_purchasing.adapters.policy_files import PolicyFiles
from dw_purchasing.application.access import Gate, PurchasingScopes
from dw_purchasing.application.intake import PurchaseRequests, Worker
from dw_purchasing.application.ports import Disposition, MessageOutcome
from dw_purchasing.application.rules import RuleBook
from dw_purchasing.domain.cases import (
    CaseStatus,
    PrSource,
    PurchaseCase,
)
from dw_purchasing.domain.requests import (
    PrLine,
    PurchaseRequest,
)
from dw_purchasing.testing.world import Authz, ScriptedModel, caller

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[5]
NOW = datetime(2026, 11, 2, 1, 0, tzinfo=UTC)
ANSWERS = json.loads(
    (REPO / "evals/fixtures/cases/purchasing_pr_intake.json").read_text(encoding="utf-8")
)["answers"]


def _case(*, source: PrSource = PrSource.FORM, ref: str | None = None) -> PurchaseCase:
    return PurchaseCase(
        case_id=uuid.uuid4(),
        case_version=1,
        status=CaseStatus.RECEIVED,
        source=source,
        source_ref=ref,
        request=PurchaseRequest(
            pr_no="PR-2611-020",
            department="Kho",
            requester="Trần Văn Kho",
            budget_code="CC-WH-01",
            currency="VND",
            lines=(PrLine(line_no=1, description="Pallet", quantity=Decimal(20), unit="cái"),),
        ),
        received_at=NOW,
        received_by=uuid.UUID(int=0xB0B),
        rules_ref="purchasing_rules@1.0.0",
    )


def _store(sessions: async_sessionmaker[AsyncSession]) -> SqlPurchasingStore:
    return SqlPurchasingStore(sessions, SqlAuditRepository, SqlApprovalRepository)


async def test_a_case_and_an_outcome_round_trip_in_their_own_workspace_only(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy
) -> None:
    store = _store(app_sessions)
    case = _case(source=PrSource.MAIL, ref="P01")
    outcome = MessageOutcome("P01", Disposition.OPENED, None, case.case_id, case.received_by, NOW)
    async with store(caller(tenancy.alpha)) as work:
        await work.cases.add(case)
        await work.outcomes.add(outcome)

    async with store(caller(tenancy.alpha)) as work:
        assert await work.cases.get(case.case_id) == case
        assert await work.outcomes.get("P01") == outcome
        assert list(await work.cases.page(limit=10, before=None)) == [case]
    for other in (tenancy.alpha_other, tenancy.beta):
        async with store(caller(other)) as work:
            assert await work.cases.get(case.case_id) is None
            assert await work.outcomes.all() == []
            assert await work.cases.page(limit=10, before=None) == []


async def test_a_session_that_never_scoped_itself_reads_nothing(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy
) -> None:
    async with _store(app_sessions)(caller(tenancy.alpha)) as work:
        await work.cases.add(_case())
    async with app_sessions() as session:
        for table in ("purchasing.cases", "purchasing.mail_outcomes"):
            count = (await session.execute(sa.text(f"SELECT count(*) FROM {table}"))).scalar()
            assert count == 0, table


async def test_a_mail_is_settled_once(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy
) -> None:
    store = _store(app_sessions)
    outcome = MessageOutcome(
        "P03", Disposition.TO_PERSON, "sender_not_internal", None, uuid.UUID(int=1), NOW
    )
    async with store(caller(tenancy.alpha)) as work:
        await work.outcomes.add(outcome)
    with pytest.raises(ConflictError):
        async with store(caller(tenancy.alpha)) as work:
            await work.outcomes.add(outcome)
    # Another workspace's mail with the same id is its own.
    async with store(caller(tenancy.alpha_other)) as work:
        await work.outcomes.add(outcome)


async def test_an_outcome_is_never_rewritten_nor_one_of_the_wrong_shape_written(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy
) -> None:
    store = _store(app_sessions)
    async with store(caller(tenancy.alpha)) as work:
        await work.outcomes.add(
            MessageOutcome(
                "P05", Disposition.TO_PERSON, "no_pr_number", None, uuid.UUID(int=1), NOW
            )
        )
    for statement in (
        "UPDATE purchasing.mail_outcomes SET reason = 'x'",
        "DELETE FROM purchasing.mail_outcomes",
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with store(caller(tenancy.alpha)) as work:
                await work.cases.get(uuid.uuid4())  # opens the scoped transaction
                await _execute(work, statement)
    # An opened mail names its case; one for a person gives its reason.
    with pytest.raises(DBAPIError, match="ck_mail_outcomes_shape"):
        async with store(caller(tenancy.alpha)) as work:
            await work.outcomes.add(
                MessageOutcome("P06", Disposition.OPENED, None, None, uuid.UUID(int=1), NOW)
            )


async def _execute(work: object, statement: str) -> None:
    session = work.cases._session  # type: ignore[attr-defined]
    await session.execute(sa.text(statement))


async def test_the_catalogs_checks_hold_the_domains_values(migrator: AsyncEngine) -> None:
    async with migrator.connect() as conn:
        rows = (
            await conn.execute(
                sa.text(
                    "SELECT conname, pg_get_constraintdef(oid) AS definition FROM pg_constraint"
                    " WHERE connamespace = 'purchasing'::regnamespace"
                    " AND conname IN ('ck_cases_status', 'ck_cases_source',"
                    " 'ck_mail_outcomes_disposition')"
                )
            )
        ).all()
    found = {row.conname: set(re.findall(r"'([a-z_]+)'::text", row.definition)) for row in rows}
    assert found == {
        "ck_cases_status": {s.value for s in CaseStatus},
        "ck_cases_source": {s.value for s in PrSource},
        "ck_mail_outcomes_disposition": {d.value for d in Disposition},
    }


async def test_the_application_holds_the_verbs_each_table_needs(migrator: AsyncEngine) -> None:
    async with migrator.connect() as conn:
        held = {
            (row.tbl, row.verb)
            for row in await conn.execute(
                sa.text(
                    "SELECT c.relname AS tbl, v.verb FROM pg_class c"
                    " JOIN pg_namespace n ON n.oid = c.relnamespace"
                    " CROSS JOIN unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE']) AS v(verb)"
                    " WHERE n.nspname = 'purchasing' AND c.relkind IN ('r', 'p')"
                    " AND has_table_privilege('dw_app', c.oid, v.verb)"
                )
            )
        }
    assert {v for t, v in held if t == "cases"} == {"SELECT", "INSERT", "UPDATE", "DELETE"}
    assert {v for t, v in held if t == "mail_outcomes"} == {"SELECT", "INSERT"}


async def test_the_roles_hold_purchasing_scopes_and_no_platform_role_does(
    migrator: AsyncEngine,
) -> None:
    async with migrator.connect() as conn:
        roles = {
            row.key: set(row.scopes)
            for row in await conn.execute(sa.text("SELECT key, scopes FROM platform.roles"))
        }
    every = {s.value for s in PurchasingScopes}
    read = PurchasingScopes.REQUEST_READ.value
    assert roles["purchasing_buyer"] == {
        read,
        PurchasingScopes.REQUEST_INTAKE.value,
        PurchasingScopes.REQUEST_SUBMIT.value,
        PurchasingScopes.RFQ_PREPARE.value,
    }
    assert roles["purchasing_viewer"] == {read}
    assert roles["purchasing_head"] == {
        read,
        PurchasingScopes.APPROVE_TIER1.value,
        PurchasingScopes.APPROVE_TIER2.value,
    }
    leaking = {k for k, s in roles.items() if not k.startswith("purchasing_") and s & every}
    assert leaking == set()
    async with migrator.connect() as conn:
        sets = {
            row.key: set(row.scopes)
            for row in await conn.execute(
                sa.text("SELECT key, scopes FROM platform.permission_sets")
            )
        }
    assert sets["purchasing_director_approver"] == {PurchasingScopes.APPROVE_TIER3.value}
    # Every scope a rule may stamp is held by someone the catalogue names.
    held = set().union(*roles.values(), *sets.values())
    assert every <= held


async def test_the_service_on_the_database_audits_and_reads_the_tenants_own_rules(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy
) -> None:
    files = PolicyFiles.load(REPO / "configs/policies")
    overrides = SqlPolicyOverrideRepository(app_sessions)
    service = PurchaseRequests(
        uow=_store(app_sessions),
        gate=Gate(Authz()),
        rules=RuleBook(files, overrides, files.versions),
        inbox=MockInbox.load(tenant_id=tenancy.alpha[0], workspace_id=tenancy.alpha[1]),
        model=ScriptedModel(ANSWERS),
        worker=Worker("purchasing-dw2", "1.0.0"),
        clock=FixedClock(NOW),
        ids=Uuid4Generator(),
    )
    me = caller(tenancy.alpha)
    opened = await service.read_mail(me, "P01")
    assert opened.disposition is Disposition.OPENED and opened.case_id is not None
    assert (await service.case(me, opened.case_id)).request.pr_no == "PR-2611-004"

    # The tenant's own version, from the platform's store: need-by required.
    document = {
        "version": "1.0.0-proterial.1",
        "pr_form": {
            "required": ["budget_code", "need_by"],
            "max_lines": 50,
            "currencies": ["VND"],
            "default_currency": "VND",
        },
        "internal_domains": ["seller.example"],
    }
    await overrides.put(me, "purchasing_rules", document, audit=_audit(me))
    routed = await service.read_mail(me, "P02")
    # P02's one line names its date.
    assert routed.disposition is Disposition.OPENED and routed.case_id is not None
    stamped = (await service.case(me, routed.case_id)).rules_ref
    assert stamped == "purchasing_rules@1.0.0-proterial.1"

    async with app_sessions() as session, session.begin():
        await session.execute(
            sa.text(
                "SELECT set_config('app.tenant_id', :t, true),"
                " set_config('app.workspace_id', :w, true)"
            ),
            {"t": str(tenancy.alpha[0]), "w": str(tenancy.alpha[1])},
        )
        actions = (
            (
                await session.execute(
                    sa.text(
                        "SELECT action FROM platform.audit_events"
                        " WHERE resource_type = 'purchase_case' ORDER BY occurred_at"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert list(actions).count("purchasing.request.received") == 2


def _audit(context: object) -> AuditEvent:
    from dw_platform.application.access_context import AccessContext

    assert isinstance(context, AccessContext)
    return AuditEvent(
        id=uuid.uuid4(),
        tenant_id=TenantId(context.tenant_id),
        workspace_id=WorkspaceId(context.workspace_id),
        actor_id=UserId(context.principal_id),
        action="platform.policy_override.put",
        resource_type="policy_override",
        resource_id="purchasing_rules",
        occurred_at=NOW,
    )

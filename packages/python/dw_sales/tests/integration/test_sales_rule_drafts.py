"""Rule drafts in PostgreSQL, as the application role ("Tạo từ tệp mẫu").

A template is requested through the service, drafted by the worker's step
from the id its outbox event carries, read back, and its bytes are gone; one
whose event was lost is failed by the sweep, its bytes gone too.
Each negative is checked against rows that are really there (read back as
the migrator), so a zero is isolation and not an empty table.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sales_harness import World
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_kernel.errors import NotFoundError
from dw_kernel.ports import SystemClock, Uuid4Generator
from dw_platform.adapters.persistence.repositories import (
    SqlApprovalRepository,
    SqlAuditRepository,
    SqlOutboxRepository,
)
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_sales.adapters.persistence.catalog import SqlCatalogUnitOfWorkFactory
from dw_sales.adapters.persistence.rule_drafts import SqlRuleDraftScopes
from dw_sales.adapters.persistence.rule_versions import SqlRuleVersionLookup
from dw_sales.adapters.policy_files import load_sales_policies, rule_book
from dw_sales.adapters.reader_client import ClientSourceView
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.application.access import Gate
from dw_sales.application.artifact_content import BravoUploadLayout
from dw_sales.application.ports import SalesScope
from dw_sales.application.rule_drafts import (
    RULE_DRAFT_REQUESTED,
    RuleDrafting,
    RuleDraftService,
    RuleDraftSweep,
    RuleDraftView,
)
from dw_sales.application.rules import RuleKey
from dw_sales.evals.graders import AN
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.rule_drafts import gold, template_xlsx
from dw_sales.evals.world import Directory
from dw_sales.testing.scanners import NoMalware

pytestmark = pytest.mark.integration

_REPO = Path(__file__).resolve().parents[5]
_CONFIGS = _REPO / "configs"
_TEMPLATE: dict[str, Any] = json.loads(
    (_REPO / "evals" / "fixtures" / "cases" / "sales_rule_drafts.json").read_text(encoding="utf-8")
)["golden"][0]


@pytest.fixture
def drafts(app_sessions: async_sessionmaker[AsyncSession]) -> SqlCatalogUnitOfWorkFactory:
    return SqlCatalogUnitOfWorkFactory(
        app_sessions,
        audit=SqlAuditRepository,
        approvals=SqlApprovalRepository,
        outbox=SqlOutboxRepository,
    )


def _service(drafts: SqlCatalogUnitOfWorkFactory) -> RuleDraftService:
    return RuleDraftService(
        drafts, Gate(ScopeAuthorizationService()), SystemClock(), Uuid4Generator()
    )


def _drafting(
    drafts: SqlCatalogUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    model: Recorded,
) -> RuleDrafting:
    policies = load_sales_policies(_CONFIGS / "policies", _CONFIGS / "copy")
    return RuleDrafting(
        uow=drafts,
        sheets=ClientSourceView(InProcessReaderTransport(), policies.order_rules.intake),
        scanner=NoMalware(),
        rules=rule_book(policies, SqlRuleVersionLookup(app_sessions)),
        access=Directory((AN,)),
        model=model,
        clock=SystemClock(),
        ids=Uuid4Generator(),
        worker_id="sales-dw1",
        worker_version="1.0.0",
    )


async def _count(migrator: AsyncEngine, sql: str, **params: object) -> int:
    async with migrator.connect() as conn:
        found = await conn.scalar(sa.text(sql), params)
    return int(found or 0)


async def _drafted(
    world: World,
    drafts: SqlCatalogUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
) -> RuleDraftView:
    """A template requested in alpha and drafted from its outbox event."""
    requested = await _service(drafts).request(
        AN.context(world.alpha), RuleKey.BRAVO_UPLOAD, "mau.xlsx", template_xlsx(_TEMPLATE)
    )
    async with migrator.connect() as conn:
        payload = await conn.scalar(
            sa.text(
                "SELECT payload FROM platform.outbox_events"
                " WHERE event_type = :type AND aggregate_id = :id"
            ),
            {"type": RULE_DRAFT_REQUESTED, "id": requested.draft_id},
        )
    assert payload == {"draft_id": str(requested.draft_id)}
    drafting = _drafting(drafts, app_sessions, Recorded(raw=gold(_TEMPLATE)))
    assert await drafting.draft(world.alpha, uuid.UUID(payload["draft_id"])) == "draft ready"
    return await _service(drafts).get(AN.context(world.alpha), requested.draft_id)


async def test_a_template_is_drafted_from_its_event_and_its_file_dropped(
    world: World,
    drafts: SqlCatalogUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
) -> None:
    view = await _drafted(world, drafts, app_sessions, migrator)
    assert view.status == "ready"
    layout = BravoUploadLayout.model_validate(view.document)
    assert [c.header for c in layout.columns] == [h for h, f in _TEMPLATE["columns"] if f]
    assert view.template is not None and view.evidence["sheet_name"] == view.template.span
    assert [p.code for p in view.problems] == ["column_unmapped"]
    left = await _count(
        migrator,
        "SELECT count(*) FROM sales.rule_draft_files WHERE draft_id = :id",
        id=view.draft_id,
    )
    assert left == 0
    actions = await _count(
        migrator,
        "SELECT count(*) FROM platform.audit_events WHERE resource_id = :id"
        " AND action IN ('sales.rule_draft.requested', 'sales.rule_draft.ready')",
        id=str(view.draft_id),
    )
    assert actions == 2


async def test_an_outsider_reads_no_draft(
    world: World,
    drafts: SqlCatalogUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
) -> None:
    # A queued one keeps its file: both tables hold a row of alpha's.
    queued = await _service(drafts).request(
        AN.context(world.alpha), RuleKey.BRAVO_UPLOAD, "mau.xlsx", template_xlsx(_TEMPLATE)
    )
    held = await _count(
        migrator,
        "SELECT count(*) FROM sales.rule_draft_files WHERE draft_id = :id",
        id=queued.draft_id,
    )
    assert held == 1, "the owner's rows are there: the zeros below are isolation"
    for outsider in (world.beta, world.alpha_other):
        with pytest.raises(NotFoundError):
            await _service(drafts).get(AN.context(outsider), queued.draft_id)
        # Asked of the policy alone: no WHERE names the scope here.
        async with tenant_session(
            app_sessions, TenantScope(outsider.tenant_id.value, outsider.workspace_id.value)
        ) as session:
            seen = [
                (await session.execute(sa.text(f"SELECT count(*) FROM sales.{table}"))).scalar()
                for table in ("rule_drafts", "rule_draft_files")
            ]
        assert seen == [0, 0], outsider


async def test_an_outsider_cannot_write_into_the_owners_scope(
    world: World, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    owner, outsider = world.alpha, world.beta
    with pytest.raises(DBAPIError, match="row-level security"):
        async with tenant_session(
            app_sessions, TenantScope(outsider.tenant_id.value, outsider.workspace_id.value)
        ) as session:
            await session.execute(
                sa.text(
                    "INSERT INTO sales.rule_drafts (id, tenant_id, workspace_id, rule_key,"
                    " status, requested_by, requested_at, file_name, file_sha256, file_size)"
                    " VALUES (gen_random_uuid(), :t, :w, 'sales_bravo_upload', 'queued',"
                    " gen_random_uuid(), now(), 'x.xlsx', repeat('0', 64), 1)"
                ),
                {"t": owner.tenant_id.value, "w": owner.workspace_id.value},
            )


async def test_the_database_refuses_what_a_draft_cannot_be(
    world: World,
    drafts: SqlCatalogUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
) -> None:
    view = await _drafted(world, drafts, app_sessions, migrator)
    for change, constraint in (
        # Shaped as no other check refuses it, so the status check is the one.
        ("status = 'drafted', document = NULL, template = NULL", "ck_rule_drafts_status"),
        ("rule_key = 'sales_emails'", "ck_rule_drafts_rule_key"),
        ("document = NULL", "ck_rule_drafts_document"),
        ("error = 'x'", "ck_rule_drafts_error"),
    ):
        async with migrator.connect() as conn:
            with pytest.raises(sa.exc.IntegrityError, match=constraint):
                await conn.execute(
                    sa.text(f"UPDATE sales.rule_drafts SET {change} WHERE id = :id"),
                    {"id": view.draft_id},
                )


async def test_a_template_file_is_never_rewritten(
    world: World,
    drafts: SqlCatalogUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    queued = await _service(drafts).request(
        AN.context(world.alpha), RuleKey.BRAVO_UPLOAD, "mau.xlsx", template_xlsx(_TEMPLATE)
    )
    scope: SalesScope = world.alpha
    with pytest.raises(DBAPIError, match="permission denied"):
        async with tenant_session(
            app_sessions, TenantScope(scope.tenant_id.value, scope.workspace_id.value)
        ) as session:
            await session.execute(
                sa.text("UPDATE sales.rule_draft_files SET content = 'x' WHERE draft_id = :id"),
                {"id": queued.draft_id},
            )


async def test_the_sweep_fails_a_lost_draft_in_its_own_workspace_only(
    world: World,
    drafts: SqlCatalogUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
) -> None:
    service = _service(drafts)
    data = template_xlsx(_TEMPLATE)
    lost = await service.request(AN.context(world.alpha), RuleKey.BRAVO_UPLOAD, "m.xlsx", data)
    fresh = await service.request(AN.context(world.beta), RuleKey.BRAVO_UPLOAD, "m.xlsx", data)
    async with migrator.begin() as conn:
        await conn.execute(
            sa.text(
                "UPDATE sales.rule_drafts SET requested_at = now() - interval '2 hours'"
                " WHERE id = :id"
            ),
            {"id": lost.draft_id},
        )
    sweep = RuleDraftSweep(
        drafts, SqlRuleDraftScopes(app_sessions), SystemClock(), Uuid4Generator()
    )

    # The one read across tenants, as the application role with no tenant set.
    due = await sweep.due()
    assert world.alpha in due and world.beta not in due
    swept = await sweep.sweep(world.alpha)
    assert swept.expired >= 1

    view = await service.get(AN.context(world.alpha), lost.draft_id)
    assert (view.status, view.error) == (
        "failed",
        "DW1 không đọc xong tệp trong 1 giờ: hãy tải lại tệp mẫu",
    )
    for draft_id, files in ((lost.draft_id, 0), (fresh.draft_id, 1)):
        held = await _count(
            migrator,
            "SELECT count(*) FROM sales.rule_draft_files WHERE draft_id = :id",
            id=draft_id,
        )
        assert held == files
    assert (await service.get(AN.context(world.beta), fresh.draft_id)).status == "queued"
    audited = await _count(
        migrator,
        "SELECT count(*) FROM platform.audit_events WHERE resource_id = :id"
        " AND action = 'sales.rule_draft.failed' AND tenant_id = :t"
        " AND details->>'actor' = 'system:sales_rule_drafts'",
        id=str(lost.draft_id),
        t=world.alpha.tenant_id.value,
    )
    assert audited == 1


async def test_only_the_application_role_may_ask_which_workspaces_are_due(
    migrator: AsyncEngine,
) -> None:
    function = "sales.rule_draft_scopes_due(timestamp with time zone, timestamp with time zone)"
    async with migrator.connect() as conn:
        app, public = (
            await conn.execute(
                sa.text(
                    "SELECT has_function_privilege('dw_app', :f, 'EXECUTE'),"
                    " has_function_privilege('public', :f, 'EXECUTE')"
                ),
                {"f": function},
            )
        ).one()
    assert (app, public) == (True, False)

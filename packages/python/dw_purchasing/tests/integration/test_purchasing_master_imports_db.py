"""DW2's master-data queue (migration cf783456f739) on PostgreSQL, as `dw_app`.

An upload is kept with its bytes until the lane reads it and never after; one
workspace holds one open import; another tenant or workspace reads none of
it, and a connection that never scoped itself reads nothing; the status and
what it holds agree by constraint; and a workbook the head submits becomes
the master data every check reads, through the platform's rule versions.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from purchasing_harness import Tenancy
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.adapters.persistence.repositories import (
    SqlApprovalRepository,
    SqlAuditRepository,
)
from dw_platform.adapters.persistence.rule_versions import SqlRuleVersionLookup
from dw_platform.application.malware import ScanVerdict
from dw_platform.application.rule_versions import ContextScope
from dw_purchasing.adapters.master_data import RuleMasterData
from dw_purchasing.adapters.master_template import XlsxMasterTemplate
from dw_purchasing.adapters.persistence.master_imports import SqlMasterImports
from dw_purchasing.adapters.persistence.store import SqlPurchasingStore
from dw_purchasing.adapters.policy_files import platform_rule_book
from dw_purchasing.application.access import Gate, PurchasingScopes
from dw_purchasing.application.master_data import (
    KEEP_FOR,
    MasterDataService,
    MasterImportLane,
)
from dw_purchasing.application.rules import PurchasingRulesService
from dw_purchasing.domain.master_lists import SheetRows
from dw_purchasing.testing.world import Authz, caller

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[5]
NOW = datetime(2026, 11, 2, 7, 0, tzinfo=UTC)
XLSX = b"PK\x03\x04 bytes kept until the lane reads them"
HEAD = frozenset({PurchasingScopes.RULES_PROPOSE.value, PurchasingScopes.RULES_APPROVE.value})
ITEMS: SheetRows = {
    "Vật tư": [(1, ["Mã vật tư", "Mô tả", "Đơn vị"]), (2, ["GT-01", "Găng tay", "đôi"])]
}


class Reader:
    async def sheets(self, data: bytes, wanted: Sequence[str]) -> SheetRows:
        return ITEMS


class Clean:
    async def scan(self, data: bytes) -> ScanVerdict:
        return ScanVerdict.clean()


def _desk(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock
) -> tuple[MasterDataService, MasterImportLane]:
    store = SqlPurchasingStore(sessions, SqlAuditRepository, SqlApprovalRepository)
    book = platform_rule_book(REPO / "configs/policies", SqlRuleVersionLookup(sessions))
    imports = SqlMasterImports(sessions, SqlAuditRepository)
    ids = Uuid4Generator()
    rules = PurchasingRulesService(uow=store, gate=Gate(Authz()), book=book, clock=clock, ids=ids)
    service = MasterDataService(
        gate=Gate(Authz()),
        imports=imports,
        rules=rules,
        book=book,
        template=XlsxMasterTemplate(),
        clock=clock,
        ids=ids,
    )
    return service, MasterImportLane(imports, Reader(), Clean(), clock, ids)


async def test_a_workbook_is_kept_until_read_then_its_bytes_are_gone(
    app_sessions: async_sessionmaker[AsyncSession], migrator: AsyncEngine, tenancy: Tenancy
) -> None:
    service, lane = _desk(app_sessions, FixedClock(NOW))
    sent = await service.upload(caller(tenancy.alpha, scopes=HEAD), "lists.xlsx", XLSX)
    async with migrator.connect() as conn:
        kept = await conn.scalar(
            sa.text("SELECT content FROM purchasing.master_imports WHERE id = :i"),
            {"i": sent.import_id},
        )
    assert bytes(kept) == XLSX

    assert await lane.tick(ContextScope.of(caller(tenancy.alpha))) == 1

    async with migrator.connect() as conn:
        row = (
            await conn.execute(
                sa.text(
                    "SELECT status, content, lists FROM purchasing.master_imports WHERE id = :i"
                ),
                {"i": sent.import_id},
            )
        ).one()
        actions = set(
            await conn.scalars(
                sa.text("SELECT action FROM platform.audit_events WHERE resource_id = :i"),
                {"i": str(sent.import_id)},
            )
        )
    assert (row.status, row.content) == ("parsed", None)
    assert [r["code"] for r in row.lists["items"]] == ["GT-01"]
    assert actions == {"purchasing.master_data.uploaded", "purchasing.master_data.read"}


async def test_a_new_upload_forgets_the_open_one_and_keeps_what_was_sent(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy
) -> None:
    clock = FixedClock(NOW)
    service, lane = _desk(app_sessions, clock)
    head = caller(tenancy.alpha, scopes=HEAD)
    sent = await service.upload(head, "a.xlsx", XLSX)
    await lane.tick(ContextScope.of(head))
    await service.submit(head, sent.import_id)
    clock.advance_to(NOW + timedelta(minutes=1))
    open_one = await service.upload(head, "b.xlsx", XLSX)
    clock.advance_to(NOW + timedelta(minutes=2))

    newest = await service.upload(head, "c.xlsx", XLSX)

    page = await service.overview(head)
    assert [i.import_id for i in page.imports] == [newest.import_id, sent.import_id]
    assert open_one.import_id not in {i.import_id for i in page.imports}


async def test_the_heads_workbook_becomes_the_master_data_every_check_reads(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy
) -> None:
    service, lane = _desk(app_sessions, FixedClock(NOW))
    head = caller(tenancy.alpha, scopes=HEAD)
    sent = await service.upload(head, "a.xlsx", XLSX)
    await lane.tick(ContextScope.of(head))

    done = await service.submit(head, sent.import_id)

    assert done.version_ref == "purchasing_master_data@1.0.1"
    book = platform_rule_book(REPO / "configs/policies", SqlRuleVersionLookup(app_sessions))
    assert set((await RuleMasterData(book).for_context(head)).items) == {"GT-01"}
    # Another tenant's checks read the platform's empty lists, never these.
    assert (await RuleMasterData(book).for_context(caller(tenancy.beta))).items == {}


async def test_another_tenant_or_workspace_reads_none_of_it(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy
) -> None:
    service, _ = _desk(app_sessions, FixedClock(NOW))
    sent = await service.upload(caller(tenancy.alpha, scopes=HEAD), "a.xlsx", XLSX)
    imports = SqlMasterImports(app_sessions, SqlAuditRepository)

    for other in (tenancy.alpha_other, tenancy.beta):
        scope = ContextScope.of(caller(other))
        assert await imports.get(scope, sent.import_id) is None
        assert await imports.recent(scope, limit=10) == []
        assert await imports.queued(scope, limit=10) == []


async def test_a_connection_that_never_scopes_itself_reads_nothing(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy
) -> None:
    service, _ = _desk(app_sessions, FixedClock(NOW))
    await service.upload(caller(tenancy.alpha, scopes=HEAD), "a.xlsx", XLSX)
    async with app_sessions() as session:
        seen = await session.scalar(sa.text("SELECT count(*) FROM purchasing.master_imports"))
    assert seen == 0


async def test_the_lane_forgets_what_it_read_long_ago_and_nothing_queued(
    app_sessions: async_sessionmaker[AsyncSession], migrator: AsyncEngine, tenancy: Tenancy
) -> None:
    clock = FixedClock(NOW)
    service, lane = _desk(app_sessions, clock)
    head = caller(tenancy.alpha_other, scopes=HEAD)
    read = await service.upload(head, "a.xlsx", XLSX)
    await lane.tick(ContextScope.of(head))
    # Sent, so no newer upload forgets it: only the lane's term does.
    await service.submit(head, read.import_id)
    clock.advance_to(NOW + KEEP_FOR + timedelta(days=1))
    # Uploaded long after, never read (the lane is told to read nothing).
    queued = await service.upload(head, "b.xlsx", XLSX)

    await lane.tick(ContextScope.of(head), limit=0)

    async with migrator.connect() as conn:
        left = set(
            await conn.scalars(
                sa.text("SELECT id FROM purchasing.master_imports WHERE workspace_id = :w"),
                {"w": head.workspace_id},
            )
        )
    assert left == {queued.import_id} and read.import_id not in left


@pytest.mark.parametrize(
    ("status", "content", "lists", "failure"),
    [
        ("queued", None, None, None),
        ("parsed", b"x", "{}", None),
        ("parsed", None, None, None),
        ("failed", None, None, None),
        ("done", None, None, None),
    ],
    ids=[
        "queued_without_bytes",
        "read_with_bytes",
        "parsed_without_lists",
        "failed_mute",
        "status",
    ],
)
async def test_a_status_and_what_the_row_holds_agree_by_constraint(
    migrator: AsyncEngine,
    tenancy: Tenancy,
    status: str,
    content: bytes | None,
    lists: str | None,
    failure: str | None,
) -> None:
    with pytest.raises(DBAPIError, match="ck_master_imports_"):
        async with migrator.begin() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO purchasing.master_imports (id, tenant_id, workspace_id,"
                    " file_name, sha256, content, status, uploaded_by, uploaded_at, read_at,"
                    " lists, failure) VALUES (:i, :t, :w, 'a.xlsx', :h, :c, :s, :u, now(),"
                    " CASE WHEN :s = 'queued' THEN NULL ELSE now() END,"
                    " CAST(:l AS jsonb), :f)"
                ),
                {
                    "i": uuid.uuid4(),
                    "t": tenancy.alpha[0],
                    "w": tenancy.alpha[1],
                    "h": "0" * 64,
                    "c": content,
                    "s": status,
                    "u": uuid.uuid4(),
                    "l": lists,
                    "f": failure,
                },
            )


async def test_the_application_holds_every_verb_of_its_queue(migrator: AsyncEngine) -> None:
    async with migrator.connect() as conn:
        verbs = (
            await conn.execute(
                sa.text(
                    "SELECT has_table_privilege('dw_app', 'purchasing.master_imports', v)"
                    " FROM unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE']) v"
                )
            )
        ).scalars()
        policed = (
            await conn.execute(
                sa.text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class"
                    " WHERE oid = 'purchasing.master_imports'::regclass"
                )
            )
        ).one()
    assert all(verbs)
    assert tuple(policed) == (True, True)


async def test_the_settings_page_never_reads_a_master_data_version(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy
) -> None:
    """A master-data version can hold thousands of rows: the settings list
    asks the store for its own keys only, so none is loaded there."""
    service, lane = _desk(app_sessions, FixedClock(NOW))
    head = caller(tenancy.alpha, scopes=HEAD)
    sent = await service.upload(head, "a.xlsx", XLSX)
    await lane.tick(ContextScope.of(head))
    await service.submit(head, sent.import_id)

    listed = await service.rules.list(head)

    assert {v.key for v in listed.versions} <= {"purchasing_rules", "purchasing_automation"}
    store = SqlPurchasingStore(app_sessions, SqlAuditRepository, SqlApprovalRepository)
    async with store(head) as work:
        held = await work.rule_versions.list_all(keys=("purchasing_rules",))
        every = await work.rule_versions.list_all()
    assert held == [] and {v.key for v in every} == {"purchasing_master_data"}

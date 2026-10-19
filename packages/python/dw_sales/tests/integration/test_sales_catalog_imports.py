"""Master-data snapshots in PostgreSQL, as the application role (ticket 41).

Written while Docker is down; owed a run (ticket 41's "Owed").
Each negative is checked against rows that are really there.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sales_harness import World
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_kernel.errors import ConflictError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_platform.adapters.persistence.repositories import (
    SqlApprovalRepository,
    SqlAuditRepository,
    SqlOutboxRepository,
)
from dw_platform.domain.approval import ApprovalRequest
from dw_sales.adapters.persistence.catalog import SqlApprovedLists, SqlCatalogUnitOfWorkFactory
from dw_sales.application.catalog_imports import CatalogSnapshot
from dw_sales.application.ports import SalesScope
from dw_sales.domain.master_data import CatalogList

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
_MAKER = uuid.UUID(int=0xA1)
_HEAD = uuid.UUID(int=0x61)
_LME = {"month": "2026-09", "usd_per_tonne": "9500"}


@pytest.fixture
def catalog_uow(app_sessions: async_sessionmaker[AsyncSession]) -> SqlCatalogUnitOfWorkFactory:
    return SqlCatalogUnitOfWorkFactory(
        app_sessions,
        audit=SqlAuditRepository,
        approvals=SqlApprovalRepository,
        outbox=SqlOutboxRepository,
    )


def _queued(snapshot_id: uuid.UUID | None = None) -> CatalogSnapshot:
    return CatalogSnapshot(
        snapshot_id=snapshot_id or uuid.uuid4(),
        catalog_list=CatalogList.LME,
        status="queued",
        source="file",
        file_name="lme.xlsx",
        file_sha256="0" * 64,
        file_size=4,
        imported_by=_MAKER,
        imported_at=_NOW,
        as_of=_NOW,
    )


async def _approved(uow: SqlCatalogUnitOfWorkFactory, scope: SalesScope) -> CatalogSnapshot:
    """A snapshot taken through every status as the services take it."""
    queued = _queued()
    approval_id = uuid.uuid4()
    async with uow(scope) as work:
        await work.snapshots.add(queued, b"data")
        parsed = queued.model_copy(update={"status": "parsed", "row_count": 1})
        assert await work.snapshots.update(parsed, expected="queued")
        await work.snapshots.write_records(queued.snapshot_id, [("2026-09", _LME)])
        await work.approvals.add(
            ApprovalRequest(
                id=approval_id,
                tenant_id=TenantId(scope.tenant_id.value),
                workspace_id=WorkspaceId(scope.workspace_id.value),
                approval_type="sales.catalog",
                requested_by=UserId(_MAKER),
                reason="test",
                payload={"makers": [str(_MAKER)]},
                required_scope="sales.master_data.approve",
            )
        )
        submitted = parsed.model_copy(
            update={
                "status": "submitted",
                "submitted_by": _MAKER,
                "submitted_at": _NOW,
                "approval_id": approval_id,
            }
        )
        assert await work.snapshots.update(submitted, expected="parsed")
        approved = submitted.model_copy(
            update={"status": "approved", "decided_by": _HEAD, "decided_at": _NOW}
        )
        assert await work.snapshots.update(approved, expected="submitted")
        await work.commit()
    return approved


async def test_a_snapshot_is_read_in_its_workspace_only(
    world: World,
    catalog_uow: SqlCatalogUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
) -> None:
    approved = await _approved(catalog_uow, world.alpha)
    async with migrator.connect() as conn:
        held = await conn.scalar(
            sa.text("SELECT count(*) FROM sales.catalog_rows WHERE snapshot_id = :id"),
            {"id": approved.snapshot_id},
        )
    assert held == 1
    lists = SqlApprovedLists(app_sessions)
    mine = await lists.approved(world.alpha, CatalogList.LME)
    assert mine is not None and mine.snapshot_id == approved.snapshot_id
    for outsider in (world.beta, world.alpha_other):
        assert await lists.approved(outsider, CatalogList.LME) is None
        async with catalog_uow(outsider) as work:
            assert await work.snapshots.get(approved.snapshot_id) is None
            assert await work.snapshots.records(approved.snapshot_id) == []
            assert await work.snapshots.approved(CatalogList.LME) is None
    # The kept list is keyed by scope: beta asking again, after alpha's was
    # kept, still reads nothing.
    assert await lists.approved(world.beta, CatalogList.LME) is None


async def test_the_file_is_dropped_once_read_and_one_import_per_list_stays_open(
    world: World, catalog_uow: SqlCatalogUnitOfWorkFactory, migrator: AsyncEngine
) -> None:
    queued = _queued()
    async with catalog_uow(world.alpha) as work:
        await work.snapshots.add(queued, b"data")
        await work.commit()
    with pytest.raises(ConflictError):
        async with catalog_uow(world.alpha) as work:
            await work.snapshots.add(_queued(), b"data")
    async with catalog_uow(world.alpha) as work:
        assert await work.snapshots.content(queued.snapshot_id) == b"data"
        failed = queued.model_copy(update={"status": "failed", "error": "x"})
        assert await work.snapshots.update(failed, expected="queued")
        assert not await work.snapshots.update(failed, expected="queued")
        await work.commit()
    async with migrator.connect() as conn:
        left = await conn.scalar(
            sa.text("SELECT count(*) FROM sales.catalog_import_files WHERE snapshot_id = :id"),
            {"id": queued.snapshot_id},
        )
    assert left == 0


async def test_the_database_refuses_a_maker_as_the_decider(
    world: World, catalog_uow: SqlCatalogUnitOfWorkFactory, migrator: AsyncEngine
) -> None:
    approved = await _approved(catalog_uow, world.alpha)
    async with migrator.connect() as conn:
        with pytest.raises(sa.exc.IntegrityError, match="ck_catalog_snapshots_checker_not_maker"):
            await conn.execute(
                sa.text(
                    "UPDATE sales.catalog_snapshots SET decided_by = imported_by WHERE id = :id"
                ),
                {"id": approved.snapshot_id},
            )


async def test_a_catalog_approval_is_stamped_with_the_approve_scope(
    world: World, catalog_uow: SqlCatalogUnitOfWorkFactory
) -> None:
    with pytest.raises((ConflictError, sa.exc.IntegrityError)):
        async with catalog_uow(world.alpha) as work:
            await work.approvals.add(
                ApprovalRequest(
                    id=uuid.uuid4(),
                    tenant_id=TenantId(world.alpha.tenant_id.value),
                    workspace_id=WorkspaceId(world.alpha.workspace_id.value),
                    approval_type="sales.catalog",
                    requested_by=UserId(_MAKER),
                    reason="test",
                    required_scope="sales.rules.approve",
                )
            )

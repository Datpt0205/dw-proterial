"""SQL side of the processing queue (ticket 25, migration 0a78ca5e96d3).

- `SqlProcessingJobs`, a unit of work's `jobs`: enqueue (one row per message,
  an upsert that leaves an active job alone), read, and settle a claimed job,
  inside the workspace's transaction and its RLS.
- `SqlProcessingQueue`, the worker's drain: the scopes with anything due come
  from `sales.processing_scopes_due()` (SECURITY DEFINER, ids only); the claim
  then runs bound to one of them, `FOR UPDATE SKIP LOCKED`, so two workers
  never take the same job and neither waits on the other. Which scope is
  visited first is shuffled per claim: a tenant that queues a whole mailbox
  does not hold every other tenant's mail behind it. Reaping goes through
  `sales.reap_processing_jobs()`, the one write that crosses tenants, and it
  touches only rows a dead worker left running.
"""

from __future__ import annotations

import random
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.adapters.persistence.tenant_session import TenantScope, bind_tenant
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import scope_values
from dw_sales.application.case_store import ProcessingJob, Settlement
from dw_sales.application.ports import SalesScope
from dw_sales.application.processing import MAX_ATTEMPTS, ClaimedJob

_J = tables.processing_jobs

_SCOPES_DUE = sa.text("SELECT tenant_id, workspace_id FROM sales.processing_scopes_due()")
_REAP = sa.text("SELECT id FROM sales.reap_processing_jobs(:older_than, :max_attempts)")


def _job(row: RowMapping) -> ProcessingJob:
    return ProcessingJob(
        job_id=row["id"],
        message_id=row["message_id"],
        status=row["status"],
        requested_by=row["requested_by"],
        requested_at=row["requested_at"],
        attempts=row["attempts"],
        failures=row["failures"],
        available_at=row["available_at"],
        error=row["error"],
        updated_at=row["updated_at"],
    )


@dataclass(frozen=True)
class SqlProcessingJobs:
    """Implements `ProcessingJobsPort`."""

    session: AsyncSession
    scope: SalesScope

    async def enqueue(
        self, message_id: str, requested_by: uuid.UUID, at: datetime, job_id: uuid.UUID
    ) -> tuple[ProcessingJob, bool]:
        insert = pg_insert(_J).values(
            id=job_id,
            **scope_values(self.scope),
            message_id=message_id,
            status="queued",
            requested_by=requested_by,
            requested_at=at,
            attempts=0,
            failures=0,
            available_at=at,
            updated_at=at,
        )
        # Back in the queue only from a finished state: an active job is the
        # one this request would have made, and is returned unchanged below.
        upsert = insert.on_conflict_do_update(
            constraint="uq_processing_jobs_message",
            set_={
                "status": "queued",
                "requested_by": insert.excluded.requested_by,
                "requested_at": insert.excluded.requested_at,
                "attempts": 0,
                "available_at": insert.excluded.available_at,
                "claimed_at": None,
                "error": None,
                "updated_at": insert.excluded.updated_at,
            },
            where=_J.c.status.in_(("done", "failed")),
        ).returning(*_J.c)
        row = (await self.session.execute(upsert)).mappings().first()
        if row is not None:
            return _job(row), True
        existing = await self.get(message_id)
        assert existing is not None and existing.active  # the conflict that skipped the update
        return existing, False

    async def get(self, message_id: str) -> ProcessingJob | None:
        row = (
            (
                await self.session.execute(
                    sa.select(_J).where(*self._mine(), _J.c.message_id == message_id)
                )
            )
            .mappings()
            .first()
        )
        return None if row is None else _job(row)

    async def list_all(self) -> Sequence[ProcessingJob]:
        rows = (await self.session.execute(sa.select(_J).where(*self._mine()))).mappings().all()
        return [_job(row) for row in rows]

    async def settle(self, job: ProcessingJob, outcome: Settlement, at: datetime) -> bool:
        values: dict[str, Any] = {"status": outcome.status, "claimed_at": None, "updated_at": at}
        match outcome.status:
            case "done":
                values |= {"error": None, "failures": 0}
            case "queued":
                values |= {"error": None, "available_at": outcome.available_at or at}
            case "failed":
                values |= {"error": outcome.error, "failures": _J.c.failures + 1}
        settled = await self.session.execute(
            sa.update(_J)
            .where(
                *self._mine(),
                _J.c.id == job.job_id,
                _J.c.status == "running",
                # The claim's token: a job reaped and claimed again since
                # carries a higher count, and is not this caller's to settle.
                _J.c.attempts == job.attempts,
            )
            .values(**values)
            .returning(_J.c.id)
        )
        return settled.first() is not None

    def _mine(self) -> tuple[sa.ColumnElement[bool], ...]:
        return (
            _J.c.tenant_id == self.scope.tenant_id.value,
            _J.c.workspace_id == self.scope.workspace_id.value,
        )


@dataclass(frozen=True)
class SqlProcessingQueue:
    """Implements `ProcessingQueuePort` (module docstring)."""

    session_factory: async_sessionmaker[AsyncSession]

    async def claim(self) -> ClaimedJob | None:
        async with self.session_factory() as session:
            scopes = list((await session.execute(_SCOPES_DUE)).all())
        random.shuffle(scopes)
        for tenant_id, workspace_id in scopes:
            claimed = await self._claim_in(
                SalesScope(TenantId(tenant_id), WorkspaceId(workspace_id))
            )
            if claimed is not None:
                return claimed
        return None

    async def reap_stale(self, *, older_than: datetime) -> Sequence[uuid.UUID]:
        async with self.session_factory() as session, session.begin():
            rows = await session.execute(
                _REAP, {"older_than": older_than, "max_attempts": MAX_ATTEMPTS}
            )
            return list(rows.scalars().all())

    async def _claim_in(self, scope: SalesScope) -> ClaimedJob | None:
        async with self.session_factory() as session, session.begin():
            await bind_tenant(
                session,
                TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value),
            )
            mine = (
                _J.c.tenant_id == scope.tenant_id.value,
                _J.c.workspace_id == scope.workspace_id.value,
            )
            due = (
                await session.execute(
                    sa.select(_J.c.id)
                    .where(*mine, _J.c.status == "queued", _J.c.available_at <= sa.func.now())
                    # Oldest due first; at one instant, the order queued.
                    .order_by(_J.c.available_at, _J.c.seq)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            ).scalar_one_or_none()
            if due is None:
                return None
            row = (
                (
                    await session.execute(
                        sa.update(_J)
                        .where(*mine, _J.c.id == due)
                        .values(
                            status="running",
                            attempts=_J.c.attempts + 1,
                            claimed_at=sa.func.now(),
                        )
                        .returning(*_J.c)
                    )
                )
                .mappings()
                .one()
            )
            return ClaimedJob(scope, _job(row))

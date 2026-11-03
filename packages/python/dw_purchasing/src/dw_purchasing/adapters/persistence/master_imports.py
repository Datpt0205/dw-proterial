"""DW2's queue of uploaded master-data workbooks (migration cf783456f739).

`SqlMasterImports` implements `MasterImportsPort` for the page (the API) and
the `purchasing_master_import` lane (the worker). Each call is one short
transaction bound to the scope it is asked about, its audit event inside it;
RLS keeps one workspace's uploads from another. The bytes are selected only
by the lane, and only while the file waits to be read.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.application.rule_versions import ContextScope
from dw_platform.domain.audit import AuditEvent
from dw_purchasing.adapters.persistence.store import AuditFactory, metadata
from dw_purchasing.application.master_data import MasterImport
from dw_purchasing.domain.master_lists import ParsedWorkbook

_TS = sa.TIMESTAMP(timezone=True)

master_imports = sa.Table(
    "master_imports",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
    sa.Column("file_name", sa.Text, nullable=False),
    sa.Column("sha256", sa.Text, nullable=False),
    sa.Column("content", sa.LargeBinary),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("uploaded_by", UUID(as_uuid=True), nullable=False),
    sa.Column("uploaded_at", _TS, nullable=False),
    sa.Column("read_at", _TS),
    sa.Column("lists", JSONB),
    sa.Column("rejected", JSONB, nullable=False),
    sa.Column("rejected_total", sa.Integer, nullable=False),
    sa.Column("failure", sa.Text),
    sa.Column("version_ref", sa.Text),
    sa.Column("submitted_by", UUID(as_uuid=True)),
    sa.Column("submitted_at", _TS),
)

_I = master_imports
# Every column but the bytes: what a page reads.
_SEEN = [c for c in _I.c if c.name != "content"]


def _bound(scope: ContextScope) -> TenantScope:
    return TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)


def _record(row: Any) -> MasterImport:
    return MasterImport(
        import_id=row.id,
        file_name=row.file_name,
        sha256=row.sha256,
        status=row.status,
        uploaded_by=row.uploaded_by,
        uploaded_at=row.uploaded_at,
        read_at=row.read_at,
        lists=row.lists,
        rejected=row.rejected,
        rejected_total=row.rejected_total,
        failure=row.failure,
        version_ref=row.version_ref,
        submitted_by=row.submitted_by,
        submitted_at=row.submitted_at,
    )


@dataclass(frozen=True)
class SqlMasterImports:
    """Implements `MasterImportsPort`."""

    session_factory: async_sessionmaker[AsyncSession]
    audit: AuditFactory

    async def add(self, record: MasterImport, content: bytes, event: AuditEvent) -> None:
        scope = TenantScope(tenant_id=event.tenant_id.value, workspace_id=event.workspace_id.value)
        async with tenant_session(self.session_factory, scope) as session:
            # One open import per workspace: an upload replaces the one not
            # sent yet, so two files are never compared or sent at once.
            await session.execute(sa.delete(_I).where(_I.c.status.in_(("queued", "parsed"))))
            await session.execute(
                sa.insert(_I).values(
                    id=record.import_id,
                    tenant_id=scope.tenant_id,
                    workspace_id=scope.workspace_id,
                    file_name=record.file_name,
                    sha256=record.sha256,
                    content=content,
                    status="queued",
                    uploaded_by=record.uploaded_by,
                    uploaded_at=record.uploaded_at,
                    rejected=[],
                    rejected_total=0,
                )
            )
            await self.audit(session).append(event)

    async def recent(self, scope: ContextScope, *, limit: int) -> Sequence[MasterImport]:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            rows = await session.execute(
                sa.select(*_SEEN).order_by(_I.c.uploaded_at.desc(), _I.c.id.desc()).limit(limit)
            )
            return [_record(row) for row in rows]

    async def get(self, scope: ContextScope, import_id: uuid.UUID) -> MasterImport | None:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            row = (await session.execute(sa.select(*_SEEN).where(_I.c.id == import_id))).first()
        return None if row is None else _record(row)

    async def submitted(
        self, record: MasterImport, *, ref: str, by: uuid.UUID, at: datetime, event: AuditEvent
    ) -> bool:
        scope = TenantScope(tenant_id=event.tenant_id.value, workspace_id=event.workspace_id.value)
        async with tenant_session(self.session_factory, scope) as session:
            marked = await session.scalar(
                sa.update(_I)
                .where(_I.c.id == record.import_id, _I.c.status == "parsed")
                .values(status="submitted", version_ref=ref, submitted_by=by, submitted_at=at)
                .returning(_I.c.id)
            )
            if marked is None:
                return False
            await self.audit(session).append(event)
        return True

    async def queued(
        self, scope: ContextScope, *, limit: int
    ) -> Sequence[tuple[MasterImport, bytes]]:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            rows = await session.execute(
                sa.select(*_SEEN, _I.c.content)
                .where(_I.c.status == "queued")
                .order_by(_I.c.uploaded_at, _I.c.id)
                .limit(limit)
            )
            return [(_record(row), bytes(row.content)) for row in rows]

    async def read(
        self,
        scope: ContextScope,
        import_id: uuid.UUID,
        parsed: ParsedWorkbook,
        *,
        at: datetime,
        event: AuditEvent,
    ) -> None:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            done = await session.scalar(
                sa.update(_I)
                .where(_I.c.id == import_id, _I.c.status == "queued")
                .values(
                    status="failed" if parsed.failure else "parsed",
                    content=None,
                    read_at=at,
                    lists=None if parsed.failure else parsed.lists,
                    rejected=[r.model_dump(mode="json") for r in parsed.rejected],
                    rejected_total=parsed.rejected_total,
                    failure=parsed.failure[:400] if parsed.failure else None,
                )
                .returning(_I.c.id)
            )
            # Forgotten meanwhile by a newer upload: nothing to say about it.
            if done is not None:
                await self.audit(session).append(event)

    async def forget(self, scope: ContextScope, *, read_before: datetime) -> int:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            gone = await session.execute(
                sa.delete(_I).where(_I.c.read_at < read_before).returning(_I.c.id)
            )
            return len(gone.all())

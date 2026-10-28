"""`ExportControlUnitOfWork` on PostgreSQL: the latest export-control result
per customer and step (`sales.export_control_screenings`), and its audit row,
in one transaction bound to one workspace (`bind_tenant`)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Self

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, bind_tenant
from dw_platform.application.ports import AuditRepositoryPort
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import scope_values
from dw_sales.application.ports import SalesScope
from dw_sales.domain.export_control import Evidence, ScreeningRecord, ScreeningStep

_S = tables.export_control_screenings
AuditFactory = Callable[[AsyncSession], AuditRepositoryPort]


class SqlScreenings:
    """Implements `ScreeningStorePort` in one bound session."""

    def __init__(self, session: AsyncSession, scope: SalesScope) -> None:
        self._session, self._scope = session, scope

    async def records(self) -> Sequence[ScreeningRecord]:
        rows = (await self._session.execute(sa.select(_S).order_by(_S.c.customer_code))).mappings()
        return [_record(row) for row in rows]

    async def put(self, record: ScreeningRecord) -> None:
        evidence = record.evidence
        values = {
            **scope_values(self._scope),
            "customer_code": record.customer_code,
            "step": record.step.value,
            "outcome": record.outcome,
            "checked_on": record.checked_on,
            "fiscal_year": record.fiscal_year,
            "answers": dict(record.answers),
            "note": record.note,
            "evidence_file_id": evidence.file_id if evidence else None,
            "evidence_sha256": evidence.sha256 if evidence else None,
            "evidence_content_type": evidence.content_type if evidence else None,
            "evidence_size": evidence.size_bytes if evidence else None,
            "recorded_by": record.recorded_by,
            "recorded_at": record.recorded_at,
        }
        statement = insert(_S).values(**values)
        replaced = {k: statement.excluded[k] for k in values if k not in _KEY}
        await self._session.execute(
            statement.on_conflict_do_update(index_elements=list(_KEY), set_=replaced)
        )


_KEY = ("tenant_id", "workspace_id", "customer_code", "step")


def _record(row: RowMapping) -> ScreeningRecord:
    evidence = (
        Evidence(
            file_id=row["evidence_file_id"],
            sha256=row["evidence_sha256"],
            content_type=row["evidence_content_type"],
            size_bytes=row["evidence_size"],
        )
        if row["evidence_file_id"] is not None
        else None
    )
    return ScreeningRecord(
        customer_code=row["customer_code"],
        step=ScreeningStep(row["step"]),
        outcome=row["outcome"],
        checked_on=row["checked_on"],
        fiscal_year=row["fiscal_year"],
        answers=row["answers"],
        note=row["note"],
        evidence=evidence,
        recorded_by=row["recorded_by"],
        recorded_at=row["recorded_at"],
    )


class SqlExportControlUnitOfWork:
    """Implements `ExportControlUnitOfWork`."""

    screenings: SqlScreenings
    audit: AuditRepositoryPort

    def __init__(self, factory: SqlExportControlUnitOfWorkFactory, scope: SalesScope) -> None:
        self._factory, self._scope = factory, scope
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> Self:
        session = self._factory.session_factory()
        try:
            await session.begin()
            await bind_tenant(
                session,
                TenantScope(
                    tenant_id=self._scope.tenant_id.value,
                    workspace_id=self._scope.workspace_id.value,
                ),
            )
        except BaseException:
            await session.close()
            raise
        self._session = session
        self.screenings = SqlScreenings(session, self._scope)
        self.audit = self._factory.audit(session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._session is not None, "unit of work not entered"
        try:
            await self._session.rollback()
        finally:
            await self._session.close()
            self._session = None

    async def commit(self) -> None:
        assert self._session is not None, "unit of work not entered"
        await self._session.commit()


@dataclass(frozen=True)
class SqlExportControlUnitOfWorkFactory:
    """Implements `ExportControlUnitOfWorkFactory`."""

    session_factory: async_sessionmaker[AsyncSession]
    audit: AuditFactory

    def __call__(self, scope: SalesScope) -> SqlExportControlUnitOfWork:
        return SqlExportControlUnitOfWork(self, scope)

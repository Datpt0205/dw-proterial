"""The sales unit of work: one transaction bound to one tenant's workspace.

`app.tenant_id` and `app.workspace_id` are set for the transaction only
(`bind_tenant`), from the scope the caller resolved from a verified access
context, so every policy on `sales.*` narrows to that workspace and a pooled
connection carries nothing into the next caller.

The platform audit repository is handed in as a factory over the session, by
the composition root: the audit row is written in this same transaction, and
this package names no platform adapter.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, bind_tenant
from dw_platform.application.ports import AuditRepositoryPort
from dw_sales.adapters.persistence.orders import SqlOrderCaseRepository
from dw_sales.adapters.persistence.quotes import SqlQuoteCaseRepository
from dw_sales.adapters.persistence.records import (
    SqlArtifactLog,
    SqlMessageLog,
    SqlSourceServed,
    SqlWorkerSwitch,
)
from dw_sales.application.ports import SalesScope

AuditFactory = Callable[[AsyncSession], AuditRepositoryPort]


class SqlSalesUnitOfWork:
    """Implements `SalesUnitOfWork`."""

    orders: SqlOrderCaseRepository
    quotes: SqlQuoteCaseRepository
    messages: SqlMessageLog
    served: SqlSourceServed
    artifacts: SqlArtifactLog
    worker: SqlWorkerSwitch
    audit: AuditRepositoryPort

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        scope: SalesScope,
        audit: AuditFactory,
    ) -> None:
        self._session_factory = session_factory
        self._scope = scope
        self._audit = audit
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> Self:
        session = self._session_factory()
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
        scope = self._scope
        self.orders = SqlOrderCaseRepository(session, scope)
        self.quotes = SqlQuoteCaseRepository(session, scope)
        self.messages = SqlMessageLog(session, scope)
        self.served = SqlSourceServed(session, scope)
        self.artifacts = SqlArtifactLog(session, scope)
        self.worker = SqlWorkerSwitch(session, scope)
        self.audit = self._audit(session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._session is not None, "unit of work not entered"
        try:
            # Anything not committed is rolled back, an exception or not.
            await self._session.rollback()
        finally:
            await self._session.close()
            self._session = None

    async def commit(self) -> None:
        assert self._session is not None, "unit of work not entered"
        await self._session.commit()


@dataclass(frozen=True)
class SqlSalesUnitOfWorkFactory:
    """Implements `SalesUnitOfWorkFactory`."""

    session_factory: async_sessionmaker[AsyncSession]
    audit: AuditFactory

    def __call__(self, scope: SalesScope) -> SqlSalesUnitOfWork:
        return SqlSalesUnitOfWork(self.session_factory, scope, self.audit)

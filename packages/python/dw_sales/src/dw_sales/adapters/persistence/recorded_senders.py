"""`RecordedSendersPort` on PostgreSQL (`sales.recorded_customer_senders`,
migration `7f94b09d1905`): the senders Sales confirmed as a customer's, read
the same by the API and the worker, in one transaction bound to the scope."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import scope_values
from dw_sales.application.ports import SalesScope
from dw_sales.application.snapshot_catalog import RecordedSender

_S = tables.recorded_customer_senders


def _bound(scope: SalesScope) -> TenantScope:
    return TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)


@dataclass(frozen=True)
class SqlRecordedSenders:
    """Implements `RecordedSendersPort`."""

    session_factory: async_sessionmaker[AsyncSession]

    async def sender(self, scope: SalesScope, address: str) -> RecordedSender | None:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            row = (
                await session.execute(
                    sa.select(_S.c.customer_code, _S.c.recorded_at).where(
                        _S.c.tenant_id == scope.tenant_id.value,
                        _S.c.workspace_id == scope.workspace_id.value,
                        _S.c.sender_address == address,
                    )
                )
            ).one_or_none()
            return None if row is None else RecordedSender(row.customer_code, row.recorded_at)

    async def learn(
        self,
        scope: SalesScope,
        address: str,
        customer_code: str,
        *,
        by: uuid.UUID,
        message_id: str,
    ) -> None:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            await session.execute(
                insert(_S)
                .values(
                    **scope_values(scope),
                    sender_address=address,
                    customer_code=customer_code,
                    confirmed_by=by,
                    message_id=message_id,
                )
                .on_conflict_do_nothing()
            )

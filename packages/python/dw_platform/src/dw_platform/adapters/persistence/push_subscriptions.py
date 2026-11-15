"""`PushSubscriptionStorePort` on PostgreSQL (`platform.push_subscriptions`,
migration 4bcfa82060fc), and its retention.

Every statement runs in a transaction bound to one tenant, workspace AND
person (`tenant_session`): the table's policy reads all three, so another
person's device is not found whatever is asked, and each statement names the
three again, so a policy dropped by mistake still finds nothing. A row is
written only through `platform.save_push_subscription`, which reads the
three from that binding.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence import tables
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.application.access_context import AccessContext
from dw_platform.application.web_push import PushSubscription

_p = tables.push_subscriptions
_SAVE = sa.text("SELECT platform.save_push_subscription(:endpoint, :p256dh, :auth)")


def _theirs(
    tenant_id: uuid.UUID, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[sa.ColumnElement[bool], ...]:
    return (
        _p.c.tenant_id == tenant_id,
        _p.c.workspace_id == workspace_id,
        _p.c.user_id == user_id,
    )


@dataclass(frozen=True)
class SqlPushSubscriptions:
    """Implements `dw_platform.application.web_push.PushSubscriptionStorePort`."""

    session_factory: async_sessionmaker[AsyncSession]

    async def save(self, context: AccessContext, *, endpoint: str, p256dh: str, auth: str) -> None:
        async with tenant_session(
            self.session_factory, TenantScope.from_access_context(context)
        ) as session:
            await session.execute(_SAVE, {"endpoint": endpoint, "p256dh": p256dh, "auth": auth})

    async def remove(self, context: AccessContext, endpoint: str) -> bool:
        async with tenant_session(
            self.session_factory, TenantScope.from_access_context(context)
        ) as session:
            gone = (
                await session.execute(
                    sa.delete(_p)
                    .where(
                        *_theirs(context.tenant_id, context.workspace_id, context.principal_id),
                        _p.c.endpoint == endpoint,
                    )
                    .returning(_p.c.id)
                )
            ).first()
        return gone is not None

    async def of_member(
        self, tenant_id: uuid.UUID, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> Sequence[PushSubscription]:
        async with tenant_session(
            self.session_factory, TenantScope(tenant_id, workspace_id, user_id)
        ) as session:
            rows = (
                await session.execute(
                    sa.select(_p.c.id, _p.c.endpoint, _p.c.p256dh, _p.c.auth)
                    .where(*_theirs(tenant_id, workspace_id, user_id))
                    .order_by(_p.c.created_at, _p.c.id)
                )
            ).all()
        return [PushSubscription(r.id, r.endpoint, r.p256dh, r.auth) for r in rows]

    async def drop(
        self,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        subscription_id: uuid.UUID,
    ) -> None:
        async with tenant_session(
            self.session_factory, TenantScope(tenant_id, workspace_id, user_id)
        ) as session:
            await session.execute(
                sa.delete(_p).where(
                    *_theirs(tenant_id, workspace_id, user_id), _p.c.id == subscription_id
                )
            )


@dataclass(frozen=True)
class SqlPushSubscriptionRetention:
    """Implements `dw_worker.consumers.retention.RetentionPrunePort`: a
    subscription the portal has not renewed for 90 days goes
    (`platform.prune_push_subscriptions()`), a technical bound like the
    inbox's, not a legal term."""

    session_factory: async_sessionmaker[AsyncSession]

    async def prune(self) -> None:
        async with self.session_factory() as session, session.begin():
            await session.execute(sa.text("SELECT platform.prune_push_subscriptions()"))

"""SQL implementation of the in-app inbox, its senders' door, and its pruning.

Every read and update runs under `tenant_session`, which binds the caller's
tenant AND principal; the table's RLS narrows both to rows addressed to that
principal (migration 855ae928c3fa), and every query also names the recipient
explicitly, a belt beside that brace.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence import tables
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.application.access_context import AccessContext
from dw_platform.application.notifications import Inbox, Notification, SourcedNotification

_n = tables.notifications
# The one door into `platform.notifications`; the Zalo link store calls it inside
# its own transaction, so a link and the message about it commit together.
DELIVER_NOTIFICATION = sa.text(
    "SELECT platform.deliver_notification("
    "CAST(:workspace_id AS uuid), CAST(:recipients AS uuid[]), :source_key, :title, :body, :link)"
)
# The same, queueing no web push (19a366484422): for a sender that pushes on
# its own, batched, so nobody's phone rings twice for one item.
DELIVER_WITHOUT_PUSH = sa.text(
    "SELECT platform.deliver_notification("
    "CAST(:workspace_id AS uuid), CAST(:recipients AS uuid[]), :source_key, :title, :body, :link,"
    " false)"
)


@dataclass(frozen=True)
class SqlNotificationRepository:
    session_factory: async_sessionmaker[AsyncSession]
    # Whether a delivery also queues a web push for each recipient who turned
    # push on (Sales ticket 78). False only where the composition root wires a
    # sender that pushes itself (Sales' follow-ups, ticket 48).
    push: bool = True

    async def latest(self, context: AccessContext, *, limit: int) -> Inbox:
        mine = sa.and_(
            _n.c.tenant_id == context.tenant_id, _n.c.recipient_user_id == context.principal_id
        )
        async with tenant_session(
            self.session_factory, TenantScope.from_access_context(context)
        ) as session:
            rows = (
                await session.execute(
                    sa.select(
                        _n.c.id, _n.c.title, _n.c.body, _n.c.link, _n.c.created_at, _n.c.read_at
                    )
                    .where(mine)
                    .order_by(_n.c.created_at.desc(), _n.c.id.desc())
                    .limit(limit)
                )
            ).all()
            unread = await session.scalar(
                sa.select(sa.func.count()).select_from(_n).where(mine, _n.c.read_at.is_(None))
            )
        return Inbox(
            items=tuple(
                Notification(
                    id=row.id,
                    title=row.title,
                    body=row.body,
                    link=row.link,
                    created_at=row.created_at,
                    read_at=row.read_at,
                )
                for row in rows
            ),
            unread=int(unread or 0),
        )

    async def sourced(
        self, context: AccessContext, *, prefix: str, since: datetime, limit: int
    ) -> list[SourcedNotification]:
        """The caller's own notifications whose key starts with ``prefix``,
        delivered since ``since``, newest first: what one sender told them
        lately (`dw_sales.application.today.FollowupNoticesPort`)."""
        # The prefix is matched as written: LIKE's own characters escaped.
        literal = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"{literal}%"
        async with tenant_session(
            self.session_factory, TenantScope.from_access_context(context)
        ) as session:
            rows = (
                await session.execute(
                    sa.select(
                        _n.c.id, _n.c.source_key, _n.c.title, _n.c.body, _n.c.link, _n.c.created_at
                    )
                    .where(
                        _n.c.tenant_id == context.tenant_id,
                        _n.c.recipient_user_id == context.principal_id,
                        _n.c.created_at >= since,
                        _n.c.source_key.like(pattern, escape="\\"),
                    )
                    .order_by(_n.c.created_at.desc(), _n.c.id.desc())
                    .limit(limit)
                )
            ).all()
        return [
            SourcedNotification(
                id=row.id,
                source_key=row.source_key,
                title=row.title,
                body=row.body,
                link=row.link,
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def mark_read(self, context: AccessContext, notification_id: uuid.UUID) -> bool:
        async with tenant_session(
            self.session_factory, TenantScope.from_access_context(context)
        ) as session:
            row = (
                await session.execute(
                    sa.update(_n)
                    .where(
                        _n.c.id == notification_id,
                        _n.c.tenant_id == context.tenant_id,
                        _n.c.recipient_user_id == context.principal_id,
                    )
                    .values(read_at=sa.func.coalesce(_n.c.read_at, sa.func.now()))
                    .returning(_n.c.id)
                )
            ).first()
        return row is not None

    async def mark_all_read(self, context: AccessContext) -> None:
        async with tenant_session(
            self.session_factory, TenantScope.from_access_context(context)
        ) as session:
            await session.execute(
                sa.update(_n)
                .where(
                    _n.c.tenant_id == context.tenant_id,
                    _n.c.recipient_user_id == context.principal_id,
                    _n.c.read_at.is_(None),
                )
                .values(read_at=sa.func.now())
            )

    async def deliver(
        self,
        context: AccessContext,
        *,
        recipients: Sequence[uuid.UUID],
        source_key: str,
        title: str,
        body: str,
        link: str | None,
    ) -> None:
        """Address one message to each member among `recipients` in the
        caller's workspace, once per `source_key`: delivering again is a
        no-op, so a sender may retry until it has recorded the delivery.
        Through `platform.deliver_notification`, the table's one door in."""
        if not recipients:
            return
        async with tenant_session(
            self.session_factory, TenantScope.from_access_context(context)
        ) as session:
            await session.execute(
                DELIVER_NOTIFICATION if self.push else DELIVER_WITHOUT_PUSH,
                {
                    "workspace_id": context.workspace_id,
                    "recipients": list(dict.fromkeys(recipients)),
                    "source_key": source_key,
                    "title": title,
                    "body": body,
                    "link": link,
                },
            )


@dataclass(frozen=True)
class SqlNotificationRetention:
    """Implements `dw_worker.consumers.retention.RetentionPrunePort`.

    The window is the database's (`platform.prune_notifications()`, 90
    days): a technical bound on an inbox nobody scrolls back through, not a
    legal term, so it is not in `retention@*.yaml`."""

    session_factory: async_sessionmaker[AsyncSession]

    async def prune(self) -> None:
        async with self.session_factory() as session, session.begin():
            await session.execute(sa.text("SELECT platform.prune_notifications()"))

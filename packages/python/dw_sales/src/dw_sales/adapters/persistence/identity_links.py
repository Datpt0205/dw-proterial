"""Person ↔ employee code links and the admin's queue in PostgreSQL
(ticket 64, migration adad4d524377). Each call one transaction bound to its
tenant; the partial unique indexes hold one live link per person and per
code whatever writes the row, and a violation is a `ConflictError`."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.errors import ConflictError
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.domain.audit import AuditEvent
from dw_sales.adapters.persistence.uow import AuditFactory
from dw_sales.application.identity_links import Link, QueueReason


@dataclass(frozen=True)
class SqlIdentityLinks:
    session_factory: async_sessionmaker[AsyncSession]
    audit: AuditFactory

    async def links(self, tenant_id: uuid.UUID) -> Sequence[Link]:
        async with tenant_session(
            self.session_factory, TenantScope(tenant_id=tenant_id)
        ) as session:
            rows = (
                await session.execute(
                    sa.text(
                        "SELECT subject, employee_code, linked_how FROM bravo.person_links"
                        " WHERE retired_at IS NULL"
                    )
                )
            ).all()
        return [Link(r.subject, r.employee_code, r.linked_how) for r in rows]

    async def employee_code(self, tenant_id: uuid.UUID, subject: uuid.UUID) -> str | None:
        """`EmployeeCodesPort` (ticket 53): the person's live link, or None."""
        async with tenant_session(
            self.session_factory, TenantScope(tenant_id=tenant_id)
        ) as session:
            code = await session.scalar(
                sa.text(
                    "SELECT employee_code FROM bravo.person_links"
                    " WHERE subject = :s AND retired_at IS NULL"
                ),
                {"s": subject},
            )
        return None if code is None else str(code)

    async def save(
        self,
        tenant_id: uuid.UUID,
        link: Link,
        *,
        linked_by: uuid.UUID | None,
        retire: uuid.UUID | None,
        at: datetime,
        audit: AuditEvent,
    ) -> None:
        try:
            async with tenant_session(
                self.session_factory, TenantScope(tenant_id=tenant_id)
            ) as session:
                if retire is not None:
                    await session.execute(
                        sa.text(
                            "UPDATE bravo.person_links SET retired_at = :at,"
                            " retired_reason = 'account disabled; the code moved to a new account'"
                            " WHERE subject = :s AND retired_at IS NULL"
                        ),
                        {"at": at, "s": retire},
                    )
                await session.execute(
                    sa.text(
                        "INSERT INTO bravo.person_links (tenant_id, id, subject, employee_code,"
                        " linked_how, linked_by, linked_at)"
                        " VALUES (:t, :id, :s, :c, :how, :by, :at)"
                    ),
                    {
                        "t": tenant_id,
                        "id": uuid.uuid4(),
                        "s": link.subject,
                        "c": link.employee_code,
                        "how": link.how,
                        "by": linked_by,
                        "at": at,
                    },
                )
                await session.execute(
                    sa.text(
                        "UPDATE bravo.link_queue SET resolved_at = :at, resolved_by = :by"
                        " WHERE subject = :s AND resolved_at IS NULL"
                    ),
                    {"at": at, "by": linked_by or link.subject, "s": link.subject},
                )
                await self.audit(session).append(audit)
        except IntegrityError as clash:
            if "uq_person_links_live" in str(clash.orig):
                raise ConflictError(
                    "người này, hoặc mã nhân viên này, đã có liên kết đang dùng",
                    details={"rule": "one_live_link"},
                ) from None
            raise

    async def queue(
        self,
        tenant_id: uuid.UUID,
        subject: uuid.UUID,
        reason: QueueReason,
        code: str | None,
        at: datetime,
    ) -> None:
        async with tenant_session(
            self.session_factory, TenantScope(tenant_id=tenant_id)
        ) as session:
            await session.execute(
                sa.text(
                    "INSERT INTO bravo.link_queue (tenant_id, id, subject, employee_code, reason,"
                    " opened_at) VALUES (:t, :id, :s, :c, :r, :at)"
                    " ON CONFLICT (tenant_id, subject) WHERE resolved_at IS NULL DO NOTHING"
                ),
                {
                    "t": tenant_id,
                    "id": uuid.uuid4(),
                    "s": subject,
                    "c": code,
                    "r": reason,
                    "at": at,
                },
            )

    async def open_items(self, tenant_id: uuid.UUID) -> Sequence[tuple[uuid.UUID, str, str | None]]:
        async with tenant_session(
            self.session_factory, TenantScope(tenant_id=tenant_id)
        ) as session:
            rows = (
                await session.execute(
                    sa.text(
                        "SELECT subject, reason, employee_code FROM bravo.link_queue"
                        " WHERE resolved_at IS NULL ORDER BY opened_at"
                    )
                )
            ).all()
        return [(r.subject, r.reason, r.employee_code) for r in rows]

"""The stop control: any PIC pauses DW1 in a workspace, only the head resumes it.

Pausing needs `sales.worker.pause`, resuming `sales.worker.resume` and a
reason; each is audited, the resume with its reason. A pause notifies every
holder of `sales.worker.resume` in the workspace, saying who paused and when,
and nothing else: no case, no amount (spec decision 8). While paused, "DW xử
lý" is refused (`InboxService`).

The notification goes after the commit, through the platform's inbox, which
delivers once per source key: a pause that committed is a pause, whether or
not the message reached anyone yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from dw_kernel.errors import ConflictError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import SalesUnitOfWorkFactory, WorkerState
from dw_sales.application.ports import (
    MemberDirectoryPort,
    NotificationSenderPort,
    ScopeHoldersPort,
)
from dw_sales.application.views import WorkerStateView, worker_state

_LOCAL = ZoneInfo("Asia/Ho_Chi_Minh")


@dataclass(frozen=True)
class WorkerService:
    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator
    holders: ScopeHoldersPort
    notifications: NotificationSenderPort
    directory: MemberDirectoryPort

    async def state(self, context: AccessContext) -> WorkerStateView:
        await self.gate.require(context, SalesScopes.OVERVIEW_READ, resource_type="sales_worker")
        async with self.uow(sales_scope(context)) as work:
            return worker_state(await work.worker.state())

    async def pause(self, context: AccessContext, reason: str | None) -> WorkerStateView:
        await self.gate.require(context, SalesScopes.WORKER_PAUSE, resource_type="sales_worker")
        now = self.clock.now()
        paused = WorkerState(
            paused=True, changed_by=context.principal_id, changed_at=now, reason=reason
        )
        async with self.uow(sales_scope(context)) as work:
            if (await work.worker.state()).paused:
                raise ConflictError("DW1 đã tạm dừng", details={"rule": "worker_paused"})
            await work.worker.set(paused)
            await work.audit.append(self._audit(context, "sales.worker.paused", now, {}))
            await work.commit()
        await self._notify_resumers(context, paused)
        return worker_state(paused)

    async def resume(self, context: AccessContext, reason: str) -> WorkerStateView:
        await self.gate.require(context, SalesScopes.WORKER_RESUME, resource_type="sales_worker")
        now = self.clock.now()
        running = WorkerState(
            paused=False, changed_by=context.principal_id, changed_at=now, reason=reason
        )
        async with self.uow(sales_scope(context)) as work:
            if not (await work.worker.state()).paused:
                raise ConflictError("DW1 không tạm dừng", details={"rule": "worker_running"})
            await work.worker.set(running)
            # The resume is audited with the head's reason, as the ticket asks.
            await work.audit.append(
                self._audit(context, "sales.worker.resumed", now, {"reason": reason})
            )
            await work.commit()
        return worker_state(running)

    def _audit(
        self, context: AccessContext, action: str, at: datetime, details: dict[str, object]
    ) -> AuditEvent:
        return AuditEvent(
            id=self.ids.new_uuid(),
            tenant_id=TenantId(context.tenant_id),
            workspace_id=WorkspaceId(context.workspace_id),
            actor_id=UserId(context.principal_id),
            action=action,
            resource_type="sales_worker",
            resource_id=str(context.workspace_id),
            occurred_at=at,
            details=details,
        )

    async def _notify_resumers(self, context: AccessContext, paused: WorkerState) -> None:
        recipients = await self.holders.holding(
            context.tenant_id, context.workspace_id, frozenset({SalesScopes.WORKER_RESUME.value})
        )
        names = {m.user_id: m.display_name for m in await self.directory.list_members(context)}
        assert paused.changed_at is not None
        when = paused.changed_at.astimezone(_LOCAL).strftime("%H:%M %d/%m/%Y")
        who = names.get(context.principal_id, "Một PIC")
        await self.notifications.deliver(
            context,
            recipients=recipients,
            source_key=f"sales.worker.paused:{context.workspace_id}:{paused.changed_at.isoformat()}",
            title="DW1 đã tạm dừng",
            body=f"{who} đã tạm dừng DW1 lúc {when} (giờ Việt Nam). Chỉ Trưởng bộ phận mở lại.",
            link="/sales",
        )

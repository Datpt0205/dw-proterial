"""The Bravo change watch, as people see and act on it (ticket 65).

The `bravo_watch` lane pauses the write kinds a change in Bravo concerns
(`dw_bravo.watch`); nothing resumes them by itself. This service is the one
way back: a holder of `sales.bravo.watch.accept` accepts the latest
production fingerprint as the new baseline, with a reason (that the replay
passed on UAT), and every pause is lifted in the same transaction as the
baseline and its audit row. The right is checked here, where the baseline
is written, not where a button is drawn.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

from pydantic import BaseModel

from dw_kernel.errors import DomainError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent
from dw_sales.application.access import SalesAuthorizationPort, SalesScopes

REASON_LIMIT: Final = 500
ACCEPTED_ACTION: Final = "sales.bravo.watch.baseline_accepted"


@dataclass(frozen=True)
class WatchPause:
    kind: str
    reasons: tuple[str, ...]
    paused_at: datetime


@dataclass(frozen=True)
class WatchState:
    pauses: tuple[WatchPause, ...]
    latest_fingerprint: uuid.UUID | None
    latest_taken_at: datetime | None
    baseline_fingerprint: uuid.UUID | None
    baseline_accepted_at: datetime | None
    last_read: datetime | None


class BravoWatchStorePort(Protocol):
    async def state(self, tenant_id: uuid.UUID) -> WatchState: ...

    async def accept(
        self,
        tenant_id: uuid.UUID,
        *,
        baseline_id: uuid.UUID,
        fingerprint_id: uuid.UUID,
        accepted_by: uuid.UUID,
        reason: str,
        at: datetime,
        audit: AuditEvent,
    ) -> None:
        """Baseline, pauses lifted and audit row, in one transaction.
        `ConflictError` when the fingerprint is not the latest production one."""
        ...


@dataclass(frozen=True)
class BravoWatchService:
    store: BravoWatchStorePort
    authz: SalesAuthorizationPort
    clock: UtcClock
    ids: IdGenerator

    async def state(self, context: AccessContext) -> WatchState:
        await self.authz.require(
            context=context,
            action=SalesScopes.BRAVO_WATCH_READ,
            resource_type="workspace",
            resource_id=str(context.workspace_id),
        )
        return await self.store.state(context.tenant_id)

    async def accept(
        self, context: AccessContext, fingerprint_id: uuid.UUID, reason: str
    ) -> Sequence[str]:
        """The new baseline; returns the kinds whose pauses it lifted."""
        await self.authz.require(
            context=context,
            action=SalesScopes.BRAVO_WATCH_ACCEPT,
            resource_type="workspace",
            resource_id=str(context.workspace_id),
        )
        reason = reason.strip()
        if not 1 <= len(reason) <= REASON_LIMIT:
            raise DomainError(
                "ghi lý do chấp nhận (lần chạy lại trên UAT đã khớp), tối đa 500 ký tự"
            )
        before = await self.store.state(context.tenant_id)
        now = self.clock.now()
        baseline_id = self.ids.new_uuid()
        await self.store.accept(
            context.tenant_id,
            baseline_id=baseline_id,
            fingerprint_id=fingerprint_id,
            accepted_by=context.principal_id,
            reason=reason,
            at=now,
            audit=AuditEvent(
                id=self.ids.new_uuid(),
                tenant_id=TenantId(context.tenant_id),
                workspace_id=WorkspaceId(context.workspace_id),
                actor_id=UserId(context.principal_id),
                action=ACCEPTED_ACTION,
                resource_type="bravo_watch_baseline",
                resource_id=str(baseline_id),
                occurred_at=now,
                details={
                    "fingerprint_id": str(fingerprint_id),
                    "lifted": sorted(p.kind for p in before.pauses),
                },
            ),
        )
        return sorted(p.kind for p in before.pauses)


class WatchPauseView(BaseModel):
    kind: str
    reasons: list[str]
    paused_at: datetime


class WatchStateView(BaseModel):
    """The watch as its readers see it: what is paused and why, the latest
    fingerprint (the one a baseline accepts) and when Bravo was last read."""

    pauses: list[WatchPauseView]
    latest_fingerprint: uuid.UUID | None
    latest_taken_at: datetime | None
    baseline_fingerprint: uuid.UUID | None
    baseline_accepted_at: datetime | None
    last_read: datetime | None

    @classmethod
    def of(cls, state: WatchState) -> WatchStateView:
        return cls(
            pauses=[
                WatchPauseView(kind=p.kind, reasons=list(p.reasons), paused_at=p.paused_at)
                for p in state.pauses
            ],
            latest_fingerprint=state.latest_fingerprint,
            latest_taken_at=state.latest_taken_at,
            baseline_fingerprint=state.baseline_fingerprint,
            baseline_accepted_at=state.baseline_accepted_at,
            last_read=state.last_read,
        )


class BaselineAcceptedView(BaseModel):
    lifted: list[str]

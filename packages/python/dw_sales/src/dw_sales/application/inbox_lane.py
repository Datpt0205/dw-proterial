"""DW1 processes new mail on its own: the worker's `sales_inbox` lane (ticket 16).

"DW xử lý" waits for a person. In production each new message must start
processing without a click, and the mock mailbox exercises the same path, so
a lane in the worker does on a timer what the button does.

**Whose authority.** DW1's own service account in the tenant, "DW1 (tài khoản
dịch vụ)" (decided 2026-10-12, shape (a)): a platform user, `dw1_subject`,
with a membership holding `sales.inbox.process` through the role `sales_dw1`,
resolved by the platform like any member (`ServiceAccessPort`). The lane never
builds a context of its own, and cuts the one it is given to the one scope it
needs (`LANE_CEILING`): the account cannot prepare, cross-check, price or
approve, and a role given to it by hand does not change what the lane does.

**One tick, per workspace whose mailbox the host reads:**

1. DW1's context there, or nothing at all: no account, a locked tenant, or a
   context for any other workspace than the one asked for.
2. Nothing while DW1 is paused there ("enabled" is the pause state only,
   decided 2026-10-12): pausing stops the lane on its next tick, before a run
   is spent.
3. Each message with no disposition when the tick began, oldest first, in a
   DW1 run of its own, `Dw1Runs.process`: the door "DW xử lý" uses, so the
   scope, the plan's daily runs (`RunAllowancePort`, where the run begins),
   the pause and the message's idempotency key are checked in the same places
   whoever pressed. A message a person processed is skipped, read again just
   before its run (a person may have routed it, or paused DW1, since the tick
   began); one a person processes while the lane's run works on it is refused
   to whichever is second (`MessageLogPort.record`).
4. Over the plan's runs for the day, the tick stops: the rest stay "Chưa xử
   lý" in the inbox, where people see them, and the next tick tries again.

**It audits as itself.** For each message it had processed, one
`lane_audit_event` from `system_actor("sales_inbox")`, naming the account it
acted under. The case events and the processing's own audit rows name that
account, never a person.

A message whose run fails for any other reason is not retried on every tick,
which would spend a run a minute on one bad file and leave a tenant's people
none: it waits a doubling delay (`RETRY_FIRST`, at most `RETRY_LONGEST`),
kept in memory and forgotten once the message has a disposition. A person can
still press "DW xử lý" on it.

The lane owns no job queue (it reads the mailbox and writes the message log),
so the worker has nothing of it to reap.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final, Literal, Protocol

from dw_kernel.errors import (
    ConflictError,
    EntitlementDeniedError,
    PermissionDeniedError,
    QuotaExceededError,
)
from dw_kernel.ids import TenantId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.identity import MembershipAccess, context_from
from dw_platform.domain.audit import lane_audit_event
from dw_sales.application.access import SalesScopes, sales_scope
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.ports import InboxPort, SalesScope
from dw_sales.application.support import DW1_WORKER_ID
from dw_sales.application.views import MessageDispositionView

logger = logging.getLogger("dw_sales.inbox_lane")

# The lane's worker registry name, and so its audit actor (ADR 0011): the
# worker registers it under this constant, never a copy of the string.
SALES_INBOX_LANE: Final = "sales_inbox"
# What the lane does with DW1's account, and so all its context carries.
LANE_CEILING: Final = frozenset({SalesScopes.INBOX_PROCESS.value})
# A failed message waits this long before the lane tries it again, doubling.
RETRY_FIRST: Final = timedelta(minutes=5)
RETRY_LONGEST: Final = timedelta(hours=6)

Stopped = Literal["no_account", "wrong_scope", "paused", "not_permitted", "quota"]


def dw1_subject(tenant_id: uuid.UUID) -> str:
    """DW1's service account in one tenant: the subject its platform user has.

    One account per tenant, so the tenant is part of it (a subject is unique
    across the platform). It is no sign-in name: no identity provider issues
    it, and the demo roster does not list it.
    """
    return f"service|{DW1_WORKER_ID}|{tenant_id}"


class ServiceAccessPort(Protocol):
    """A service account's access in one workspace, cut to a ceiling, as the
    platform resolves any member's (`SqlMembershipLookup.find_service_access`)."""

    async def find_service_access(
        self,
        subject: str,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        ceiling: frozenset[str],
    ) -> MembershipAccess | None: ...


class ProcessRunPort(Protocol):
    """Processing one message in a DW1 run of its own: `Dw1Runs.process`,
    the door "DW xử lý" uses."""

    async def process(self, context: AccessContext, message_id: str) -> MessageDispositionView: ...


@dataclass(frozen=True, slots=True)
class LaneTick:
    """What one tick did in one workspace."""

    # Processed by this tick, oldest first.
    processed: tuple[str, ...] = ()
    # Why the tick stopped before the mailbox was done, if it did.
    stopped: Stopped | None = None


@dataclass(slots=True)
class _Retry:
    attempts: int
    not_before: datetime


@dataclass
class InboxLane:
    uow: SalesUnitOfWorkFactory
    inbox: InboxPort
    runs: ProcessRunPort
    access: ServiceAccessPort
    clock: UtcClock
    ids: IdGenerator
    # Failed messages waiting out their delay, per workspace. Bounded by the
    # mailbox: a message leaves when it has a disposition or the mailbox drops it.
    _retry: dict[tuple[SalesScope, str], _Retry] = field(default_factory=dict, repr=False)

    async def tick(self, scope: SalesScope) -> LaneTick:
        context = await self._context(scope)
        if context is None:
            return LaneTick(stopped="no_account")
        if sales_scope(context) != scope:
            # Never one workspace's mail under another's context, whatever
            # answered for the account.
            logger.error("sales_inbox: a context for another workspace was refused")
            return LaneTick(stopped="wrong_scope")
        async with self.uow(scope) as work:
            if (await work.worker.state()).paused:
                return LaneTick(stopped="paused")
            done = {logged.disposition.message_id for logged in await work.messages.list_all()}
        waiting = [
            message.message_id
            for message in await self.inbox.list_messages(scope)
            if message.message_id not in done
        ]
        self._forget_all_but(scope, waiting)
        processed: list[str] = []
        for message_id in waiting:
            if self._waits(scope, message_id):
                continue
            # Read again just before its run: since the tick began a person may
            # have processed it, or paused DW1. The log's key refuses a second
            # disposition on a case, but a routed message may be processed
            # again, so only this keeps the lane off one a person routed
            # meanwhile; and a run the pause refuses is still a run spent.
            async with self.uow(scope) as work:
                if (await work.worker.state()).paused:
                    return LaneTick(tuple(processed), stopped="paused")
                if await work.messages.get(message_id) is not None:
                    continue
            try:
                view = await self.runs.process(context, message_id)
            except QuotaExceededError:
                logger.warning("sales_inbox: the plan's runs for today are spent; mail waits")
                return LaneTick(tuple(processed), stopped="quota")
            except (PermissionDeniedError, EntitlementDeniedError):
                logger.warning("sales_inbox: DW1's account may not process the mailbox")
                return LaneTick(tuple(processed), stopped="not_permitted")
            except ConflictError as refused:
                if refused.details.get("rule") == "worker_paused":
                    return LaneTick(tuple(processed), stopped="paused")
                # Processed meanwhile (next tick it has a disposition), or a
                # case that refuses it: either way, not again every tick.
                self._failed(scope, message_id)
                continue
            except Exception:
                logger.exception("sales_inbox: processing %s failed; it waits", message_id)
                self._failed(scope, message_id)
                continue
            await self._audit(context, message_id, view)
            processed.append(message_id)
        return LaneTick(tuple(processed))

    # ------------------------------------------------------------- helpers --

    async def _context(self, scope: SalesScope) -> AccessContext | None:
        tenant_id, workspace_id = scope.tenant_id.value, scope.workspace_id.value
        access = await self.access.find_service_access(
            dw1_subject(tenant_id), tenant_id, workspace_id, LANE_CEILING
        )
        return None if access is None else context_from(access)

    async def _audit(
        self, context: AccessContext, message_id: str, view: MessageDispositionView
    ) -> None:
        details: dict[str, object] = {
            "disposition": view.kind,
            # The account the lane acted under: the actor of the processing's
            # own audit rows and case events.
            "account_id": str(context.principal_id),
        }
        if view.case_kind is not None and view.case_id is not None:
            details |= {"case_kind": view.case_kind.value, "case_id": str(view.case_id)}
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            await work.audit.append(
                lane_audit_event(
                    lane=SALES_INBOX_LANE,
                    event_id=self.ids.new_uuid(),
                    tenant_id=TenantId(scope.tenant_id.value),
                    workspace_id=WorkspaceId(scope.workspace_id.value),
                    action="sales.message.processed_by_lane",
                    resource_type="sales_message",
                    resource_id=message_id,
                    occurred_at=self.clock.now(),
                    details=details,
                )
            )
            await work.commit()

    def _waits(self, scope: SalesScope, message_id: str) -> bool:
        retry = self._retry.get((scope, message_id))
        return retry is not None and self.clock.now() < retry.not_before

    def _failed(self, scope: SalesScope, message_id: str) -> None:
        earlier = self._retry.get((scope, message_id))
        attempts = 1 if earlier is None else earlier.attempts + 1
        # The exponent is capped too: a file that fails for months must not
        # overflow the delay it is already held to.
        delay = min(RETRY_FIRST * 2 ** min(attempts - 1, 16), RETRY_LONGEST)
        self._retry[scope, message_id] = _Retry(attempts, self.clock.now() + delay)

    def _forget_all_but(self, scope: SalesScope, waiting: list[str]) -> None:
        still = set(waiting)
        for key in [k for k in self._retry if k[0] == scope and k[1] not in still]:
            del self._retry[key]

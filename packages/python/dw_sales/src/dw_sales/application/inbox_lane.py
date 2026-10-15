"""DW1 processes new mail on its own: the worker's `sales_inbox` lane (ticket 16).

"DW xử lý" waits for a person. In production each new message must start
processing without a click, and the mock mailbox exercises the same path, so
a lane in the worker does on a timer what the button does: since ticket 25,
**it queues the message** (`ProcessingService.enqueue`, the button's own door)
and the worker's `sales_processing` lane runs it, as it runs a person's.

**Whose authority.** DW1's own service account in the tenant, "DW1 (tài khoản
dịch vụ)" (decided 2026-10-12, shape (a)): a platform user, `dw1_subject`,
with a membership holding `sales.inbox.process` through the role `sales_dw1`,
resolved by the platform like any member (`ServiceAccessPort`). The lane never
builds a context of its own, and cuts the one it is given to the one scope it
needs (`LANE_CEILING`): the account cannot prepare, cross-check, price or
approve, and a role given to it by hand does not change what the lane does.
The job names the account as who asked, and the drain resolves the account
again when it runs it.

**One tick, per workspace whose mailbox the host reads:**

1. DW1's context there, or nothing at all: no account, a locked tenant, or a
   context for any other workspace than the one asked for.
2. Nothing while DW1 is paused there ("enabled" is the pause state only,
   decided 2026-10-12): pausing stops the lane on its next tick.
3. Each message with no disposition, oldest first, is queued, unless its job
   is already queued or running, or failed less than its delay ago: a message
   whose processing fails is not queued again on every tick, which would
   spend a run a minute on one bad file. The delay doubles with the job's
   failures in a row (`RETRY_FIRST`, at most `RETRY_LONGEST`), and it is the
   job's row that remembers them, not this process. A person can still press
   "DW xử lý" on it.
4. The plan's runs for the day are counted where each run begins, by the
   drain: a job over them fails (``quota``) and waits out its delay here.

**It audits as itself.** For each message it queued, one `lane_audit_event`
from `system_actor("sales_inbox")`, naming the account it acted under; the
queueing's own audit row names the account, never a person.

The lane owns no job queue of its own: the jobs are the processing queue's,
which the worker's reaper settles (`sales_processing`).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Literal, Protocol

from dw_kernel.errors import (
    ConflictError,
    EntitlementDeniedError,
    NotFoundError,
    PermissionDeniedError,
)
from dw_kernel.ids import TenantId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.identity import MembershipAccess, context_from
from dw_platform.domain.audit import lane_audit_event
from dw_sales.application.access import sales_scope
from dw_sales.application.case_store import ProcessingJob, SalesUnitOfWorkFactory
from dw_sales.application.ports import InboxPort, SalesScope
from dw_sales.application.processing import PROCESSING_CEILING
from dw_sales.application.support import DW1_WORKER_ID
from dw_sales.application.views import ProcessingJobView

logger = logging.getLogger("dw_sales.inbox_lane")

# The lane's worker registry name, and so its audit actor
# (ADR 0011-a-background-lane-audits-as-itself): the worker registers it under this constant, never
# a copy of the string.
SALES_INBOX_LANE: Final = "sales_inbox"
# What the lane does with DW1's account, and so all its context carries: what
# processing needs, the drain's own ceiling.
LANE_CEILING: Final = PROCESSING_CEILING
# A message whose job failed waits this long before the lane queues it
# again, doubling with the job's failures in a row.
RETRY_FIRST: Final = timedelta(minutes=5)
RETRY_LONGEST: Final = timedelta(hours=6)

Stopped = Literal["no_account", "wrong_scope", "paused", "not_permitted"]


def dw1_subject(tenant_id: uuid.UUID) -> str:
    """DW1's service account in one tenant: the subject its platform user has.

    One account per tenant, so the tenant is part of it (a subject is unique
    across the platform). It is no sign-in name: no identity provider issues
    it, and the demo roster does not list it.
    """
    return f"service|{DW1_WORKER_ID}|{tenant_id}"


def retry_delay(failures: int) -> timedelta:
    """How long a job failed ``failures`` times in a row waits for the lane.
    The exponent is capped too: a file that fails for months must not
    overflow the delay it is already held to."""
    delay: timedelta = RETRY_FIRST * 2 ** min(max(failures, 1) - 1, 16)
    return min(delay, RETRY_LONGEST)


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


class EnqueuePort(Protocol):
    """Queueing one message, through the door "DW xử lý" uses:
    `ProcessingService.enqueue`."""

    async def enqueue(self, context: AccessContext, message_id: str) -> ProcessingJobView: ...


@dataclass(frozen=True, slots=True)
class LaneTick:
    """What one tick did in one workspace."""

    # Queued by this tick, oldest first.
    queued: tuple[str, ...] = ()
    # Why the tick stopped before the mailbox was done, if it did.
    stopped: Stopped | None = None


@dataclass(frozen=True)
class InboxLane:
    uow: SalesUnitOfWorkFactory
    inbox: InboxPort
    processing: EnqueuePort
    access: ServiceAccessPort
    clock: UtcClock
    ids: IdGenerator

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
            jobs = {job.message_id: job for job in await work.jobs.list_all()}
        now = self.clock.now()
        queued: list[str] = []
        for message in await self.inbox.list_messages(scope):
            message_id = message.message_id
            if message_id in done or not _due(jobs.get(message_id), now):
                continue
            try:
                job = await self.processing.enqueue(context, message_id)
            except (PermissionDeniedError, EntitlementDeniedError):
                logger.warning("sales_inbox: DW1's account may not process the mailbox")
                return LaneTick(tuple(queued), stopped="not_permitted")
            except ConflictError as refused:
                if refused.details.get("rule") == "worker_paused":
                    return LaneTick(tuple(queued), stopped="paused")
                # On a case since the tick began: not queued, and next tick
                # it has its disposition.
                continue
            except NotFoundError:
                continue
            await self._audit(context, message_id, job)
            queued.append(message_id)
        return LaneTick(tuple(queued))

    # ------------------------------------------------------------- helpers --

    async def _context(self, scope: SalesScope) -> AccessContext | None:
        tenant_id, workspace_id = scope.tenant_id.value, scope.workspace_id.value
        access = await self.access.find_service_access(
            dw1_subject(tenant_id), tenant_id, workspace_id, LANE_CEILING
        )
        return None if access is None else context_from(access)

    async def _audit(self, context: AccessContext, message_id: str, job: ProcessingJobView) -> None:
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            await work.audit.append(
                lane_audit_event(
                    lane=SALES_INBOX_LANE,
                    event_id=self.ids.new_uuid(),
                    tenant_id=TenantId(scope.tenant_id.value),
                    workspace_id=WorkspaceId(scope.workspace_id.value),
                    action="sales.message.queued_by_lane",
                    resource_type="sales_message",
                    resource_id=message_id,
                    occurred_at=self.clock.now(),
                    details={
                        "job_id": str(job.job_id),
                        # The account the lane acted under: who asked, on the job.
                        "account_id": str(context.principal_id),
                    },
                )
            )
            await work.commit()


def _due(job: ProcessingJob | None, now: datetime) -> bool:
    """Whether the lane queues the message of ``job``: never asked, done
    without a disposition, or failed past its delay; never while active."""
    if job is None:
        return True
    if job.active:
        return False
    if job.status == "failed":
        return now >= job.updated_at + retry_delay(job.failures)
    return True

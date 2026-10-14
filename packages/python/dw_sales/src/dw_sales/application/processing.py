""" "DW xử lý" as a queue (ticket 25; asynchronous by Đạt's decision of 2026-10-14).

Processing a message reads its files, and since ticket 25 every file is read
in the reader sandbox, which the API does not wait on: the button, "DW xử lý
tất cả" and DW1's mailbox lane (ticket 16) all **enqueue**, and the worker's
`sales_processing` lane **drains**. Both ends are here.

**Enqueue** (`ProcessingService`, the routes' 202): the caller's
`sales.inbox.process`, DW1 running in the workspace (409 naming who paused it
otherwise), the message in the mailbox (404) and not already on a case (409),
then one row per message (`ProcessingJobsPort.enqueue`, idempotent per
(workspace, message_id): a second press, or the lane and a person at once,
queue it once), and an audit row naming who asked. "All" enqueues every
message still without a disposition, oldest first: one job, and one DW1 run,
per message, as the mailbox lane always counted it.

**Drain** (`ProcessingDrain`, the worker's lane): it claims one due job at a
time (`ProcessingQueuePort.claim`: `FOR UPDATE SKIP LOCKED` in the job's own
scope), resolves **the asker's access as it stands now**, cut to
`PROCESSING_CEILING` (`RequesterAccessPort`, the platform's membership lookup
by user id): a person whose membership or scope went away since they pressed
processes nothing, and a role cannot widen what the lane does. It then runs
the same door the button used before (`Dw1Runs.process`, a DW1 run counted
against the plan by `RunAllowancePort` where it begins), so the pause, the
quota, the message's own idempotency key and every check of the processing
apply exactly as they did. The job settles as:

- ``done``: the message has its disposition (the inbox shows it);
- back to ``queued`` after an outage (`InfrastructureError`: the scanner or
  the reader did not answer), after `RETRY_AFTER` doubling, at most
  `MAX_ATTEMPTS` claims; then ``failed`` (``unavailable``);
- ``failed`` with its reason (`JobError`) otherwise. A failed job is pressed
  again by a person, or queued again by the lane after its own delay.

Each settlement that ends a run is audited by the lane as itself
(`lane_audit_event`, actor `system:sales_processing`), naming who asked; the
processing's own audit rows and case events name the asker, as the button's
always did. A job a dead worker left running is returned to the queue by the
worker's reaper (`reap_stale`, through the platform's `ReapTarget`).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Protocol

from dw_kernel.errors import (
    ConflictError,
    EntitlementDeniedError,
    InfrastructureError,
    NotFoundError,
    PermissionDeniedError,
    QuotaExceededError,
)
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.identity import MembershipAccess, context_from
from dw_platform.domain.audit import AuditEvent, lane_audit_event
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import (
    ProcessingJob,
    SalesUnitOfWork,
    SalesUnitOfWorkFactory,
    Settlement,
)
from dw_sales.application.inbox_service import ON_A_CASE, require_running
from dw_sales.application.ports import InboxPort, SalesScope
from dw_sales.application.views import MessageDispositionView, ProcessingJobView, processing_job
from dw_sales.domain.dispositions import DispositionKind

logger = logging.getLogger("dw_sales.processing")

# The drain's worker registry name, and so its audit actor (ADR 0011).
SALES_PROCESSING_LANE: Final = "sales_processing"
# What processing needs, and so all a context the drain builds carries.
PROCESSING_CEILING: Final = frozenset({SalesScopes.INBOX_PROCESS.value})
# How many times one round claims a job an outage interrupted.
MAX_ATTEMPTS: Final = 3
# The wait after an outage before the next claim, doubling.
RETRY_AFTER: Final = timedelta(seconds=30)


class RequesterAccessPort(Protocol):
    """A user's access in one workspace, by user id, cut to a ceiling, as the
    platform resolves any member's (`SqlMembershipLookup.find_linked_access`):
    None when the membership is gone, or the tenant is locked or planless."""

    async def find_linked_access(
        self,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        ceiling: frozenset[str],
    ) -> MembershipAccess | None: ...


class ProcessRunPort(Protocol):
    """Processing one message in a DW1 run of its own: `Dw1Runs.process`."""

    async def process(self, context: AccessContext, message_id: str) -> MessageDispositionView: ...


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    """A job the drain holds: running, in its scope, until it settles."""

    scope: SalesScope
    job: ProcessingJob


class ProcessingQueuePort(Protocol):
    """The queue across workspaces, as the worker drains it."""

    async def claim(self) -> ClaimedJob | None:
        """The oldest due job of a workspace with one, marked running, its
        attempts counted; None when nothing is due anywhere."""
        ...

    async def reap_stale(self, *, older_than: datetime) -> Sequence[uuid.UUID]:
        """Jobs running since before ``older_than`` (their worker died): back
        in the queue, or failed ``abandoned`` once their attempts are spent."""
        ...


@dataclass(frozen=True)
class ProcessingService:
    """The routes' "DW xử lý" and "DW xử lý tất cả" (module docstring)."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator
    inbox: InboxPort

    async def enqueue(self, context: AccessContext, message_id: str) -> ProcessingJobView:
        await self.gate.require(
            context,
            SalesScopes.INBOX_PROCESS,
            resource_type="sales_message",
            resource_id=message_id,
        )
        scope = sales_scope(context)
        if await self.inbox.get_message(scope, message_id) is None:
            raise NotFoundError("no such message", details={"message_id": message_id})
        async with self.uow(scope) as work:
            await require_running(work)
            existing = await work.messages.get(message_id)
            if existing is not None and existing.kind in ON_A_CASE:
                raise ConflictError(
                    "the message is already on a case",
                    details={"message_id": message_id, "disposition": existing.kind.value},
                )
            job = await self._enqueue(work, context, message_id)
            await work.commit()
        return processing_job(job)

    async def enqueue_waiting(self, context: AccessContext) -> list[ProcessingJobView]:
        """Every message still without a disposition, oldest first."""
        await self.gate.require(context, SalesScopes.INBOX_PROCESS, resource_type="sales_message")
        scope = sales_scope(context)
        messages = await self.inbox.list_messages(scope)
        async with self.uow(scope) as work:
            await require_running(work)
            done = {m.disposition.message_id for m in await work.messages.list_all()}
            jobs = [
                await self._enqueue(work, context, message.message_id)
                for message in messages
                if message.message_id not in done
            ]
            await work.commit()
        return [processing_job(job) for job in jobs]

    async def _enqueue(
        self, work: SalesUnitOfWork, context: AccessContext, message_id: str
    ) -> ProcessingJob:
        now = self.clock.now()
        job, queued = await work.jobs.enqueue(
            message_id, context.principal_id, now, self.ids.new_uuid()
        )
        if queued:
            await work.audit.append(
                AuditEvent(
                    id=self.ids.new_uuid(),
                    tenant_id=TenantId(context.tenant_id),
                    workspace_id=WorkspaceId(context.workspace_id),
                    actor_id=UserId(context.principal_id),
                    action="sales.message.queued",
                    resource_type="sales_message",
                    resource_id=message_id,
                    occurred_at=now,
                    details={"job_id": str(job.job_id)},
                )
            )
        return job


@dataclass(frozen=True)
class ProcessingDrain:
    """The worker's `sales_processing` lane (module docstring)."""

    queue: ProcessingQueuePort
    uow: SalesUnitOfWorkFactory
    runs: ProcessRunPort
    access: RequesterAccessPort
    clock: UtcClock
    ids: IdGenerator

    async def drain_one(self) -> bool:
        """One due job processed and settled; False when none was due."""
        claimed = await self.queue.claim()
        if claimed is None:
            return False
        outcome, view = await self._run(claimed)
        await self._settle(claimed, outcome, view)
        return True

    async def _run(self, claimed: ClaimedJob) -> tuple[Settlement, MessageDispositionView | None]:
        scope, job = claimed.scope, claimed.job
        access = await self.access.find_linked_access(
            job.requested_by, scope.tenant_id.value, scope.workspace_id.value, PROCESSING_CEILING
        )
        if access is None:
            return Settlement.failed("not_permitted"), None
        context = context_from(access)
        if sales_scope(context) != scope:
            # Never one workspace's mail under another's context.
            logger.error("sales_processing: a context for another workspace was refused")
            return Settlement.failed("not_permitted"), None
        try:
            view = await self.runs.process(context, job.message_id)
        except QuotaExceededError:
            return Settlement.failed("quota"), None
        except (PermissionDeniedError, EntitlementDeniedError):
            return Settlement.failed("not_permitted"), None
        except NotFoundError:
            return Settlement.failed("not_found"), None
        except ConflictError as refused:
            paused = refused.details.get("rule") == "worker_paused"
            return Settlement.failed("paused" if paused else "conflict"), None
        except InfrastructureError as outage:
            logger.warning(
                "sales_processing: %s on attempt %d",
                outage.details.get("reason_code"),
                job.attempts,
            )
            if job.attempts >= MAX_ATTEMPTS:
                return Settlement.failed("unavailable"), None
            wait = RETRY_AFTER * 2 ** (job.attempts - 1)
            return Settlement.retry(self.clock.now() + wait), None
        except Exception:
            logger.exception("sales_processing: processing a message failed")
            return Settlement.failed("error"), None
        if view.kind == DispositionKind.NOT_YET_PROCESSED.value:
            # A model gave no usable answer and the message may be read again.
            return Settlement.failed("model_retry"), view
        return Settlement.done(), view

    async def _settle(
        self, claimed: ClaimedJob, outcome: Settlement, view: MessageDispositionView | None
    ) -> None:
        scope, job = claimed.scope, claimed.job
        now = self.clock.now()
        async with self.uow(scope) as work:
            if not await work.jobs.settle(job, outcome, now):
                logger.warning("sales_processing: a job was taken back before it settled")
                return
            if outcome.status != "queued":
                await work.audit.append(self._audit(scope, job, outcome, view, now))
            await work.commit()

    def _audit(
        self,
        scope: SalesScope,
        job: ProcessingJob,
        outcome: Settlement,
        view: MessageDispositionView | None,
        at: datetime,
    ) -> AuditEvent:
        details: dict[str, object] = {
            "job_id": str(job.job_id),
            "outcome": outcome.status,
            # Who asked: a person, or DW1's service account (the mailbox lane).
            "requested_by": str(job.requested_by),
            "attempts": job.attempts,
        }
        if outcome.error is not None:
            details["error"] = outcome.error
        if view is not None:
            details["disposition"] = view.kind
            if view.case_kind is not None and view.case_id is not None:
                details |= {"case_kind": view.case_kind.value, "case_id": str(view.case_id)}
        return lane_audit_event(
            lane=SALES_PROCESSING_LANE,
            event_id=self.ids.new_uuid(),
            tenant_id=TenantId(scope.tenant_id.value),
            workspace_id=WorkspaceId(scope.workspace_id.value),
            action=f"sales.message.processing_{outcome.status}",
            resource_type="sales_message",
            resource_id=job.message_id,
            occurred_at=at,
            details=details,
        )

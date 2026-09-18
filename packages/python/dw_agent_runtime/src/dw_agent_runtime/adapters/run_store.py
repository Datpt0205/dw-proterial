"""Persistence for worker runs (platform.worker_runs) under RLS."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_agent_runtime.adapters.runtime_tables import model_usage_ledger, worker_runs
from dw_agent_runtime.contracts import RunContext, WorkerDefinition
from dw_kernel.autonomy import AutonomyLevel
from dw_kernel.errors import ConflictError, NotFoundError

# Migration 0015. Matched by name so an unrelated constraint violation stays a
# bug report rather than being reported to the user as "already in flight".
ACTIVE_THREAD_INDEX = "uq_worker_runs_active_thread"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = frozenset({RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED})

_SET_TENANT = text("SELECT set_config('app.tenant_id', :tenant_id, true)")

# One channel for every worker. A listener filters on the payload rather than
# on the channel name because channel names are cluster-global and cannot be
# scoped to a tenant - putting a tenant id in one would leak it to anybody able
# to LISTEN, and would still need the payload filter to be correct.
RUN_STATE_CHANNEL = "dw_run_state"

_NOTIFY = text(f"SELECT pg_notify('{RUN_STATE_CHANNEL}', :payload)")


def _announcement(run_context: RunContext, status: RunStatus) -> str:
    """What a watcher needs to decide whether this run concerns it.

    Deliberately not the run's input or result: a payload rides in the server's
    memory until every listener has read it, Postgres caps it at 8000 bytes,
    and a watcher that wants the outcome should read it through the same
    authorized path it would have used anyway.
    """
    return json.dumps(
        {
            "tenant": str(run_context.tenant_id),
            "worker": run_context.worker_id,
            "run": str(run_context.run_id),
            "subject": run_context.subject_ref,
            "status": status.value,
        },
        ensure_ascii=False,
    )


@dataclass(frozen=True)
class RunRecord:
    id: uuid.UUID
    thread_id: uuid.UUID
    status: RunStatus
    worker_id: str
    worker_version: str
    graph_version: str
    # None only for a run started before migration 0005, which recorded no
    # artifact versions beyond the graph's. Every run since carries all four.
    prompt_bundle_version: str | None
    toolset_version: str | None
    policy_version: str | None
    memory_policy_version: str | None
    # None for a run started before migration 0006; the policy asks about
    # everything for such a run rather than guess what it was allowed.
    autonomy_level: AutonomyLevel | None
    approval_policy_version: str | None
    input: dict[str, Any]
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    approval_request_id: uuid.UUID | None
    release_manifest_ref: str | None
    requested_by: uuid.UUID
    # What the requester was allowed to do when the run started. Resuming
    # replays this rather than asking whoever approved.
    actor_roles: frozenset[str]
    actor_scopes: frozenset[str]
    actor_plan_id: str
    actor_clearance: str
    actor_record_visibility: str
    # None means the roll-up was never recorded (a run started before
    # migration 0145), which replays as "no owner limit" exactly as it did
    # then. Every run started since carries the real set.
    actor_visible_owners: frozenset[uuid.UUID] | None


@dataclass(frozen=True)
class SqlWorkerRunStore:
    session_factory: async_sessionmaker[AsyncSession]
    # How long a `running` row may sit untouched before the next turn that
    # collides with it presumes the process behind it is gone. Injected, never
    # defaulted: a host that quietly ran without a reaper is a host where one
    # hard kill locks a conversation for good. See
    # `configs/policies/worker_runs@1.0.0.yaml` for the number and its limits.
    stale_run_after_seconds: int

    async def _execute(self, run_context: RunContext, statement: sa.Executable) -> Any:
        return await self._execute_for_tenant(run_context.tenant_id, statement)

    async def _execute_for_tenant(self, tenant_id: uuid.UUID, statement: sa.Executable) -> Any:
        async with self.session_factory() as session, session.begin():
            await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
            return await session.execute(statement)

    async def _write_and_announce(
        self, run_context: RunContext, statement: sa.Executable, status: RunStatus
    ) -> None:
        """One transaction for the write and the announcement of it.

        Postgres holds a NOTIFY until the transaction commits and drops it if
        the transaction does not, so a listener cannot be told about a state
        that was rolled back - and cannot miss one that was not. That property
        is the whole reason the announcement is here rather than in the caller
        that just finished awaiting the write.
        """
        async with self.session_factory() as session, session.begin():
            await session.execute(_SET_TENANT, {"tenant_id": str(run_context.tenant_id)})
            await session.execute(statement)
            await session.execute(
                _NOTIFY,
                {"payload": _announcement(run_context, status)},
            )

    async def create(
        self,
        run_context: RunContext,
        *,
        worker: WorkerDefinition,
        input_payload: dict[str, Any],
        release_manifest_ref: str | None = None,
    ) -> None:
        """Claim the thread for this run, or refuse because someone else has it.

        The claim is the insert: `uq_worker_runs_active_thread` lets exactly one
        unfinished run exist per thread, so two concurrent turns cannot both
        believe they won.

        Takes the whole worker definition rather than a graph version and four
        more strings beside it. The row has to carry every artifact version the
        run was pinned to, and passing them one by one is how the row comes to
        disagree with the worker: five arguments are five chances to pass last
        week's value, and an argument nobody passes is a NULL nobody notices.
        """
        try:
            await self._insert(
                run_context,
                worker=worker,
                input_payload=input_payload,
                release_manifest_ref=release_manifest_ref,
            )
        except IntegrityError as exc:
            if ACTIVE_THREAD_INDEX not in str(exc.orig):
                raise
            thread_id = run_context.thread_id or run_context.run_id
            # Two unfinished runs cannot share a thread, but the two ways to get
            # here need different things from the user: one waits, the other
            # decides. Reporting both as "in flight" sent people to wait out an
            # approval that was only ever going to move when they clicked it.
            approval_id = await self.waiting_approval_for_thread(run_context.tenant_id, thread_id)
            if approval_id is not None:
                raise ConflictError(
                    "this conversation is waiting for an approval decision",
                    details={
                        "thread_id": str(thread_id),
                        "approval_request_id": str(approval_id),
                    },
                ) from exc
            # The approval check comes first and stays first: a thread parked on
            # a decision is not stale, however long it waits, and reaping it
            # would throw away the pause a person still has to answer.
            if await self._reap_stale_thread(run_context.tenant_id, thread_id):
                await self._insert(
                    run_context,
                    worker=worker,
                    input_payload=input_payload,
                    release_manifest_ref=release_manifest_ref,
                )
                return
            raise ConflictError(
                "this conversation already has a turn in flight",
                details={"thread_id": str(thread_id)},
            ) from exc

    async def _reap_stale_thread(self, tenant_id: uuid.UUID, thread_id: uuid.UUID) -> bool:
        """Settle a run whose process is gone, so its thread can be used again.

        Only on the claim path, and only for the one thread being claimed. A
        background sweep would have to read across tenants, and `worker_runs` is
        behind RLS with the tenant set per transaction - a cross-tenant reaper
        needs `BYPASSRLS`, which is the migrator's alone. This is also the only
        moment a stranded row does any harm.

        Aged against the DATABASE clock, not `UtcClock`: `updated_at` is written
        with `now()` on the server, and comparing a server timestamp to a
        client one is how two clocks a few seconds apart become a bug nobody can
        reproduce. This is where it deliberately parts company with
        a context's own `reap_stale(older_than=...)`, whose `heartbeat_at` IS
        written client-side.

        Reports whether anything was freed, because the caller has to tell
        "there is room now" from "somebody else is genuinely mid-turn".
        """
        result = await self._execute_for_tenant(
            tenant_id,
            sa.update(worker_runs)
            .where(
                worker_runs.c.thread_id == thread_id,
                worker_runs.c.status == RunStatus.RUNNING.value,
                # A bound INTERVAL, not an interpolated one. The number is an
                # int from a validated policy and could not carry SQL, but a
                # value spliced into a statement is a habit worth not having.
                worker_runs.c.updated_at
                < sa.func.now() - timedelta(seconds=self.stale_run_after_seconds),
            )
            .values(
                status=RunStatus.FAILED.value,
                updated_at=sa.func.now(),
                error={
                    "type": "StaleRun",
                    "message": (
                        "tiến trình chạy run này đã biến mất; run được dọn để mở lại hội thoại"
                    ),
                },
            ),
        )
        return bool(result.rowcount)

    async def waiting_approval_for_thread(
        self, tenant_id: uuid.UUID, thread_id: uuid.UUID
    ) -> uuid.UUID | None:
        """The approval a thread is parked on, or None if it is free to run.

        A paused thread refuses every new turn, and the only thing that unparks
        it is a decision on this row - so a caller that cannot find it has no
        way forward. The live stream is not the only route to the card: a reload
        or a second device arrives with no memory of the turn that paused.
        """
        result = await self._execute_for_tenant(
            tenant_id,
            sa.select(worker_runs.c.approval_request_id).where(
                worker_runs.c.thread_id == thread_id,
                worker_runs.c.status == RunStatus.WAITING_APPROVAL.value,
            ),
        )
        row = result.first()
        return None if row is None else row.approval_request_id

    async def started_since(self, tenant_id: uuid.UUID, since: datetime) -> int:
        """How many runs this tenant has started since ``since``.

        Every run, whatever its outcome: a run that failed still spent the
        model calls the quota is there to bound, and counting only successes
        would make a failing worker free to loop.

        The boundary is passed in rather than computed here as
        ``date_trunc('day', now())``: that function reads the session's
        ``TimeZone``, so the same tenant's day would start at a different
        instant on a connection whose timezone happened to differ. The caller
        holds a ``UtcClock`` and states the instant.
        """
        result = await self._execute_for_tenant(
            tenant_id,
            sa.select(sa.func.count())
            .select_from(worker_runs)
            .where(worker_runs.c.created_at >= since),
        )
        count: int = result.scalar_one()
        return count

    async def spend_since(self, tenant_id: uuid.UUID, since: datetime) -> Decimal:
        """What this tenant has spent since ``since``, in USD.

        The other half of a quota. `started_since` bounds how MANY runs a tenant
        makes; this bounds what they cost, and without it a plan of twenty runs
        a day is twenty chances to spend without limit — the per-run ceiling
        caps one loop, never a day.

        `COALESCE`: a tenant with no runs, or runs that recorded no cost yet,
        has spent nothing. `SUM` over no rows is NULL, and a NULL compared
        against a limit is neither above nor below it — which would read as
        "under quota" and make the cap silently absent exactly when the table
        is empty.

        Summed from `model_usage_ledger`, not from `worker_runs`: the run table
        carries no cost column at all. Cost is recorded per model CALL, which is
        also the right grain — a run that is still going has already spent what
        its finished calls cost, and a cap that only counted settled runs would
        let a single long run outspend the day.

        Written against the wrong table first, and neither mypy nor ruff said a
        word: SQLAlchemy resolves `table.c.<name>` at runtime, so a column that
        does not exist is an AttributeError in production and nothing at all in
        a type check. The integration test below is what says it.
        """
        result = await self._execute_for_tenant(
            tenant_id,
            sa.select(sa.func.coalesce(sa.func.sum(model_usage_ledger.c.cost_usd), 0)).where(
                model_usage_ledger.c.created_at >= since
            ),
        )
        return Decimal(result.scalar_one())

    async def active_since(
        self,
        tenant_id: uuid.UUID,
        *,
        worker_id: str,
        subject_ref: str,
    ) -> datetime | None:
        """When the oldest still-running run for this subject started, or None.

        A surface that triggers work it does not wait for has no other way to
        say "this is in progress" - and "no result yet" reads to a user as "it
        failed", which is the one thing it does not mean. The row exists from
        the moment the run is created, so this answers correctly no matter who
        started the run: the requester's own click, another device, or a worker
        reacting to an event nobody clicked at all.

        Matched on the run's declared subject rather than on its input payload:
        what a run is about is a platform fact every worker states the same way,
        while the payload is each worker's own shape.
        """
        result = await self._execute_for_tenant(
            tenant_id,
            sa.select(sa.func.min(worker_runs.c.created_at)).where(
                worker_runs.c.worker_id == worker_id,
                worker_runs.c.subject_ref == subject_ref,
                worker_runs.c.status.notin_([status.value for status in TERMINAL_STATUSES]),
            ),
        )
        started: datetime | None = result.scalar_one_or_none()
        return started

    async def _insert(
        self,
        run_context: RunContext,
        *,
        worker: WorkerDefinition,
        input_payload: dict[str, Any],
        release_manifest_ref: str | None,
    ) -> None:
        await self._write_and_announce(
            run_context,
            sa.insert(worker_runs).values(
                id=run_context.run_id,
                thread_id=run_context.thread_id or run_context.run_id,
                tenant_id=run_context.tenant_id,
                workspace_id=run_context.workspace_id,
                worker_id=run_context.worker_id,
                worker_version=run_context.worker_version,
                graph_version=worker.graph_version,
                # Every artifact version the run is pinned to, on the row that
                # produced the result. The trace carries them too, but a trace is
                # sampled and expires; this is the system of record.
                prompt_bundle_version=worker.prompt_bundle_version,
                toolset_version=worker.toolset_version,
                policy_version=worker.policy_version,
                memory_policy_version=worker.memory_policy_version,
                autonomy_level=run_context.autonomy_level,
                approval_policy_version=run_context.approval_policy_version,
                status=RunStatus.RUNNING.value,
                input=input_payload,
                requested_by=run_context.actor_id,
                actor_roles=sorted(run_context.roles),
                actor_scopes=sorted(run_context.scopes),
                actor_plan_id=run_context.plan_id,
                actor_clearance=run_context.clearance,
                actor_record_visibility=run_context.record_visibility,
                actor_visible_owners=(
                    None
                    if run_context.visible_owners is None
                    else sorted(run_context.visible_owners)
                ),
                trace_id=run_context.trace_id,
                subject_ref=run_context.subject_ref,
                release_manifest_ref=release_manifest_ref,
                created_at=sa.func.now(),
                updated_at=sa.func.now(),
            ),
            RunStatus.RUNNING,
        )

    async def set_status(
        self,
        run_context: RunContext,
        run_id: uuid.UUID,
        status: RunStatus,
        *,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        approval_request_id: uuid.UUID | None = None,
    ) -> None:
        values: dict[str, Any] = {"status": status.value, "updated_at": sa.func.now()}
        if result is not None:
            values["result"] = result
        if error is not None:
            values["error"] = error
        if approval_request_id is not None:
            values["approval_request_id"] = approval_request_id
        await self._write_and_announce(
            run_context,
            sa.update(worker_runs).where(worker_runs.c.id == run_id).values(**values),
            status,
        )

    async def get(self, run_context: RunContext, run_id: uuid.UUID) -> RunRecord:
        result = await self._execute(
            run_context, sa.select(worker_runs).where(worker_runs.c.id == run_id)
        )
        row = result.first()
        if row is None:
            raise NotFoundError("run not found", details={"run_id": str(run_id)})
        return RunRecord(
            id=row.id,
            thread_id=row.thread_id,
            status=RunStatus(row.status),
            worker_id=row.worker_id,
            worker_version=row.worker_version,
            graph_version=row.graph_version,
            prompt_bundle_version=row.prompt_bundle_version,
            toolset_version=row.toolset_version,
            policy_version=row.policy_version,
            memory_policy_version=row.memory_policy_version,
            autonomy_level=row.autonomy_level,
            approval_policy_version=row.approval_policy_version,
            input=dict(row.input),
            result=dict(row.result) if row.result is not None else None,
            error=dict(row.error) if row.error is not None else None,
            approval_request_id=row.approval_request_id,
            release_manifest_ref=row.release_manifest_ref,
            requested_by=row.requested_by,
            actor_roles=frozenset(row.actor_roles),
            actor_scopes=frozenset(row.actor_scopes),
            actor_plan_id=row.actor_plan_id,
            actor_clearance=row.actor_clearance,
            actor_record_visibility=row.actor_record_visibility,
            actor_visible_owners=(
                None if row.actor_visible_owners is None else frozenset(row.actor_visible_owners)
            ),
        )

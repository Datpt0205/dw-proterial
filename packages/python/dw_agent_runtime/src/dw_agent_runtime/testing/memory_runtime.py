"""The runtime in one process: the real runner and approval flow, stores in memory.

For a context's evals and unit tests, which run on every push without a
database. What runs here is the code a deployment runs: `LangGraphWorkflowRunner`
(start, interrupt to an approval request, resume, withdraw, the run quota) and
`ApproveAndResumeService` (the decide scope, separation of duties, a context's
decision guard). Only what PostgreSQL holds is replaced: the run rows, the
approval rows, the audit log and LangGraph's checkpoints.

What this does not show, and where it is shown instead: row-level security,
the active-thread index and the grants, by the runtime's and the platform's
integration suites. Each double here refuses what its SQL counterpart refuses
where a caller could notice the difference (a second unfinished run on a
thread, a stale approval version, another tenant's run).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from types import TracebackType
from typing import Any, Self, cast

from langgraph.checkpoint.memory import InMemorySaver

from dw_agent_runtime.adapters.langgraph_runner import LangGraphWorkflowRunner
from dw_agent_runtime.adapters.run_store import (
    TERMINAL_STATUSES,
    RunRecord,
    RunStatus,
    WaitingRun,
)
from dw_agent_runtime.approval_flow import ApproveAndResumeService
from dw_agent_runtime.autonomy import AutonomyApprovalPolicy
from dw_agent_runtime.contracts import RunContext, WorkerDefinition
from dw_agent_runtime.model.budget import RunBudgetLedger
from dw_agent_runtime.ports import RunAllowancePort
from dw_agent_runtime.registry import GraphRegistry, WorkerRegistry
from dw_kernel.errors import ConflictError, NotFoundError
from dw_kernel.pagination import CursorPosition, Page, PageRequest, build_page
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ApprovalAudience
from dw_platform.application.ports import PlatformUnitOfWork
from dw_platform.domain.approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
)
from dw_platform.domain.audit import AuditEvent


@dataclass
class _Run:
    context: RunContext
    worker: WorkerDefinition
    input: dict[str, Any]
    created_at: datetime
    release_manifest_ref: str | None
    status: RunStatus = RunStatus.RUNNING
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    approval_request_id: uuid.UUID | None = None


@dataclass
class MemoryRuns:
    """`SqlWorkerRunStore`'s methods the runner and the approval flow call."""

    clock: UtcClock
    rows: dict[uuid.UUID, _Run] = field(default_factory=dict)

    async def create(
        self,
        run_context: RunContext,
        *,
        worker: WorkerDefinition,
        input_payload: dict[str, Any],
        release_manifest_ref: str | None = None,
    ) -> None:
        thread = run_context.thread_id or run_context.run_id
        if any(
            (r.context.thread_id or r.context.run_id) == thread
            and r.status not in TERMINAL_STATUSES
            for r in self.rows.values()
        ):
            raise ConflictError("this conversation already has a turn in flight")
        self.rows[run_context.run_id] = _Run(
            context=run_context,
            worker=worker,
            input=input_payload,
            created_at=self.clock.now(),
            release_manifest_ref=release_manifest_ref,
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
        row = self._row(run_context.tenant_id, run_id)
        row.status = status
        if result is not None:
            row.result = result
        if error is not None:
            row.error = error
        if approval_request_id is not None:
            row.approval_request_id = approval_request_id

    async def get(self, run_context: RunContext, run_id: uuid.UUID) -> RunRecord:
        row = self._row(run_context.tenant_id, run_id)
        started = row.context
        return RunRecord(
            id=run_id,
            thread_id=started.thread_id or run_id,
            workspace_id=started.workspace_id,
            status=row.status,
            worker_id=started.worker_id,
            worker_version=started.worker_version,
            graph_version=row.worker.graph_version,
            prompt_bundle_version=row.worker.prompt_bundle_version,
            toolset_version=row.worker.toolset_version,
            policy_version=row.worker.policy_version,
            memory_policy_version=row.worker.memory_policy_version,
            autonomy_level=started.autonomy_level,
            approval_policy_version=started.approval_policy_version,
            input=row.input,
            result=row.result,
            error=row.error,
            approval_request_id=row.approval_request_id,
            release_manifest_ref=row.release_manifest_ref,
            requested_by=started.actor_id,
            actor_roles=started.roles,
            actor_scopes=started.scopes,
            actor_plan_id=started.plan_id,
            actor_clearance=started.clearance,
            actor_record_visibility=started.record_visibility,
            actor_visible_owners=started.visible_owners,
        )

    async def started_since(self, tenant_id: uuid.UUID, since: datetime) -> int:
        return sum(
            1
            for r in self.rows.values()
            if r.context.tenant_id == tenant_id and r.created_at >= since
        )

    async def waiting_for_subject(
        self,
        tenant_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        worker_id: str,
        subject_ref: str,
    ) -> list[WaitingRun]:
        return [
            WaitingRun(run_id, row.approval_request_id, row.context.actor_id)
            for run_id, row in sorted(self.rows.items(), key=lambda item: item[1].created_at)
            if (row.context.tenant_id, row.context.workspace_id) == (tenant_id, workspace_id)
            and row.context.worker_id == worker_id
            and row.context.subject_ref == subject_ref
            and row.status is RunStatus.WAITING_APPROVAL
            and row.approval_request_id is not None
        ]

    def _row(self, tenant_id: uuid.UUID, run_id: uuid.UUID) -> _Run:
        row = self.rows.get(run_id)
        if row is None or row.context.tenant_id != tenant_id:
            raise NotFoundError("run not found", details={"run_id": str(run_id)})
        return row


@dataclass
class MemoryApprovals:
    """`ApprovalRepositoryPort` over a dict; one tenant's rows per caller."""

    clock: UtcClock
    rows: dict[uuid.UUID, ApprovalRequest] = field(default_factory=dict)
    decisions: list[ApprovalDecision] = field(default_factory=list)
    tenant_id: uuid.UUID | None = None

    def scoped(self, tenant_id: uuid.UUID) -> MemoryApprovals:
        return MemoryApprovals(self.clock, self.rows, self.decisions, tenant_id)

    async def add(self, request: ApprovalRequest) -> None:
        request.created_at = request.created_at or self.clock.now()
        self.rows[request.id] = request

    async def get(
        self, request_id: uuid.UUID, *, workspace_id: uuid.UUID, audience: ApprovalAudience
    ) -> ApprovalRequest | None:
        request = self.rows.get(request_id)
        if (
            request is None
            or request.tenant_id.value != self.tenant_id
            or request.workspace_id.value != workspace_id
            or not audience.may_see(request)
        ):
            return None
        return request

    async def save(self, request: ApprovalRequest) -> None:
        # The aggregate is shared by reference; the SQL store's optimistic
        # check is on the version the decision moved it from.
        if request.id not in self.rows:
            raise ConflictError("approval request was modified concurrently")

    async def add_decision(self, decision: ApprovalDecision) -> None:
        self.decisions.append(decision)

    async def list_pending(
        self, request: PageRequest, *, workspace_id: uuid.UUID, audience: ApprovalAudience
    ) -> Page[ApprovalRequest]:
        pending = sorted(
            (
                r
                for r in self.rows.values()
                if r.tenant_id.value == self.tenant_id
                and r.workspace_id.value == workspace_id
                and r.status is ApprovalStatus.PENDING
                and audience.may_see(r)
            ),
            key=lambda r: (r.created_at, r.id),
            reverse=True,
        )

        def position(r: ApprovalRequest) -> CursorPosition:
            assert r.created_at is not None
            return CursorPosition(sort_value=r.created_at, tiebreaker=r.id)

        return build_page(pending[: request.fetch_limit], request=request, position_of=position)


@dataclass
class MemoryAudit:
    events: list[AuditEvent] = field(default_factory=list)

    async def append(self, event: AuditEvent) -> None:
        self.events.append(event)

    async def list_page(self, request: PageRequest, *, workspace_id: uuid.UUID) -> Page[AuditEvent]:
        raise NotImplementedError("not exercised by the runner or the approval flow")

    async def list_for_run(
        self, run_id: uuid.UUID, *, workspace_id: uuid.UUID, limit: int = 100
    ) -> list[AuditEvent]:
        return [
            e for e in self.events if e.run_id == run_id and e.workspace_id.value == workspace_id
        ][:limit]


class _Work:
    def __init__(self, approvals: MemoryApprovals, audit: MemoryAudit) -> None:
        self.approvals = approvals
        self.audit = audit

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


@dataclass(frozen=True)
class _Unmetered:
    """A plan with no daily limits: a real answer (`RunAllowancePort`)."""

    def runs_per_day(self, plan_id: str) -> int | None:
        return None

    def spend_usd_per_day(self, plan_id: str) -> Decimal | None:
        return None


@dataclass
class MemoryRuntime:
    """The runner and the approval flow over in-memory stores.

    Register a graph on ``graphs`` and load its worker on ``workers`` before
    starting a run, as a composition root does.
    """

    runner: LangGraphWorkflowRunner
    approval_flow: ApproveAndResumeService
    graphs: GraphRegistry
    workers: WorkerRegistry
    runs: MemoryRuns
    approvals: MemoryApprovals
    audit: MemoryAudit

    @classmethod
    def build(
        cls,
        *,
        clock: UtcClock,
        ids: IdGenerator,
        allowance: RunAllowancePort | None = None,
    ) -> MemoryRuntime:
        graphs = GraphRegistry()
        workers = WorkerRegistry(graph_registry=graphs)
        runs = MemoryRuns(clock)
        approvals = MemoryApprovals(clock)
        audit = MemoryAudit()

        def uow_factory(context: AccessContext) -> PlatformUnitOfWork:
            return cast(PlatformUnitOfWork, _Work(approvals.scoped(context.tenant_id), audit))

        runner = LangGraphWorkflowRunner(
            worker_registry=workers,
            graph_registry=graphs,
            # Typed for the SQL saver and store; these honour the same calls.
            checkpoint_saver=cast(Any, InMemorySaver()),
            run_store=cast(Any, runs),
            uow_factory=uow_factory,
            clock=clock,
            id_generator=ids,
            allowance=allowance or _Unmetered(),
            budget=RunBudgetLedger(),
            approval_policy=AutonomyApprovalPolicy(),
            release_manifest_ref="sha256:memory",
        )
        flow = ApproveAndResumeService(
            uow_factory=uow_factory,
            runner=runner,
            run_store=cast(Any, runs),
            clock=clock,
            id_generator=ids,
        )
        return cls(runner, flow, graphs, workers, runs, approvals, audit)

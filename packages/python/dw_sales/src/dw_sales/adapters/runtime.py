"""DW1's runs on the agent runtime: `Dw1RunsPort` and `PendingDecisionsPort`.

The run starts as the person who asked ("DW xử lý", "Trình duyệt", "Đã nhập
Bravo"), with what their verified access context holds: their scopes, their
plan (whose daily run allowance the runner checks before anything runs),
their clearance and record reach, and the tenant's autonomy ceiling. Nothing
in a request names any of it. The approval a run pauses on is therefore
requested by that person, who is a maker of what is decided: the pricer who
submits, the PIC who records the Bravo entry.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from dw_agent_runtime.adapters.run_store import WaitingRun
from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.ports import WorkflowRunnerPort
from dw_kernel.ports import IdGenerator
from dw_platform.application.access_context import AccessContext
from dw_sales.application.runs import Dw1Task
from dw_sales.workflows.graph import STATE_SCHEMA_VERSION


class SubjectApprovalsPort(Protocol):
    """The approval flow's subject lookups (`ApproveAndResumeService`)."""

    async def waiting(
        self, context: AccessContext, *, worker_id: str, subject_ref: str
    ) -> list[WaitingRun]: ...

    async def withdraw(
        self, context: AccessContext, *, worker_id: str, subject_ref: str
    ) -> int: ...


@dataclass(frozen=True)
class RuntimeDw1Runs:
    runner: WorkflowRunnerPort
    approvals: SubjectApprovalsPort
    ids: IdGenerator
    # The worker the runs are recorded under, as its config declares it.
    worker_id: str
    worker_version: str

    async def run(self, context: AccessContext, task: Dw1Task, *, subject_ref: str | None) -> None:
        run_id = self.ids.new_uuid()
        await self.runner.start(
            run_context=RunContext(
                run_id=run_id,
                tenant_id=context.tenant_id,
                workspace_id=context.workspace_id,
                actor_id=context.principal_id,
                worker_id=self.worker_id,
                worker_version=self.worker_version,
                channel="web",
                plan_id=context.plan_id,
                roles=context.roles,
                scopes=context.scopes,
                clearance=context.clearance,
                record_visibility=context.record_visibility,
                visible_owners=context.visible_owners,
                autonomy_ceiling=context.max_autonomy_level,
                trace_id=f"sales-{run_id.hex[:12]}",
                subject_ref=subject_ref,
            ),
            input_payload={
                "schema_version": STATE_SCHEMA_VERSION,
                "task": task.model_dump(mode="json"),
            },
        )

    async def pending(self, context: AccessContext, subject_ref: str) -> uuid.UUID | None:
        waiting = await self.approvals.waiting(
            context, worker_id=self.worker_id, subject_ref=subject_ref
        )
        # The newest: an older one is what a failed withdrawal left behind,
        # and the next submit withdraws it.
        return waiting[-1].approval_request_id if waiting else None

    async def withdraw(self, context: AccessContext, subject_ref: str) -> None:
        await self.approvals.withdraw(context, worker_id=self.worker_id, subject_ref=subject_ref)

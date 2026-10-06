"""Approve/reject a pending approval and resume its paused run.

Bridges platform approvals and the workflow runner: the human decision is
persisted first (aggregate invariant: decided exactly once), then the durable
run resumes with the decision payload.

Who may decide is the request's own answer (`ApprovalRequest.required_scope`):
the scope its raiser stamped on it, else the platform's `approvals.decide`.
A context checks a decision on its own approvals before it is recorded,
through an `ApprovalDecisionGuard` it registers here, so a decision the run
could not apply is refused while it can still be refused.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC
from typing import Any, Protocol

from dw_agent_runtime.adapters.run_store import (
    RunRecord,
    RunStatus,
    SqlWorkerRunStore,
    WaitingRun,
)
from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.ports import WorkflowRunnerPort
from dw_kernel.autonomy import FAIL_CLOSED_LEVEL
from dw_kernel.errors import ConflictError, NotFoundError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.application.ports import PlatformUnitOfWorkFactory
from dw_platform.domain.approval import (
    ApprovalAudience,
    ApprovalRequest,
    ApprovalStatus,
    DecisionOutcome,
)
from dw_platform.domain.audit import AuditEvent


@dataclass(frozen=True, slots=True)
class ProposedDecision:
    """A decision as its decider proposes it, before anything is recorded."""

    approve: bool
    comment: str
    # A reason per item the approval names (a Sales quote's blocking price
    # findings, by finding key). Empty when the approval names none.
    reasons: Mapping[str, str]
    # The version of the subject the decider was shown. The subject's guard
    # refuses a decision made on a version it has since left behind.
    subject_version: int | None


class ApprovalDecisionGuard(Protocol):
    """A context's own check of a decision on one of its approval types.

    Declared here, by the consumer, and satisfied by the context at the
    composition root (`decision_guards`). Called after the decider's scope and
    the separation-of-duties rules, before the decision is recorded: once it
    is recorded the run resumes with it, and a decision the run then refused
    would leave the approval decided and its subject undecided. The run
    applies the decision and checks it again there; this is the same check,
    made while a refusal still costs nothing.

    Raises the platform's errors (403, 404, 409, 422) as the subject would.
    """

    async def check(
        self, request: ApprovalRequest, decision: ProposedDecision, context: AccessContext
    ) -> None: ...


@dataclass
class ApproveAndResumeService:
    uow_factory: PlatformUnitOfWorkFactory
    runner: WorkflowRunnerPort
    run_store: SqlWorkerRunStore
    clock: UtcClock
    id_generator: IdGenerator
    strict_approval_prefixes: frozenset[str] = frozenset()
    # By approval-type prefix (`"sales."`), added where a context is wired:
    # `approval_flow.decision_guards["sales."] = guard`.
    decision_guards: dict[str, ApprovalDecisionGuard] = field(default_factory=dict)

    def is_strict(self, approval_type: str) -> bool:
        """Whether this type demands a second person and a written reason.

        Public because the UI has to know before it offers a decision: a form
        that hardcoded the prefixes would be a second copy of this policy, and
        the one it had let approvers submit decisions the server always refused.
        """
        return approval_type.startswith(tuple(self.strict_approval_prefixes))

    @staticmethod
    def audience(
        context: AccessContext, authorization: ScopeAuthorizationService
    ) -> ApprovalAudience:
        """The caller, as the decision and the inbox both read them."""
        return ApprovalAudience(
            principal_id=context.principal_id,
            workspace_id=context.workspace_id,
            scopes=context.scopes,
            unrestricted=authorization.is_unrestricted(context),
        )

    def _enforce_strict_rules(
        self, request: ApprovalRequest, comment: str, context: AccessContext
    ) -> None:
        # The requester and every maker the raiser named: a strict type is
        # decided by a second person, and "second" means none of the people
        # who made what is being decided, not only the one who asked.
        if context.principal_id in request.makers:
            raise ConflictError(
                "separation of duties (tách nhiệm): the requester or a maker of what is"
                " decided cannot decide it",
                details={
                    "approval_id": str(request.id),
                    "approval_type": request.approval_type,
                    "rule": "maker_checker",
                },
            )
        if not comment.strip():
            raise ConflictError(
                "this approval type requires a review comment",
                details={"approval_type": request.approval_type},
            )

    async def _resumable_run(
        self, context: AccessContext, request: ApprovalRequest
    ) -> RunRecord | None:
        if request.run_id is None:
            return None
        record = await self.run_store.get(
            self._run_context_for(context, request.run_id), request.run_id
        )
        if record.status is not RunStatus.WAITING_APPROVAL:
            raise ConflictError(
                "run is not waiting for approval",
                details={
                    "approval_id": str(request.id),
                    "run_id": str(request.run_id),
                    "status": record.status.value,
                },
            )
        if not self.runner.hosts(
            worker_id=record.worker_id,
            worker_version=record.worker_version,
            graph_version=record.graph_version,
        ):
            raise ConflictError(
                "this service does not run the graph that owns the approval",
                details={
                    "approval_id": str(request.id),
                    "worker_id": record.worker_id,
                    "worker_version": record.worker_version,
                    "graph_version": record.graph_version,
                },
            )
        return record

    async def decide(
        self,
        *,
        approval_id: uuid.UUID,
        approve: bool,
        comment: str,
        context: AccessContext,
        authorization: ScopeAuthorizationService,
        approved_action_ids: list[str] | None = None,
        reasons: Mapping[str, str] | None = None,
        subject_version: int | None = None,
    ) -> ApprovalRequest:
        async with self.uow_factory(context) as uow:
            request = await uow.approvals.get(approval_id)
            # Another workspace's request is not found: the caller's scopes are
            # this workspace's, and RLS narrows by tenant only.
            if request is None or request.workspace_id.value != context.workspace_id:
                raise NotFoundError(
                    "approval request not found", details={"approval_id": str(approval_id)}
                )
            # Approving is the decision that needs the right; WITHDRAWING your
            # own request is not. A seller who asks the assistant to do
            # something and then changes their mind must not have to find a
            # manager to take it back — without this the request sits pending
            # forever and its run stays parked (measured 2026-09-08: a sales
            # role got `permission_denied` on Reject as well as Approve).
            # The read moves above the gate so we know whose request it is;
            # it is already tenant/workspace-scoped by RLS.
            if approve or request.requested_by.value != context.principal_id:
                # The scope the request was raised under: `approvals.decide`
                # unless its raiser named its own.
                await authorization.require(
                    context=context,
                    action=request.required_scope,
                    resource_type="approval_request",
                    resource_id=str(approval_id),
                )
            if self.is_strict(request.approval_type):
                self._enforce_strict_rules(request, comment, context)
            proposal = ProposedDecision(
                approve=approve,
                comment=comment,
                reasons=dict(reasons or {}),
                subject_version=subject_version,
            )
            guard = self._guard_for(request.approval_type)
            if guard is not None:
                await guard.check(request, proposal, context)
            record = await self._resumable_run(context, request)

            decision = request.decide(
                decision_id=self.id_generator.new_uuid(),
                decided_by=UserId(context.principal_id),
                outcome=DecisionOutcome.APPROVED if approve else DecisionOutcome.REJECTED,
                decided_at=self.clock.now().astimezone(UTC),
                comment=comment,
            )
            await uow.approvals.save(request)
            await uow.approvals.add_decision(decision)
            await uow.commit()

        if record is not None and request.run_id is not None:
            resume_payload: dict[str, Any] = {
                "approved": approve,
                "comment": comment,
                # Who decided. The run resumes as its requester (below), so a
                # graph that records the decision needs the decider named.
                "decided_by": str(context.principal_id),
                "reasons": dict(proposal.reasons),
                "subject_version": proposal.subject_version,
            }
            if approved_action_ids is not None:
                resume_payload["approved_action_ids"] = approved_action_ids
            await self.runner.resume(
                run_context=RunContext(
                    run_id=request.run_id,
                    thread_id=record.thread_id,
                    tenant_id=context.tenant_id,
                    workspace_id=context.workspace_id,
                    actor_id=record.requested_by,
                    worker_id=record.worker_id,
                    worker_version=record.worker_version,
                    channel="web",
                    # Authority comes from the run, not from whoever is
                    # approving it. Separation of duties guarantees they are
                    # different people, so reading it from the approver's
                    # context handed their scopes to the requester's agent.
                    plan_id=record.actor_plan_id,
                    roles=record.actor_roles,
                    scopes=record.actor_scopes,
                    clearance=record.actor_clearance,
                    # Same reason as the roles and scopes above: the run
                    # resumes with the reach it started with, not with the
                    # approver's. Omitting these resumed with no owner limit
                    # at all, which widens rather than narrows.
                    record_visibility=record.actor_record_visibility,
                    visible_owners=record.actor_visible_owners,
                    # The autonomy the run started with, from its row — never
                    # re-resolved from the tenant's ceiling today, and never the
                    # approver's. A run started before 0006 has no stamp; it
                    # resumes at None, which the policy reads as ask-everything.
                    autonomy_level=record.autonomy_level,
                    autonomy_ceiling=record.autonomy_level or FAIL_CLOSED_LEVEL,
                    approval_policy_version=record.approval_policy_version,
                    trace_id=f"resume-{request.run_id.hex[:12]}",
                ),
                run_id=request.run_id,
                resume_payload=resume_payload,
            )
        return request

    async def waiting(
        self, context: AccessContext, *, worker_id: str, subject_ref: str
    ) -> list[WaitingRun]:
        """The runs about one subject parked on an approval, in the caller's
        workspace: how a page showing the subject finds what it waits on."""
        return await self.run_store.waiting_for_subject(
            context.tenant_id,
            workspace_id=context.workspace_id,
            worker_id=worker_id,
            subject_ref=subject_ref,
        )

    async def withdraw(self, context: AccessContext, *, worker_id: str, subject_ref: str) -> int:
        """Cancel what a subject waits on, once it moved on without a decision.

        Not a decision, and no scope is asked for here: the context calls this
        after it authorized the caller to move the subject (a quote priced
        again, an order revised), and leaving the approval open would only
        invite a decision on something that is no longer there. The approval
        is cancelled first, so nobody can decide it, then its run is settled
        as cancelled. One already decided is left to its decision. Returns how
        many were withdrawn.
        """
        withdrawn = 0
        for waiting in await self.waiting(context, worker_id=worker_id, subject_ref=subject_ref):
            async with self.uow_factory(context) as uow:
                request = await uow.approvals.get(waiting.approval_request_id)
                if request is None or request.status is not ApprovalStatus.PENDING:
                    continue
                request.cancel()
                await uow.approvals.save(request)
                await uow.audit.append(
                    AuditEvent(
                        id=self.id_generator.new_uuid(),
                        tenant_id=TenantId(context.tenant_id),
                        workspace_id=WorkspaceId(context.workspace_id),
                        actor_id=UserId(context.principal_id),
                        action="approval.withdrawn",
                        resource_type="approval_request",
                        resource_id=str(request.id),
                        run_id=waiting.run_id,
                        details={"approval_type": request.approval_type},
                        occurred_at=self.clock.now().astimezone(UTC),
                    )
                )
                await uow.commit()
            await self.runner.withdraw(
                run_context=self._run_context_for(
                    context, waiting.run_id, worker_id=worker_id, subject_ref=subject_ref
                ),
                run_id=waiting.run_id,
            )
            withdrawn += 1
        return withdrawn

    def _guard_for(self, approval_type: str) -> ApprovalDecisionGuard | None:
        matches = [prefix for prefix in self.decision_guards if approval_type.startswith(prefix)]
        return self.decision_guards[max(matches, key=len)] if matches else None

    def _run_context_for(
        self,
        context: AccessContext,
        run_id: uuid.UUID,
        *,
        worker_id: str = "unknown",
        subject_ref: str | None = None,
    ) -> RunContext:
        return RunContext(
            run_id=run_id,
            tenant_id=context.tenant_id,
            workspace_id=context.workspace_id,
            actor_id=context.principal_id,
            worker_id=worker_id,
            worker_version="0.0.0",
            channel="web",
            plan_id=context.plan_id,
            roles=context.roles,
            scopes=context.scopes,
            clearance=context.clearance,
            trace_id=f"lookup-{run_id.hex[:12]}",
            subject_ref=subject_ref,
        )

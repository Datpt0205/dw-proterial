"""A memory the policy will not write alone goes to a person, through the
platform's approval inbox.

`MemoryService.propose` opens one `memory.review` approval per REVIEW candidate,
in the candidate's own transaction. Deciding it is the platform's ordinary
`decide`; the decision reaches memory as the outbox event the approval flow
writes for every run-less approval, and `MemoryService.settle_review` acts on
it in the worker. This module holds what both sides name: the approval type,
the scope stamped on it, and the one condition memory puts on who may decide it.

**Stamped, like every type a context raises.** The platform decides on
`approvals.decide` AND the stamp (`docs/adr/0011`), so an unstamped request is
decided by whoever holds `approvals.decide` in the workspace, a Sales role
included. `memory.review` therefore carries `MEMORY_REVIEW_SCOPE`, held by the
platform's deciding roles (`approver`, `manager`, `director`, permission set
`approver_boost`) and by no context's role; the database refuses the type
unstamped (`ck_approval_requests_memory_review_stamped`).
"""

from __future__ import annotations

import uuid

from dw_kernel.errors import PermissionDeniedError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_knowledge.contracts import classifications_for_clearance
from dw_memory.policy import MemoryCandidate
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.approval import ApprovalRequest, decided_event_type

__all__ = [
    "MEMORY_REVIEW",
    "MEMORY_REVIEW_DECIDED",
    "MEMORY_REVIEW_SCOPE",
    "MemoryReviewGuard",
    "require_clearance_for_review",
    "review_request",
]

MEMORY_REVIEW = "memory.review"
"""The approval type of a held memory candidate."""

MEMORY_REVIEW_DECIDED = decided_event_type(MEMORY_REVIEW)
"""What the approval flow announces when one is decided."""

MEMORY_REVIEW_SCOPE = "memory.review"
"""What a person must hold, besides `approvals.decide`, to decide a
`memory.review`: the stamp on every one (`required_scope`). Granted by
migration `445f93c2ea2a` to the platform's deciding roles; the CHECK there
refuses the type with any other stamp or none."""


def review_request(
    *,
    approval_id: uuid.UUID,
    context: AccessContext,
    candidate_id: uuid.UUID,
    candidate: MemoryCandidate,
    reason: str,
) -> ApprovalRequest:
    """The `memory.review` approval for a held candidate, stamped.

    The payload is identifiers and the label: the content is served apart, to
    a clearance that covers it, and the label is what
    `require_clearance_for_review` checks the decider against.
    """
    return ApprovalRequest(
        id=approval_id,
        tenant_id=TenantId(context.tenant_id),
        workspace_id=WorkspaceId(context.workspace_id),
        approval_type=MEMORY_REVIEW,
        requested_by=UserId(context.principal_id),
        reason=reason,
        payload={
            "candidate_id": str(candidate_id),
            "worker_id": candidate.worker_id,
            "memory_type": candidate.memory_type.value,
            "classification": candidate.classification,
        },
        required_scope=MEMORY_REVIEW_SCOPE,
    )


def require_clearance_for_review(request: ApprovalRequest, context: AccessContext) -> None:
    """A person may not decide on a memory they are not cleared to read.

    Approving a fact is vouching for its content, and rejecting it is judging
    that content; neither is possible without reading it, and the candidate's
    content is served only to a clearance that covers it. The label is the one
    stamped on the approval when it was opened, written by memory and not by the
    client, and read through the same ladder recall filters by.

    A payload without a label refuses: it is not a memory review this build
    opened, and "no label" must not read as "nothing to protect".
    """
    classification = request.payload.get("classification")
    if not isinstance(classification, str) or classification not in (
        classifications_for_clearance(context.clearance)
    ):
        raise PermissionDeniedError(
            "your clearance does not cover the memory this approval would decide",
            details={"approval_id": str(request.id), "clearance": context.clearance},
        )


class MemoryReviewGuard:
    """`require_clearance_for_review` in the shape the approval flow calls.

    The flow's `ApprovalDecisionGuard` is asked with the proposed decision as
    well; memory's condition is on the decider alone, so the decision is
    accepted and not read.
    """

    async def check(
        self, request: ApprovalRequest, decision: object, context: AccessContext
    ) -> None:
        require_clearance_for_review(request, context)

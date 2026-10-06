"""Approval aggregate: human decisions gating critical side effects (§11.3).

Invariant: a request is decided exactly once; decisions are immutable facts.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Final

from dw_kernel.errors import ConflictError
from dw_kernel.ids import TenantId, UserId, WorkspaceId

# Who decides an approval whose raiser named no scope of its own: the
# platform's approver authority (the `approver` ladder and `approver_boost`).
DEFAULT_DECIDE_SCOPE: Final = "approvals.decide"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class DecisionOutcome(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """Immutable record of one human decision."""

    id: uuid.UUID
    request_id: uuid.UUID
    tenant_id: TenantId
    workspace_id: WorkspaceId
    decided_by: UserId
    outcome: DecisionOutcome
    comment: str
    decided_at: datetime


@dataclass(slots=True)
class ApprovalRequest:
    """A pending question for a human; pauses the workflow that raised it."""

    id: uuid.UUID
    tenant_id: TenantId
    workspace_id: WorkspaceId
    approval_type: str
    requested_by: UserId
    reason: str
    payload: dict[str, object] = field(default_factory=dict)
    run_id: uuid.UUID | None = None
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime | None = None
    decided_at: datetime | None = None
    version: int = 1

    @property
    def decide_scope(self) -> str | None:
        """The scope the raiser stamped on this request, if it named one.

        Stamped at creation, in the payload the graph interrupted with, and
        read from there by every later reader (the decision, the inbox): a
        request's authority is the one it was raised under, not whatever a
        registry says on the day it is decided. A context whose approvals are
        not the platform approver's to decide (a Sales quote is decided by
        `sales.quote.approve`, never by `approvals.decide`) names its scope
        here. Code writes the payload's top level; a model's arguments travel
        nested under it (`langchain_tools._ask_human`), never beside it.
        """
        scope = self.payload.get("decide_scope")
        if scope is None:
            return None
        if not isinstance(scope, str) or not scope.strip():
            raise ConflictError(
                "approval request names an unreadable decide scope",
                details={"request_id": str(self.id)},
            )
        return scope

    @property
    def required_scope(self) -> str:
        """The scope a person needs to decide this request."""
        return self.decide_scope or DEFAULT_DECIDE_SCOPE

    @property
    def makers(self) -> frozenset[uuid.UUID]:
        """Everyone the raiser named as having made what is being decided.

        The requester is one of them by definition; a case can have more (an
        order's preparer, its Bravo recorder in this round and earlier ones).
        A strict approval type refuses every one of them as its decider.
        Unreadable fails closed: a request whose makers cannot be read is
        decided by nobody, rather than by a maker the parse dropped.
        """
        raw = self.payload.get("makers", [])
        if not isinstance(raw, list):
            raise ConflictError(
                "approval request names its makers unreadably",
                details={"request_id": str(self.id)},
            )
        try:
            return frozenset(uuid.UUID(str(value)) for value in raw) | {self.requested_by.value}
        except ValueError:
            raise ConflictError(
                "approval request names its makers unreadably",
                details={"request_id": str(self.id)},
            ) from None

    def _require_pending(self) -> None:
        if self.status is not ApprovalStatus.PENDING:
            raise ConflictError(
                "approval request already decided",
                details={"request_id": str(self.id), "status": self.status.value},
            )

    def decide(
        self,
        *,
        decision_id: uuid.UUID,
        decided_by: UserId,
        outcome: DecisionOutcome,
        decided_at: datetime,
        comment: str = "",
    ) -> ApprovalDecision:
        """Apply a human decision; returns the immutable decision record."""
        self._require_pending()
        self.status = (
            ApprovalStatus.APPROVED
            if outcome is DecisionOutcome.APPROVED
            else ApprovalStatus.REJECTED
        )
        self.decided_at = decided_at
        self.version += 1
        return ApprovalDecision(
            id=decision_id,
            request_id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            decided_by=decided_by,
            outcome=outcome,
            comment=comment,
            decided_at=decided_at,
        )

    def cancel(self) -> None:
        self._require_pending()
        self.status = ApprovalStatus.CANCELLED
        self.version += 1


@dataclass(frozen=True, slots=True)
class ApprovalAudience:
    """Who is asking about approvals, as far as deciding and seeing them goes.

    One answer for the decision and the inbox: a request is listed to the
    people who may decide it and to the one who asked, and to nobody else.
    A Sales quote's payload is not a purchasing manager's to read just because
    `approvals.decide` would have let them decide a different approval type.
    The inbox's SQL filter (`SqlApprovalRepository.list_pending`) is this rule
    in another language; `test_approval_audience.py` holds the two together.
    """

    principal_id: uuid.UUID
    workspace_id: uuid.UUID
    # The caller's scopes in this workspace, from the verified access context.
    scopes: frozenset[str]
    # The platform admin, whom the authorization service allows everything.
    unrestricted: bool = False

    def may_decide(self, request: ApprovalRequest) -> bool:
        return request.workspace_id.value == self.workspace_id and (
            self.unrestricted or request.required_scope in self.scopes
        )

    def may_see(self, request: ApprovalRequest) -> bool:
        return self.may_decide(request) or (
            request.workspace_id.value == self.workspace_id
            and request.requested_by.value == self.principal_id
        )

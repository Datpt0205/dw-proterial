"""A request checked and sent to its approver (DW02 function 2).

- **Check** (`preview`): the request held to the company's master data
  (`domain.checks.cross_check`) and the approver its amount and findings name
  under the tenant's rules in force, shown and stamped on nothing.
- **Send** (`submit`): the same check under the rules in force, stamped on the
  case with the approver's tier, and a run-less platform approval
  `purchasing.request` opened in the same transaction, stamped with the scope
  the tier names (`required_scope`) and the case's makers (who received it,
  who sent it). `purchasing.` is strict at the composition root: a maker never
  decides, and a decision carries a written reason.
- **Decide**: on the platform's approvals (`POST /api/v1/approvals/{id}/
  decisions`), by a holder of the stamped scope. `RequestDecisions.check`, the
  context's decision guard, refuses before it is recorded a decision on a case
  that has moved on, or one shown an older version.
- **Carried out** (`RequestSettlement.settle`): the worker hands it
  `purchasing.request.decided`; it reads the outcome from the approval row,
  never from the event, and stamps the decision on the case, idempotently.

Every value that decides (the limits, the scope that approves each band, the
tolerance, which findings escalate) is the tenant's rule, read once and
stamped; nothing is re-derived when the decision is carried out.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel, ConfigDict

from dw_agent_runtime.approval_flow import ProposedDecision
from dw_kernel.errors import ConflictError, NotFoundError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ApprovalAudience
from dw_platform.domain.approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    decided_event_type,
)
from dw_platform.domain.audit import AuditEvent
from dw_purchasing.application.access import Gate, PurchasingScopes
from dw_purchasing.application.intake import CaseChange
from dw_purchasing.application.ports import MasterDataPort, PurchasingUnitOfWork
from dw_purchasing.application.rules import PurchasingRuleBook
from dw_purchasing.domain.cases import ApprovalAsked, CaseStatus, Decided, PurchaseCase
from dw_purchasing.domain.checks import CrossCheck, cross_check
from dw_purchasing.domain.rules import ApprovalRules, ApprovalTier, PurchasingRules

# The platform approval a request's sending opens, and the event its decision
# is announced by. Under `APPROVAL_PREFIX`, which the composition root makes
# strict and gives this context's decision guard.
APPROVAL_PREFIX: Final = "purchasing."
REQUEST_APPROVAL: Final = "purchasing.request"
REQUEST_DECIDED: Final = decided_event_type(REQUEST_APPROVAL)
_REASON: Final = "Yêu cầu mua hàng chờ duyệt"
_RESOURCE: Final = "purchase_case"
NO_LIMITS: Final = "quy tắc mua hàng đang áp dụng chưa có hạn mức duyệt: chưa gửi duyệt được"

_FROZEN = ConfigDict(frozen=True)


class PurchaseCheckView(BaseModel):
    """What the check found and who would approve, under the rules in force."""

    model_config = _FROZEN

    case_id: uuid.UUID
    case_version: int
    rules_ref: str
    check: CrossCheck
    required_scope: str
    tier_label: str


class RequestAsked(BaseModel):
    """The approval's payload: ids and a version, no line and no amount."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: uuid.UUID
    case_version: int
    makers: tuple[uuid.UUID, ...]


def _approval_rules(rules: PurchasingRules) -> ApprovalRules:
    if rules.approval is None:
        raise ConflictError(NO_LIMITS, details={"rules_ref": rules.ref, "rule": "no_limits"})
    return rules.approval


@dataclass(frozen=True)
class RequestApprovals:
    uow: PurchasingUnitOfWork
    gate: Gate
    rules: PurchasingRuleBook
    master: MasterDataPort
    clock: UtcClock
    ids: IdGenerator

    async def preview(self, context: AccessContext, case_id: uuid.UUID) -> PurchaseCheckView:
        await self.gate.require(
            context,
            PurchasingScopes.REQUEST_READ,
            resource_type=_RESOURCE,
            resource_id=str(case_id),
        )
        case = await self._case(context, case_id)
        rules = await self.rules.resolve(context)
        check, tier = await self._check(context, case, _approval_rules(rules))
        return PurchaseCheckView(
            case_id=case.case_id,
            case_version=case.case_version,
            rules_ref=rules.ref,
            check=check,
            required_scope=tier.scope,
            tier_label=tier.label,
        )

    async def submit(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int
    ) -> CaseChange:
        await self.gate.require(
            context,
            PurchasingScopes.REQUEST_SUBMIT,
            resource_type=_RESOURCE,
            resource_id=str(case_id),
        )
        case = await self._case(context, case_id)
        if case.case_version != case_version:
            raise ConflictError(
                "hồ sơ đã thay đổi: tải lại",
                details={"case_id": str(case_id), "rule": "stale_version"},
            )
        if case.status is not CaseStatus.RECEIVED:
            raise ConflictError(
                "chỉ gửi duyệt một yêu cầu vừa nhận",
                details={"case_id": str(case_id), "status": case.status.value},
            )
        rules = await self.rules.resolve(context)
        check, tier = await self._check(context, case, _approval_rules(rules))
        approval_id = self.ids.new_uuid()
        asked = ApprovalAsked(
            approval_id=approval_id,
            required_scope=tier.scope,
            tier_label=tier.label,
            limit=tier.up_to,
            limit_currency=_approval_rules(rules).currency,
            case_version=case.case_version + 1,
            submitted_by=context.principal_id,
            submitted_at=self.clock.now(),
        )
        sent = PurchaseCase.model_validate(
            {
                **case.model_dump(),
                "case_version": case.case_version + 1,
                "status": CaseStatus.AWAITING_APPROVAL,
                "check": check,
                "approval": asked,
            }
        )
        payload = RequestAsked(
            case_id=sent.case_id,
            case_version=sent.case_version,
            makers=tuple(sorted(sent.makers, key=str)),
        )
        async with self.uow(context) as work:
            await work.approvals.add(
                ApprovalRequest(
                    id=approval_id,
                    tenant_id=TenantId(context.tenant_id),
                    workspace_id=WorkspaceId(context.workspace_id),
                    approval_type=REQUEST_APPROVAL,
                    requested_by=UserId(context.principal_id),
                    reason=_REASON,
                    payload=payload.model_dump(mode="json"),
                    required_scope=tier.scope,
                )
            )
            await work.cases.save(sent, expected_version=case.case_version)
            await work.audit.append(
                _audit(
                    self.ids,
                    self.clock,
                    context,
                    "purchasing.request.submitted",
                    sent,
                    {
                        "approval_id": str(approval_id),
                        "required_scope": tier.scope,
                        "findings": ",".join(sorted(check.codes)),
                    },
                )
            )
        return CaseChange(case_id=sent.case_id, case_version=sent.case_version, status=sent.status)

    async def _case(self, context: AccessContext, case_id: uuid.UUID) -> PurchaseCase:
        async with self.uow(context) as work:
            case = await work.cases.get(case_id)
        if case is None:
            raise NotFoundError("không có yêu cầu mua hàng này", details={"case_id": str(case_id)})
        return case

    async def _check(
        self, context: AccessContext, case: PurchaseCase, rules: ApprovalRules
    ) -> tuple[CrossCheck, ApprovalTier]:
        master = await self.master.for_context(context)
        check = cross_check(
            case.request,
            master,
            today=self.clock.now().date(),
            tolerance_percent=rules.price_tolerance_percent,
        )
        return check, rules.tier_for(check)


def _asked(request: ApprovalRequest) -> RequestAsked:
    try:
        return RequestAsked.model_validate(request.payload)
    except ValueError as exc:
        raise ConflictError(
            "approval names no purchase case", details={"approval_id": str(request.id)}
        ) from exc


def _awaiting(case: PurchaseCase | None, request: ApprovalRequest) -> PurchaseCase:
    """The case still waiting on this very approval, or a refusal."""
    asked = _asked(request)
    if case is None or case.case_id != asked.case_id:
        raise NotFoundError(
            "không có yêu cầu mua hàng này", details={"case_id": str(asked.case_id)}
        )
    # The version it was sent at: every write moves a case's version, so a case
    # at that version still waits, in the state it was sent in.
    if (
        case.approval is None
        or case.approval.approval_id != request.id
        or case.case_version != asked.case_version
    ):
        raise ConflictError(
            "yêu cầu mua hàng không còn chờ quyết định này",
            details={"case_id": str(case.case_id), "status": case.status.value},
        )
    return case


@dataclass(frozen=True)
class RequestDecisions:
    """`ApprovalDecisionGuard` for `purchasing.request`: refuses, before the
    platform records it, a decision the case could not take."""

    uow: PurchasingUnitOfWork

    async def check(
        self, request: ApprovalRequest, decision: ProposedDecision, context: AccessContext
    ) -> None:
        asked = _asked(request)
        async with self.uow(context) as work:
            case = _awaiting(await work.cases.get(asked.case_id), request)
        if decision.subject_version is not None and decision.subject_version != case.case_version:
            raise ConflictError(
                "hồ sơ đã thay đổi từ khi người duyệt xem: tải lại",
                details={"case_id": str(case.case_id), "rule": "stale_version"},
            )


@dataclass(frozen=True)
class RequestSettlement:
    """Carries out a decided `purchasing.request` approval: the worker's
    handler for `REQUEST_DECIDED` calls it with the decider's tenancy and
    identity, from the event's envelope."""

    uow: PurchasingUnitOfWork
    clock: UtcClock
    ids: IdGenerator

    async def settle(self, approval_id: uuid.UUID, decider: AccessContext) -> CaseChange:
        """The decision, as its decider. What was decided is read from the
        approval row, which the decision wrote. Idempotent: a redelivery finds
        the case decided on this approval and writes nothing."""
        async with self.uow(decider) as work:
            case = await work.cases.by_approval(approval_id)
            if case is None or case.approval is None:
                raise NotFoundError(
                    "no purchase case waits on this approval",
                    details={"approval_id": str(approval_id)},
                )
            if case.decision is not None:
                return CaseChange(
                    case_id=case.case_id, case_version=case.case_version, status=case.status
                )
            # Read as the decider holding the stamp the platform required of
            # them when they decided: nobody reaches here but through it.
            audience = ApprovalAudience(
                context=decider.model_copy(
                    update={"scopes": frozenset({case.approval.required_scope})}
                ),
                holds_decide=True,
            )
            request = await work.approvals.get(
                approval_id, workspace_id=decider.workspace_id, audience=audience
            )
            if request is None:
                raise NotFoundError("approval not found", details={"approval_id": str(approval_id)})
            waiting = _awaiting(case, request)
            if request.status is ApprovalStatus.PENDING:
                raise ConflictError(
                    "the approval is not decided yet", details={"approval_id": str(approval_id)}
                )
            latest: ApprovalDecision | None = await work.approvals.latest_decision(
                approval_id, workspace_id=decider.workspace_id, audience=audience
            )
            approved = request.status is ApprovalStatus.APPROVED
            decided = PurchaseCase.model_validate(
                {
                    **waiting.model_dump(),
                    "case_version": waiting.case_version + 1,
                    "status": CaseStatus.APPROVED if approved else CaseStatus.REJECTED,
                    "decision": Decided(
                        approved=approved,
                        decided_by=decider.principal_id,
                        decided_at=self.clock.now(),
                        comment=(latest.comment if latest is not None else "")[:2000],
                    ),
                }
            )
            await work.cases.save(decided, expected_version=waiting.case_version)
            action = "purchasing.request.approved" if approved else "purchasing.request.rejected"
            await work.audit.append(
                _audit(
                    self.ids,
                    self.clock,
                    decider,
                    action,
                    decided,
                    {"approval_id": str(approval_id)},
                )
            )
        return CaseChange(
            case_id=decided.case_id, case_version=decided.case_version, status=decided.status
        )


def _audit(
    ids: IdGenerator,
    clock: UtcClock,
    context: AccessContext,
    action: str,
    case: PurchaseCase,
    details: dict[str, object],
) -> AuditEvent:
    # Ids, codes and the version: no line and no amount.
    return AuditEvent(
        id=ids.new_uuid(),
        tenant_id=TenantId(context.tenant_id),
        workspace_id=WorkspaceId(context.workspace_id),
        actor_id=UserId(context.principal_id),
        action=action,
        resource_type=_RESOURCE,
        resource_id=str(case.case_id),
        occurred_at=clock.now(),
        details={"case_version": case.case_version, **details},
    )

"""A choice of suppliers that comes to more than the approver's tier decides
goes back for approval at the tier its total names (Đạt, 2026-11-01:
"vượt hạn mức → hệ thống tự mở duyệt lại ở bậc tổng mới đòi hỏi").

- **When**: the choice's total passes the stamped tier's limit by more than
  the tenant's `reapproval_tolerance_percent` (rules 1.5.0, default 0), or is
  in another currency. Within it, the choice is the case's selection as
  before.
- **Who**: the tier code finds for the new total under the rules in force
  (`ApprovalRules.tier_for`), stamped on the case and on a strict, run-less
  approval `purchasing.reapproval`, whose makers are everyone who made the
  case and the buyer who chose: none of them decides it.
- **Why, in words**: the model writes the reason from code's facts (the
  request, the approved limit, the new total, the suppliers chosen, line by
  line); the words are kept only when every figure in them is one of the
  facts' (`figure_check.unsupported`), else none, and the approver reads the
  facts themselves. Never a template.
- **The decision**: approved, the waiting choice becomes the selection and
  the case goes on to its orders; rejected, the case goes back to choosing
  suppliers, the choice and the decision kept on the case.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from dw_agent_runtime.approval_flow import ProposedDecision
from dw_agent_runtime.context import caller_run
from dw_agent_runtime.model.figure_check import unsupported
from dw_agent_runtime.model.interpretation import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
)
from dw_kernel.errors import ConflictError, NotFoundError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ApprovalAudience
from dw_platform.domain.approval import ApprovalRequest, ApprovalStatus, decided_event_type
from dw_platform.domain.audit import AuditEvent
from dw_purchasing.application.intake import CaseChange, Worker
from dw_purchasing.application.ports import NoNotices, NoticesPort, PurchasingUnitOfWork
from dw_purchasing.domain.cases import (
    ApprovalAsked,
    CaseStatus,
    Decided,
    PurchaseCase,
    Reapproval,
)
from dw_purchasing.domain.rules import ApprovalRules
from dw_purchasing.domain.sourcing import Selection

REAPPROVAL: Final = "purchasing.reapproval"
REAPPROVAL_DECIDED: Final = decided_event_type(REAPPROVAL)
# The prompt the reason is worded with; its file is
# `configs/prompts/purchasing/reapproval_reason@1.0.0.yaml`.
REAPPROVAL_REASON: Final = PromptRef("purchasing.reapproval_reason", "1.0.0")
_OUTPUT_TOKENS: Final = 600
_REASON: Final = "Lựa chọn nhà cung cấp vượt hạn mức đã duyệt: duyệt lại"
_RESOURCE: Final = "purchase_case"
# Names the reason may say that are no figure of the facts.
_NAMES: Final = ("DW2",)


class ReasonWords(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: str = Field(min_length=1, max_length=1200)


class ReapprovalAsked(BaseModel):
    """The approval's payload: ids, a version and the makers; no amount."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: uuid.UUID
    case_version: int
    makers: tuple[uuid.UUID, ...]


def over_limit(case: PurchaseCase, total: Decimal, rules: ApprovalRules | None) -> bool:
    """Whether a choice totalling ``total`` passes what the approver decided,
    beyond the tenant's tolerance (or is in another currency)."""
    assert case.approval is not None
    limit = case.approval.limit
    if limit is None:
        return False
    if case.request.currency != case.approval.limit_currency:
        return True
    tolerance = rules.reapproval_tolerance_percent if rules is not None else Decimal(0)
    return total > limit * (Decimal(100) + tolerance) / Decimal(100)


@dataclass(frozen=True)
class Reapprovals:
    """Opens the approval a choice past the tier waits on."""

    model: InterpretationPort | None
    worker: Worker
    clock: UtcClock
    ids: IdGenerator
    notices: NoticesPort = field(default_factory=NoNotices)

    async def ask(
        self,
        context: AccessContext,
        uow: PurchasingUnitOfWork,
        case: PurchaseCase,
        selection: Selection,
        rules: ApprovalRules,
        offers: dict[tuple[str, int], Decimal],
    ) -> PurchaseCase:
        assert case.approval is not None and case.check is not None
        check = case.check.model_copy(
            update={"amount": selection.total, "currency": selection.currency}
        )
        tier = rules.tier_for(check)
        explanation = await self._reason(context, case, selection, tier.label, offers)
        approval_id = self.ids.new_uuid()
        now = self.clock.now()
        asked = ApprovalAsked(
            approval_id=approval_id,
            required_scope=tier.scope,
            tier_label=tier.label,
            limit=tier.up_to,
            limit_currency=rules.currency,
            case_version=case.case_version + 1,
            submitted_by=context.principal_id,
            submitted_at=now,
        )
        waiting = PurchaseCase.model_validate(
            {
                **case.model_dump(),
                "case_version": case.case_version + 1,
                "status": CaseStatus.AWAITING_REAPPROVAL,
                "reapproval": Reapproval(
                    approval=asked,
                    selection=selection,
                    approved_limit=case.approval.limit,
                    explanation=explanation,
                ),
            }
        )
        makers = tuple(sorted({*waiting.makers, context.principal_id}, key=str))
        async with uow(context) as work:
            await work.approvals.add(
                ApprovalRequest(
                    id=approval_id,
                    tenant_id=TenantId(context.tenant_id),
                    workspace_id=WorkspaceId(context.workspace_id),
                    approval_type=REAPPROVAL,
                    requested_by=UserId(context.principal_id),
                    reason=_REASON,
                    payload=ReapprovalAsked(
                        case_id=case.case_id, case_version=waiting.case_version, makers=makers
                    ).model_dump(mode="json"),
                    required_scope=tier.scope,
                )
            )
            await work.cases.save(waiting, expected_version=case.case_version)
            await work.audit.append(
                _audit(
                    self.ids,
                    self.clock,
                    context,
                    "purchasing.selection.reapproval_asked",
                    waiting,
                    {
                        "approval_id": str(approval_id),
                        "required_scope": tier.scope,
                        "worded_by": "model" if explanation else "none",
                    },
                )
            )
        await self.notices.tell(
            context,
            scopes=frozenset({tier.scope}),
            excluding=makers,
            source_key=f"purchasing.reapproval.asked:{approval_id}",
            title=f"Yêu cầu mua hàng {case.request.pr_no} cần duyệt lại",
            body=explanation or "Tổng theo nhà cung cấp đã chọn vượt hạn mức đã duyệt.",
            link=f"/purchasing/requests/{case.case_id}",
        )
        return waiting

    async def _reason(
        self,
        context: AccessContext,
        case: PurchaseCase,
        selection: Selection,
        tier_label: str,
        offers: dict[tuple[str, int], Decimal],
    ) -> str | None:
        """The model's words for why, from code's facts, or None."""
        if self.model is None:
            return None
        assert case.approval is not None
        lines = {line.line_no: line for line in case.request.lines}
        facts = json.dumps(
            {
                "request": case.request.pr_no,
                "currency": selection.currency,
                "approved_by": case.approval.tier_label,
                "approved_limit": _money(case.approval.limit),
                "chosen_total": _money(selection.total),
                "now_decided_by": tier_label,
                "lines": [
                    {
                        "line": c.line_no,
                        "description": lines[c.line_no].description,
                        "quantity": f"{lines[c.line_no].quantity.normalize():f}",
                        "supplier": c.supplier_code,
                        "unit_price": _money(offers.get((c.supplier_code, c.line_no))),
                    }
                    for c in selection.choices
                ],
            },
            ensure_ascii=False,
        )
        run = caller_run(
            context,
            run_id=self.ids.new_uuid(),
            worker_id=self.worker.worker_id,
            worker_version=self.worker.worker_version,
            trace="dw2-reapproval",
            subject_ref=f"purchase_case:{case.case_id}",
        )
        try:
            words = await self.model.interpret(
                REAPPROVAL_REASON,
                {"facts": facts},
                ReasonWords,
                run=run,
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except ModelUnavailableError:
            return None
        if unsupported(words.reason, facts, names=_NAMES):
            return None
        return words.reason


def _money(value: Decimal | None) -> str | None:
    return None if value is None else f"{value.normalize():f}"


def _asked(request: ApprovalRequest) -> ReapprovalAsked:
    try:
        return ReapprovalAsked.model_validate(request.payload)
    except ValueError as exc:
        raise ConflictError(
            "approval names no purchase case", details={"approval_id": str(request.id)}
        ) from exc


def _waiting(case: PurchaseCase | None, request: ApprovalRequest) -> PurchaseCase:
    """The case still waiting on this very reapproval, or a refusal."""
    asked = _asked(request)
    if case is None or case.case_id != asked.case_id:
        raise NotFoundError(
            "không có yêu cầu mua hàng này", details={"case_id": str(asked.case_id)}
        )
    if (
        case.status is not CaseStatus.AWAITING_REAPPROVAL
        or case.reapproval is None
        or case.reapproval.approval.approval_id != request.id
        or case.case_version != asked.case_version
    ):
        raise ConflictError(
            "lựa chọn nhà cung cấp không còn chờ quyết định này",
            details={"case_id": str(case.case_id), "status": case.status.value},
        )
    return case


@dataclass(frozen=True)
class ReapprovalDecisions:
    """`ApprovalDecisionGuard` for `purchasing.reapproval` (the longer prefix
    than `purchasing.`): a decision the case could no longer take is refused
    before it is recorded."""

    uow: PurchasingUnitOfWork

    async def check(
        self, request: ApprovalRequest, decision: ProposedDecision, context: AccessContext
    ) -> None:
        asked = _asked(request)
        async with self.uow(context) as work:
            case = _waiting(await work.cases.get(asked.case_id), request)
        if decision.subject_version is not None and decision.subject_version != case.case_version:
            raise ConflictError(
                "hồ sơ đã thay đổi từ khi người duyệt xem: tải lại",
                details={"case_id": str(case.case_id), "rule": "stale_version"},
            )


@dataclass(frozen=True)
class ReapprovalSettlement:
    """Carries out a decided `purchasing.reapproval`: the worker's handler for
    `REAPPROVAL_DECIDED`, as the decider, idempotent."""

    uow: PurchasingUnitOfWork
    clock: UtcClock
    ids: IdGenerator
    notices: NoticesPort = field(default_factory=NoNotices)

    async def settle(self, approval_id: uuid.UUID, decider: AccessContext) -> CaseChange:
        async with self.uow(decider) as work:
            case = await work.cases.by_approval(approval_id)
            if case is None or case.reapproval is None:
                raise NotFoundError(
                    "no purchase case waits on this approval",
                    details={"approval_id": str(approval_id)},
                )
            if case.reapproval.approval.approval_id == approval_id and (
                case.reapproval.decision is not None
            ):
                return CaseChange(
                    case_id=case.case_id, case_version=case.case_version, status=case.status
                )
            audience = ApprovalAudience(
                context=decider.model_copy(
                    update={"scopes": frozenset({case.reapproval.approval.required_scope})}
                ),
                holds_decide=True,
            )
            request = await work.approvals.get(
                approval_id, workspace_id=decider.workspace_id, audience=audience
            )
            if request is None:
                raise NotFoundError("approval not found", details={"approval_id": str(approval_id)})
            waiting = _waiting(case, request)
            if request.status is ApprovalStatus.PENDING:
                raise ConflictError(
                    "the approval is not decided yet", details={"approval_id": str(approval_id)}
                )
            latest = await work.approvals.latest_decision(
                approval_id, workspace_id=decider.workspace_id, audience=audience
            )
            approved = request.status is ApprovalStatus.APPROVED
            assert waiting.reapproval is not None
            decided_choice = waiting.reapproval.model_copy(
                update={
                    "decision": Decided(
                        approved=approved,
                        decided_by=decider.principal_id,
                        decided_at=self.clock.now(),
                        comment=(latest.comment if latest is not None else "")[:2000],
                    )
                }
            )
            decided = PurchaseCase.model_validate(
                {
                    **waiting.model_dump(),
                    "case_version": waiting.case_version + 1,
                    "status": (
                        CaseStatus.SUPPLIER_SELECTED if approved else CaseStatus.RFQ_DRAFTED
                    ),
                    "selection": waiting.reapproval.selection if approved else None,
                    "reapproval": decided_choice,
                }
            )
            await work.cases.save(decided, expected_version=waiting.case_version)
            action = (
                "purchasing.selection.reapproved"
                if approved
                else "purchasing.selection.reapproval_rejected"
            )
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
        verdict = "đã được duyệt lại" if approved else "bị từ chối khi duyệt lại"
        await self.notices.tell(
            decider,
            scopes=frozenset(),
            people=_people(decided),
            excluding=(decider.principal_id,),
            source_key=f"purchasing.reapproval.decided:{approval_id}",
            title=f"Lựa chọn nhà cung cấp cho {decided.request.pr_no} {verdict}",
            body=decided_choice.decision.comment[:500] if decided_choice.decision else "",
            link=f"/purchasing/requests/{decided.case_id}",
        )
        return CaseChange(
            case_id=decided.case_id, case_version=decided.case_version, status=decided.status
        )


def _people(case: PurchaseCase) -> Sequence[uuid.UUID]:
    found = [case.requested_by]
    if case.reapproval is not None:
        found.append(case.reapproval.approval.submitted_by)
    return [p for p in found if p is not None]


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

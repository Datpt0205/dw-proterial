"""A requester writes their own request in DW2: "Tôi cần mua…" (DW02
function 1, step 2 of DW2's automation).

- **What the requester types** is read by the model into spans only
  (`purchasing.pr_from_words@1.0.0`, the PR mail's answer shape); code finds
  every span in the words, parses every value, and keeps the lines whole or
  not at all (`domain.mail_reading.read_pr_words`). Nothing is stored: the
  draft comes back to the requester's page, filled, with what the company's
  form rules still ask for named. Words the model cannot read into a request
  come back as "DW2 chưa hiểu" with why, never a guessed line.
- **The requester sends it** (`submit`): the request is held to the same
  form rules as any other, numbered by code (`DW2-<yymmdd>-<6 hex>`; the
  tenant's own numbering is a decision Proterial owes), named for the
  signed-in person by the platform's directory, and stamped with them as
  `requested_by`: they see it, and they never approve it.

The words are a requester's, so nothing in them is an instruction: a
sentence asking to skip the budget or approve at once is text; code reads
only lines.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from dw_agent_runtime.context import caller_run
from dw_agent_runtime.model.interpretation import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
)
from dw_kernel.errors import DomainError, InfrastructureError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent
from dw_purchasing.application.access import Gate, PurchasingScopes
from dw_purchasing.application.intake import CaseChange, Worker
from dw_purchasing.application.ports import PeoplePort, PurchasingUnitOfWork
from dw_purchasing.application.rules import PurchasingRuleBook
from dw_purchasing.domain.cases import CaseStatus, PrSource, PurchaseCase
from dw_purchasing.domain.mail_reading import (
    MAX_MAIL_LINES,
    ModelPrMail,
    RequestDraft,
    read_pr_words,
)
from dw_purchasing.domain.requests import (
    Code,
    Currency,
    PrLine,
    PurchaseRequest,
    RequiredField,
)

# The prompt a requester's words are read with; its file is
# `configs/prompts/purchasing/pr_from_words@1.0.0.yaml`, held to it by test.
PR_FROM_WORDS: Final = PromptRef("purchasing.pr_from_words", "1.0.0")
MAX_WORDS: Final = 2000
_OUTPUT_TOKENS: Final = 80 * MAX_MAIL_LINES + 200
NOT_NOW: Final = "DW2 chưa đọc được lúc này: thử lại sau, hoặc điền bảng bên dưới"
_RESOURCE: Final = "purchase_case"

_FROZEN = ConfigDict(frozen=True)


class DraftView(BaseModel):
    """What the requester's page shows after DW2 read their words: the
    draft, what the form rules still ask for, or why there is none."""

    model_config = _FROZEN

    draft: RequestDraft | None
    # A field the tenant's form requires that the words do not give.
    missing: list[RequiredField]
    # Why the words are no request, as a code; the page words it.
    not_read: str | None


class MyRequest(BaseModel):
    """What a requester sends: no PR number and no requester name, which are
    code's and the directory's. ``department`` is read only where the
    directory names none for them."""

    model_config = ConfigDict(extra="forbid")

    department: str | None = Field(
        default=None, min_length=1, max_length=80, pattern=r"^[^\x00-\x1f\x7f]+$"
    )
    budget_code: Code | None = None
    currency: Currency
    need_by: date | None = None
    lines: tuple[PrLine, ...] = Field(min_length=1, max_length=100)
    note: str = Field(default="", max_length=1000)


@dataclass(frozen=True)
class RequesterDesk:
    uow: PurchasingUnitOfWork
    gate: Gate
    rules: PurchasingRuleBook
    people: PeoplePort
    model: InterpretationPort | None
    worker: Worker
    clock: UtcClock
    ids: IdGenerator

    async def draft(self, context: AccessContext, words: str) -> DraftView:
        await self.gate.require(context, PurchasingScopes.REQUEST_CREATE, resource_type=_RESOURCE)
        text = words.strip()
        if not text:
            raise DomainError("hãy viết điều cần mua", details={"rule": "words_empty"})
        if len(text) > MAX_WORDS:
            raise DomainError(
                f"dài hơn {MAX_WORDS} ký tự: hãy dùng bảng bên dưới",
                details={"rule": "words_long"},
            )
        if self.model is None:
            raise InfrastructureError(NOT_NOW, details={"reason_code": "no_model"})
        rules = await self.rules.resolve(context)
        run = caller_run(
            context,
            run_id=self.ids.new_uuid(),
            worker_id=self.worker.worker_id,
            worker_version=self.worker.worker_version,
            trace="dw2-pr-words",
            subject_ref="purchasing_words",
        )
        try:
            answer = await self.model.interpret(
                PR_FROM_WORDS,
                {"words": text},
                ModelPrMail,
                run=run,
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except ModelUnavailableError as exc:
            raise InfrastructureError(NOT_NOW, details={"reason_code": "model"}) from exc
        verdict = read_pr_words(
            text,
            answer,
            received_on=self.clock.now().date(),
            default_currency=rules.pr_form.default_currency,
        )
        if verdict.draft is None:
            return DraftView(draft=None, missing=[], not_read=verdict.not_read)
        probe = PurchaseRequest(
            pr_no="DRAFT",
            department="-",
            requester="-",
            budget_code=verdict.draft.budget_code,
            currency=verdict.draft.currency,
            need_by=verdict.draft.need_by,
            lines=verdict.draft.lines,
        )
        return DraftView(
            draft=verdict.draft,
            missing=list(probe.missing(rules.pr_form.required)),
            not_read=None,
        )

    async def submit(self, context: AccessContext, mine: MyRequest) -> CaseChange:
        await self.gate.require(context, PurchasingScopes.REQUEST_CREATE, resource_type=_RESOURCE)
        person = await self.people.person(context, context.principal_id)
        if person is None:
            raise DomainError(
                "không tìm thấy tên của bạn trong danh bạ công ty",
                details={"rule": "unknown_person"},
            )
        department = person.department.strip() or (mine.department or "").strip()
        if not department:
            raise DomainError(
                "danh bạ chưa ghi phòng ban của bạn: hãy chọn phòng ban",
                details={"reason_code": "request_incomplete", "refusals": "missing:department"},
            )
        rules = await self.rules.resolve(context)
        now = self.clock.now()
        case_id = self.ids.new_uuid()
        request = PurchaseRequest(
            pr_no=f"DW2-{now:%y%m%d}-{case_id.hex[:6].upper()}",
            department=department[:80],
            requester=person.display_name[:120],
            budget_code=mine.budget_code,
            currency=mine.currency,
            need_by=mine.need_by,
            lines=mine.lines,
            note=mine.note,
        )
        if refusals := rules.refusals(request):
            raise DomainError(
                "yêu cầu mua hàng thiếu thông tin quy tắc của công ty đòi hỏi",
                details={"reason_code": "request_incomplete", "refusals": ",".join(refusals)},
            )
        case = PurchaseCase(
            case_id=case_id,
            case_version=1,
            status=CaseStatus.RECEIVED,
            source=PrSource.REQUESTER,
            request=request,
            received_at=now,
            received_by=context.principal_id,
            requested_by=context.principal_id,
            rules_ref=rules.ref,
        )
        async with self.uow(context) as work:
            await work.cases.add(case)
            await work.audit.append(
                AuditEvent(
                    id=self.ids.new_uuid(),
                    tenant_id=TenantId(context.tenant_id),
                    workspace_id=WorkspaceId(context.workspace_id),
                    actor_id=UserId(context.principal_id),
                    action="purchasing.request.received",
                    resource_type=_RESOURCE,
                    resource_id=str(case.case_id),
                    occurred_at=now,
                    details={
                        "source": case.source.value,
                        "rules_ref": case.rules_ref,
                        "lines": len(request.lines),
                    },
                )
            )
        return CaseChange(case_id=case.case_id, case_version=1, status=case.status)

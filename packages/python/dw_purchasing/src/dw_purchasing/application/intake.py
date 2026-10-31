"""Receiving purchase requests (DW02 function 1): a form, or a mail DW2 reads.

- **A form** (`submit_form`): a buyer enters what a department asked for, or
  a department enters it itself. Held to the tenant's form rules (required
  fields, line count, currency); refused (422) naming what is missing, or a
  case is opened, stamped with the rules it was received under.
- **A mail** (`read_mail`): a person presses "DW2 đọc" on one message. The
  sender must be the company's (a domain the rules list) and verified by the
  mail system, or a person reads it. Then the model reads the newest part into
  spans (`sales` ADR 0005 as DW2 applies it, `domain.mail_reading`), code
  keeps what it can find and parse, and the request is held to the same form
  rules. A request opens a case; anything else goes to a person with a reason
  code. Either way the mail is settled once: pressing again reads nothing.
  No model, or no usable answer: nothing is recorded and the caller is told to
  try again (503), never a guessed request.

The model reads; code decides whether there is a request, who asked (the
verified sender) and under which rules. Nothing a mail says is an instruction.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from pydantic import BaseModel, ConfigDict

from dw_agent_runtime.context import caller_run
from dw_agent_runtime.model.interpretation import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    cut_to_tokens,
)
from dw_kernel.errors import DomainError, InfrastructureError, NotFoundError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent
from dw_platform.domain.mail_parts import newest_part
from dw_platform.domain.messages import InboundMessage
from dw_purchasing.application.access import Gate, PurchasingScopes
from dw_purchasing.application.ports import (
    Disposition,
    InboxPort,
    MessageOutcome,
    PurchasingUnitOfWork,
)
from dw_purchasing.application.rules import RuleBook
from dw_purchasing.domain.mail_reading import MAX_MAIL_LINES, ModelPrMail, read_pr_mail
from dw_purchasing.domain.requests import CaseStatus, PrSource, PurchaseCase, PurchaseRequest
from dw_purchasing.domain.rules import PurchasingRules

# The prompt DW2 reads a request in a mail with; its file is
# `configs/prompts/purchasing/pr_mail_reading@1.0.0.yaml`, held to it by test.
PR_MAIL_READING: Final = PromptRef("purchasing.pr_mail_reading", "1.0.0")
# About 60 tokens a line read, generously, and the header.
_OUTPUT_TOKENS: Final = 80 * MAX_MAIL_LINES + 200
# What the prompt's own words take, left out of the room for the mail.
_PROMPT_TOKENS: Final = 1200
NOT_READ_NOW: Final = "DW2 chưa đọc được thư lúc này: thử lại sau"
_RESOURCE: Final = "purchase_case"

_FROZEN = ConfigDict(frozen=True)


class CaseChange(BaseModel):
    """What a mutation answers: ids only, so an idempotent replay keeps no
    request content."""

    model_config = _FROZEN

    case_id: uuid.UUID
    case_version: int
    status: CaseStatus


class InboxItem(BaseModel):
    """One mail in the list a buyer works from."""

    model_config = _FROZEN

    message_id: str
    sender: str
    subject: str
    received_at: datetime
    disposition: Disposition | None
    reason: str | None
    case_id: uuid.UUID | None


@dataclass(frozen=True, slots=True)
class Worker:
    """DW2's worker, as `configs/workers/purchasing.yaml` names it: what a
    model call is recorded under."""

    worker_id: str
    worker_version: str


@dataclass(frozen=True)
class PurchaseRequests:
    uow: PurchasingUnitOfWork
    gate: Gate
    rules: RuleBook
    inbox: InboxPort
    # None where the deployment has no model: a mail is then not read.
    model: InterpretationPort | None
    worker: Worker
    clock: UtcClock
    ids: IdGenerator

    # ------------------------------------------------------------- reads --

    async def cases(
        self, context: AccessContext, *, limit: int, before: tuple[datetime, uuid.UUID] | None
    ) -> Sequence[PurchaseCase]:
        await self.gate.require(context, PurchasingScopes.REQUEST_READ, resource_type=_RESOURCE)
        async with self.uow(context) as work:
            return await work.cases.page(limit=limit, before=before)

    async def case(self, context: AccessContext, case_id: uuid.UUID) -> PurchaseCase:
        await self.gate.require(
            context,
            PurchasingScopes.REQUEST_READ,
            resource_type=_RESOURCE,
            resource_id=str(case_id),
        )
        async with self.uow(context) as work:
            case = await work.cases.get(case_id)
        if case is None:
            raise NotFoundError("không có yêu cầu mua hàng này", details={"case_id": str(case_id)})
        return case

    async def mailbox(self, context: AccessContext) -> list[InboxItem]:
        await self.gate.require(context, PurchasingScopes.REQUEST_READ, resource_type="mailbox")
        messages = await self.inbox.list_messages(context)
        async with self.uow(context) as work:
            settled = {o.message_id: o for o in await work.outcomes.all()}
        return [_item(m, settled.get(m.message_id)) for m in messages]

    # ---------------------------------------------------------- receiving --

    async def submit_form(self, context: AccessContext, request: PurchaseRequest) -> CaseChange:
        await self.gate.require(context, PurchasingScopes.REQUEST_INTAKE, resource_type=_RESOURCE)
        rules = await self.rules.resolve(context)
        if refusals := rules.refusals(request):
            raise DomainError(
                "yêu cầu mua hàng thiếu thông tin quy tắc của công ty đòi hỏi",
                details={"reason_code": "request_incomplete", "refusals": ",".join(refusals)},
            )
        case = self._open(context, request, rules, source=PrSource.FORM, source_ref=None)
        async with self.uow(context) as work:
            await work.cases.add(case)
            await work.audit.append(self._received(context, case))
        return _change(case)

    async def read_mail(self, context: AccessContext, message_id: str) -> InboxItem:
        await self.gate.require(
            context, PurchasingScopes.REQUEST_INTAKE, resource_type="mail", resource_id=message_id
        )
        message = await self.inbox.get_message(context, message_id)
        if message is None:
            raise NotFoundError("không có thư này", details={"message_id": message_id})
        async with self.uow(context) as work:
            if (settled := await work.outcomes.get(message_id)) is not None:
                return _item(message, settled)
        rules = await self.rules.resolve(context)
        request, reason = await self._read(context, message, rules)
        case = (
            self._open(context, request, rules, source=PrSource.MAIL, source_ref=message_id)
            if request is not None
            else None
        )
        outcome = MessageOutcome(
            message_id=message_id,
            disposition=Disposition.OPENED if case is not None else Disposition.TO_PERSON,
            reason=reason,
            case_id=case.case_id if case is not None else None,
            settled_by=context.principal_id,
            settled_at=self.clock.now(),
        )
        async with self.uow(context) as work:
            # The case first: the outcome names it. Refused (409) when a second
            # press settled the mail meanwhile, and the case goes with it.
            if case is not None:
                await work.cases.add(case)
                await work.audit.append(self._received(context, case))
            else:
                await work.audit.append(self._to_person(context, message_id, reason))
            await work.outcomes.add(outcome)
        return _item(message, outcome)

    async def _read(
        self, context: AccessContext, message: InboundMessage, rules: PurchasingRules
    ) -> tuple[PurchaseRequest | None, str | None]:
        """The request a mail holds, or why there is none."""
        if message.sender.domain not in rules.internal_domains:
            return None, "sender_not_internal"
        if not message.authentication.verified:
            return None, "sender_unverified"
        if self.model is None:
            raise InfrastructureError(NOT_READ_NOW, details={"reason_code": "no_model"})
        part = newest_part(message)
        room = self.model.max_input_tokens - _PROMPT_TOKENS - _OUTPUT_TOKENS
        shown = cut_to_tokens(part.text, room)
        run = caller_run(
            context,
            run_id=self.ids.new_uuid(),
            worker_id=self.worker.worker_id,
            worker_version=self.worker.worker_version,
            trace="dw2-pr-mail",
            subject_ref=f"purchasing_mail:{message.message_id}",
        )
        try:
            answer = await self.model.interpret(
                PR_MAIL_READING,
                {"mail": shown},
                ModelPrMail,
                run=run,
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except ModelUnavailableError as exc:
            raise InfrastructureError(NOT_READ_NOW, details={"reason_code": "model"}) from exc
        verdict = read_pr_mail(
            shown,
            answer,
            requester=message.sender.display_name or message.sender.address,
            received_on=message.received_at.date(),
            default_currency=rules.pr_form.default_currency,
        )
        if verdict.request is None:
            return None, verdict.not_read
        if refusals := rules.refusals(verdict.request):
            return None, refusals[0]
        return verdict.request, None

    def _open(
        self,
        context: AccessContext,
        request: PurchaseRequest,
        rules: PurchasingRules,
        *,
        source: PrSource,
        source_ref: str | None,
    ) -> PurchaseCase:
        return PurchaseCase(
            case_id=self.ids.new_uuid(),
            case_version=1,
            status=CaseStatus.RECEIVED,
            source=source,
            source_ref=source_ref,
            request=request,
            received_at=self.clock.now(),
            received_by=context.principal_id,
            rules_ref=rules.ref,
        )

    def _audit(
        self, context: AccessContext, action: str, resource_id: str, details: dict[str, object]
    ) -> AuditEvent:
        return AuditEvent(
            id=self.ids.new_uuid(),
            tenant_id=TenantId(context.tenant_id),
            workspace_id=WorkspaceId(context.workspace_id),
            actor_id=UserId(context.principal_id),
            action=action,
            resource_type=_RESOURCE,
            resource_id=resource_id,
            occurred_at=self.clock.now(),
            details=details,
        )

    def _received(self, context: AccessContext, case: PurchaseCase) -> AuditEvent:
        # Ids, the source and the rules only: no line, no amount.
        return self._audit(
            context,
            "purchasing.request.received",
            str(case.case_id),
            {
                "source": case.source.value,
                "rules_ref": case.rules_ref,
                "lines": len(case.request.lines),
            },
        )

    def _to_person(self, context: AccessContext, message_id: str, reason: str | None) -> AuditEvent:
        return self._audit(
            context, "purchasing.mail.to_person", message_id, {"reason": reason or "unknown"}
        )


def _change(case: PurchaseCase) -> CaseChange:
    return CaseChange(case_id=case.case_id, case_version=case.case_version, status=case.status)


def _item(message: InboundMessage, outcome: MessageOutcome | None) -> InboxItem:
    return InboxItem(
        message_id=message.message_id,
        sender=message.sender.address,
        subject=message.subject,
        received_at=message.received_at,
        disposition=outcome.disposition if outcome else None,
        reason=outcome.reason if outcome else None,
        case_id=outcome.case_id if outcome else None,
    )

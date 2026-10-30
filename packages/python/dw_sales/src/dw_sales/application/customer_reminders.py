"""A reminder to a customer DW1 is waiting on, drafted by the model (the
contract's DW01 function 4: "nhắc nhân viên bán hàng và khách hàng khi việc
chưa được xử lý đúng hạn").

Two waits are the customer's: an order whose correction was asked of them
(`correction_requested`, WIV-03-012 step 8) and a quote whose spec is being
discussed with them (`spec_discussion`). The follow-up lane already tells the
PIC when such a wait runs long (`waiting_customer`); it never writes to a
customer. On request, the model drafts the reminder the PIC sends, in the
customer's language, from facts code gathers: the customer's name, the PO or
request number, the day they were asked and, for an order, which points were
asked (each finding's kind and line, never its values). **Never an amount**:
a reminder chases an answer, it restates nothing a price check compared.

- Code checks every number, date and code in the subject and body is among
  the facts (`figure_check`), and that it names no amount at all. Otherwise
  there is no draft.
- Code chooses the recipients: the customer's contacts in the master data.
- Only a case the caller may see and prepare, and only while it waits on the
  customer: a case past that wait has nothing to remind them of (409).
- Nothing is sent and nothing is stored: the page opens the draft in the
  person's own mail program, as Q12's question does.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from dw_kernel.errors import ConflictError, NotFoundError, QuotaExceededError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.artifact_content import local_time
from dw_sales.application.case_store import LoggedEvent, SalesUnitOfWorkFactory
from dw_sales.application.figure_check import names_amount, unsupported
from dw_sales.application.model_reading import InterpretationPort, ModelUnavailableError, PromptRef
from dw_sales.application.ports import SalesCatalogPort
from dw_sales.application.runs import caller_run
from dw_sales.application.screening_followups import ModelFollowupMail
from dw_sales.application.support import stored_order, stored_quote
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import DispositionKind, OrderStatus
from dw_sales.domain.quotes import QuoteStatus

# The prompt the reminder is drafted with. Its file is
# `configs/prompts/sales/customer_reminder@1.0.0.yaml`; a test holds the two
# together, and the rendered prompt under `PROMPT_TOKENS`.
CUSTOMER_REMINDER: Final = PromptRef("sales.customer_reminder", "1.0.0")
PROMPT_TOKENS: Final = 900
_OUTPUT_TOKENS: Final = 700
# The status of each kind that waits on the customer (`domain.followups`
# watches the same two).
_WAITING: Final[dict[CaseKind, str]] = {
    CaseKind.ORDER: OrderStatus.CORRECTION_REQUESTED.value,
    CaseKind.QUOTE: QuoteStatus.SPEC_DISCUSSION.value,
}
_SCOPE: Final = {
    CaseKind.ORDER: SalesScopes.ORDER_PREPARE,
    CaseKind.QUOTE: SalesScopes.QUOTE_PREPARE,
}
NOT_WAITING_ON_CUSTOMER: Final = "the case is not waiting on the customer"


class CustomerReminderView(BaseModel):
    """A draft, or why there is none; always marked as the model's."""

    model_config = ConfigDict(frozen=True)

    case_id: uuid.UUID
    status: Literal["drafted", "unavailable", "refused"]
    # The customer's contacts in the master data: code's choice, not the model's.
    to: list[str] = []
    # The day the customer was asked, local time (`dd/mm/yyyy` on the page).
    asked_on: date
    subject: str | None = None
    body: str | None = None
    language: str | None = None
    prompt_ref: str | None = None
    model_profile: str | None = None


def asked_at(history: list[LoggedEvent], status: str, fallback: datetime) -> datetime:
    """When the case last entered ``status`` from another one: the wait's
    start, as the follow-up lane reads it."""
    moves = [
        e.occurred_at
        for e in history
        if e.to_status == status and e.from_status is not None and e.from_status != status
    ]
    return max(moves, default=fallback)


@dataclass(frozen=True)
class CustomerReminders:
    """`GET /{orders,quotes}/{case_id}/customer-reminder` (module docstring)."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    catalog: SalesCatalogPort
    model: InterpretationPort | None
    clock: UtcClock
    ids: IdGenerator
    worker_id: str
    worker_version: str

    async def draft(
        self, context: AccessContext, kind: CaseKind, case_id: uuid.UUID
    ) -> CustomerReminderView:
        resource = f"sales_{kind.value}_case"
        await self.gate.require(
            context, _SCOPE[kind], resource_type=resource, resource_id=str(case_id)
        )
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            if kind is CaseKind.ORDER:
                order = (await stored_order(work, case_id, viewer=context)).case
                status, customer_code, received = (
                    order.status.value,
                    order.customer_code,
                    order.received_at,
                )
                header = order.effective_header
                facts: dict[str, object] = {
                    "waiting_for": "corrected_po",
                    "po_no": header.po_no,
                    "po_date": _day(header.po_date),
                    "points_asked": [
                        {"issue": f.code.value, "line_no": f.line_no}
                        for f in order.findings
                        if f.disposition.kind is DispositionKind.ASK_CUSTOMER
                    ],
                }
            else:
                quote = (await stored_quote(work, case_id, viewer=context)).case
                status, customer_code, received = (
                    quote.status.value,
                    quote.request.customer_code,
                    quote.request.received_at,
                )
                facts = {"waiting_for": "spec_answer", "request_no": quote.request.reference}
            history = list(await work.overview.history(kind, case_id))
        if status != _WAITING[kind]:
            raise ConflictError(
                NOT_WAITING_ON_CUSTOMER,
                details={"case_id": str(case_id), "status": status, "rule": "not_waiting"},
            )
        customer = (await self.catalog.customer_by_code(scope, customer_code)).data
        if customer is None:
            raise NotFoundError("no such customer", details={"customer_code": customer_code})
        asked = local_time(asked_at(history, status, received)).date()
        today = local_time(self.clock.now()).date()
        base = {
            "case_id": case_id,
            "to": [c.address for c in customer.contacts],
            "asked_on": asked,
            "language": customer.language,
        }
        if self.model is None:
            return CustomerReminderView(**base, status="unavailable")
        written_facts = json.dumps(
            {
                "today": _day(today),
                "language": customer.language,
                "customer_name": customer.name,
                **facts,
                "asked_on": _day(asked),
                "days_waiting": (today - asked).days,
            },
            ensure_ascii=False,
            indent=1,
        )
        stamp = {
            **base,
            "prompt_ref": str(CUSTOMER_REMINDER),
            "model_profile": self.model.model_profile,
        }
        try:
            answer = await self.model.interpret(
                CUSTOMER_REMINDER,
                {"facts": written_facts},
                ModelFollowupMail,
                run=caller_run(
                    context,
                    run_id=self.ids.new_uuid(),
                    worker_id=self.worker_id,
                    worker_version=self.worker_version,
                    trace="sales-reminder",
                    subject_ref=f"{resource}:{case_id}",
                ),
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except (ModelUnavailableError, QuotaExceededError):
            return CustomerReminderView(**stamp, status="unavailable")
        written = f"{answer.subject}\n{answer.body}"
        if unsupported(written, written_facts) or names_amount(written):
            return CustomerReminderView(**stamp, status="refused")
        return CustomerReminderView(
            **stamp, status="drafted", subject=answer.subject, body=answer.body
        )


def _day(value: date) -> str:
    return value.strftime("%d/%m/%Y")

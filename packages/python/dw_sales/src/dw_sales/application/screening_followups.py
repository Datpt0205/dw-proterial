"""A mail asking the customer about a quotation nobody ordered, drafted by the
model (the AI list, item 11; WIV-03-023 step 12).

The screening (`QuotationService.screening`) lists each customer's item
quoted to them with no order of it in twelve months, for Sales to decide
whether the quotation stays. Deciding usually starts with asking the
customer, and that mail was written by hand each time. On request, the model
writes it, in the customer's language, from facts code gathers: the
customer's name, the item's code, the quotation numbers and how long each is
valid. **Never a price**: the question is whether they still need the item,
and an amount in a mail no approval looked at is a quotation by another name.

- Code checks every number, date and code in the subject and body is among
  the facts (`figure_check`), and that it names no amount at all (a percent
  sign, a currency code or symbol): a "5%" passes a figure check whenever a
  date holds a 5. Otherwise there is no draft.
- Code chooses the recipients: the customer's contacts in the master data.
- Nothing is sent and nothing is stored: the page opens the draft in the
  person's own mail program (`mailto:`), to read, change and send from their
  own mailbox. The decision on the quotation stays Sales'.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from dw_kernel.errors import NotFoundError, QuotaExceededError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.artifact_content import local_time
from dw_sales.application.figure_check import names_amount, unsupported
from dw_sales.application.model_reading import InterpretationPort, ModelUnavailableError, PromptRef
from dw_sales.application.ports import SalesCatalogPort
from dw_sales.application.quotation import QuotationService
from dw_sales.application.runs import caller_run

# The prompt the mail is drafted with. Its file is
# `configs/prompts/sales/screening_followup@1.0.0.yaml`; a test holds the two
# together, and the rendered prompt under `PROMPT_TOKENS`.
SCREENING_FOLLOWUP: Final = PromptRef("sales.screening_followup", "1.0.0")
PROMPT_TOKENS: Final = 900
_OUTPUT_TOKENS: Final = 700
_RESOURCE: Final = "sales_quote_screening"

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class ModelFollowupMail(BaseModel):
    """What the model writes: a subject and a body."""

    model_config = _FROZEN

    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=2500)


class FollowupDraftView(BaseModel):
    """A draft, or why there is none; always marked as the model's."""

    model_config = ConfigDict(frozen=True)

    customer_code: str
    prv_code: str
    status: Literal["drafted", "unavailable", "refused"]
    # The customer's contacts in the master data: code's choice, not the model's.
    to: list[str] = []
    subject: str | None = None
    body: str | None = None
    language: str | None = None
    prompt_ref: str | None = None
    model_profile: str | None = None


@dataclass(frozen=True)
class ScreeningFollowups:
    """`GET /quotes/screening/{customer}/{prv}/followup` (module docstring)."""

    gate: Gate
    catalog: SalesCatalogPort
    quotation: QuotationService
    model: InterpretationPort | None
    clock: UtcClock
    ids: IdGenerator
    worker_id: str
    worker_version: str

    async def draft(
        self, context: AccessContext, customer_code: str, prv_code: str
    ) -> FollowupDraftView:
        await self.gate.require(
            context,
            SalesScopes.QUOTE_PREPARE,
            resource_type=_RESOURCE,
            resource_id=f"{customer_code}:{prv_code}",
        )
        scope = sales_scope(context)
        day = local_time(self.clock.now()).date()
        row = next(
            (
                r
                for r in await self.quotation.screening(scope, day)
                if (r.customer_code, r.prv_code) == (customer_code, prv_code)
            ),
            None,
        )
        customer = (await self.catalog.customer_by_code(scope, customer_code)).data
        if row is None or customer is None:
            raise NotFoundError(
                "no such row in the screening",
                details={"customer_code": customer_code, "prv_code": prv_code},
            )
        to = [c.address for c in customer.contacts]
        base = {
            "customer_code": customer_code,
            "prv_code": prv_code,
            "to": to,
            "language": customer.language,
        }
        if self.model is None:
            return FollowupDraftView(**base, status="unavailable")
        valid = await self.catalog.quotations_valid_on(scope, customer_code, prv_code, day)
        facts = json.dumps(
            {
                "today": day.isoformat(),
                "language": customer.language,
                "customer_name": customer.name,
                "item_code": prv_code,
                "quotations": [
                    {
                        "quote_no": q.quote_no,
                        "valid_from": _day(q.valid_from),
                        "valid_to": _day(q.valid_to),
                    }
                    for q in valid.data
                    if q.quote_no in row.quote_nos
                ],
                "months_without_order": 12,
            },
            ensure_ascii=False,
            indent=1,
        )
        stamp = {
            **base,
            "prompt_ref": str(SCREENING_FOLLOWUP),
            "model_profile": self.model.model_profile,
        }
        try:
            answer = await self.model.interpret(
                SCREENING_FOLLOWUP,
                {"facts": facts},
                ModelFollowupMail,
                run=caller_run(
                    context,
                    run_id=self.ids.new_uuid(),
                    worker_id=self.worker_id,
                    worker_version=self.worker_version,
                    trace="sales-screening",
                    subject_ref=f"{_RESOURCE}:{customer_code}:{prv_code}",
                ),
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except (ModelUnavailableError, QuotaExceededError):
            return FollowupDraftView(**stamp, status="unavailable")
        written = f"{answer.subject}\n{answer.body}"
        if unsupported(written, facts) or names_amount(written):
            return FollowupDraftView(**stamp, status="refused")
        return FollowupDraftView(
            **stamp, status="drafted", subject=answer.subject, body=answer.body
        )


def _day(value: date) -> str:
    return value.strftime("%d/%m/%Y")

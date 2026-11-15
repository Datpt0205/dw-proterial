"""A mail to a customer about an order, worded by the model beside the
template's draft (ticket 32; dw_sales ADR 0012 decision 2, ADR 0010
decision 3, ADR 0011).

Four kinds, each the order's own (`ReplyKind`):

- **an answer to a question**: a customer's reply in the order's thread that
  the thread-intent reading found `asks` in (ticket 26). There is no template
  draft of it: the model's wording is the only draft, or there is none.
- **6-DW4 and 6-DW3**, PC's answer to a customer's change (ticket 29), and
  **the confirmation** (ticket 28, 6.3 when the update loop sends it again):
  offered while the template draft of the same kind is (`ORDER_GATES`, the
  one owner of when), and never in its place. The template path is the one
  that works with this step off.

How it is worded and checked, as every model-worded mail in Sales is
(`customer_reminders`, `screening_followups`):

- **Code writes every fact** (`reply_facts`): the PO's numbers, the lines,
  their quantities and dates, the people named; the same values the template
  fills, in the customer's language's date format. **Never an amount**: no
  unit price, total, currency or percentage is a fact of any kind, the
  confirmation's included, whose prices reach the customer only in the
  template's draft and its Excel, drawn by `sales.price.read`. A customer's
  question about a price is a person's to answer.
- **The tenant's letter is the example** (`sales_emails`, through
  `ArtifactCopyPort`, its values left as placeholders), for the tone and the
  sign-off; the question is the sentences code located (`ReadIntent.quotes`).
  Both, like the facts, reach the prompt as data.
- **One call, no tools.** Every figure the draft may state is a fact code
  gathered, and the check reads the facts alone: a figure a tool found would
  be refused anyway, so a turn with tools would add calls and nothing the
  draft could say (ADR 0012, "Applied to ticket 32").
- **The check** (`check_reply`): every number, date and code of the subject
  and body is among the facts (`figure_check`; a figure in the question is
  not a fact), no amount is named, and no address or link is written (the
  recipients are code's). A draft that fails is dropped, with why; the person
  has the template's draft, or nothing.
- **Recipients are code's**: the customer's contacts in master data, as every
  customer draft's (`Drafting.customer_email`). The model's answer has no
  field for one. A person sends it; nothing is sent or stored.
- **Gated** as every model step (`ModelStep.REPLY_DRAFT`, the switch
  `model_assist.reply_draft`, off in every platform version, and its live
  eval at the bar). Off, unmeasured or with no model, the view says so.

Only a holder of `sales.order.prepare`, on an order of the caller's
workspace (another tenant's is not found).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final, Literal, get_args

from pydantic import BaseModel, ConfigDict

from dw_agent_runtime.context import caller_run
from dw_agent_runtime.model.figure_check import figures, names_amount, unsupported
from dw_agent_runtime.model.interpretation import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    estimated_tokens,
)
from dw_kernel.errors import ConflictError, DomainError, NotFoundError, QuotaExceededError
from dw_kernel.ports import IdGenerator
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.artifact_content import day_text
from dw_sales.application.artifacts_service import ORDER_GATES
from dw_sales.application.case_store import SalesUnitOfWork, SalesUnitOfWorkFactory
from dw_sales.application.drafting import MOCK_COPY, ArtifactCopyPort, People
from dw_sales.application.order_ports import ModelStepGatePort, OrderRulesPort
from dw_sales.application.ports import MemberDirectoryPort, SalesCatalogPort, SalesScope
from dw_sales.application.screening_followups import ModelFollowupMail
from dw_sales.application.support import stored_order
from dw_sales.domain.catalog import Customer, Language
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.orders import OrderCase, OrderLine
from dw_sales.domain.process import DW_NAMES

_LOG = logging.getLogger(__name__)

# The prompt a reply is worded with. Its file is
# `configs/prompts/sales/reply_draft@1.0.0.yaml`; a test holds the two
# together, and the rendered prompt under `PROMPT_TOKENS`.
REPLY_DRAFT: Final = PromptRef("sales.reply_draft", "1.0.0")
PROMPT_TOKENS: Final = 1400
_OUTPUT_TOKENS: Final = 900
_ORDER: Final = "sales_order_case"

ReplyKind = Literal[
    "question_answer", "change_can_do_draft", "change_options_draft", "confirmation_draft"
]
REPLY_KINDS: Final[tuple[ReplyKind, ...]] = get_args(ReplyKind)
QUESTION: Final = "question_answer"
# Why code dropped a draft: a figure no fact holds, an amount, an address or
# a link.
Refusal = Literal["figure", "amount", "address"]
ReplyStatus = Literal["drafted", "refused", "unavailable", "off"]

# An address or a link, in any language's mail: never the model's to write,
# since who receives the mail is code's.
_ADDRESS: Final = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+|https?://|\bwww\.", re.IGNORECASE)


class ReplyDraftView(BaseModel):
    """The model's wording, or why there is none; always marked as the model's
    on the page, beside the template's draft of ``kind`` where it has one."""

    model_config = ConfigDict(frozen=True)

    case_id: uuid.UUID
    kind: ReplyKind
    status: ReplyStatus
    # The customer's contacts in the master data: code's choice, not the model's.
    to: list[str] = []
    language: str
    # Code's check of a refused draft: why, and the figures no fact holds.
    refusal: Refusal | None = None
    unsupported: list[str] = []
    # A drafted mail: how many figures it writes, each one a fact.
    figures_checked: int = 0
    subject: str | None = None
    body: str | None = None
    prompt_ref: str | None = None
    model_profile: str | None = None


@dataclass(frozen=True, slots=True)
class ReplyCheck:
    """What code makes of a worded mail: None when it may be shown."""

    refusal: Refusal | None
    unsupported: tuple[str, ...] = ()
    figures: int = 0


def check_reply(written: str, facts: str) -> ReplyCheck:
    """Whether ``written`` (subject and body) may reach a person: every figure
    among ``facts``, no amount, no address or link."""
    missing = unsupported(written, facts, names=DW_NAMES)
    if missing:
        return ReplyCheck("figure", tuple(sorted(missing)))
    if names_amount(written):
        return ReplyCheck("amount")
    if _ADDRESS.search(written):
        return ReplyCheck("address")
    return ReplyCheck(None, figures=len(figures(written) - DW_NAMES))


def reply_facts(
    kind: ReplyKind, case: OrderCase, customer: Customer, people: People
) -> dict[str, object]:
    """The facts of ``kind``, the only figures its wording may state: the
    values its template fills, without a price, an amount or a currency."""
    language = customer.language
    header = case.effective_header
    facts: dict[str, object] = {
        "reply": kind,
        "language": language,
        "customer_name": customer.name,
        "po_no": header.po_no,
        "revision": header.revision,
        "po_date": day_text(header.po_date, language),
        "bravo_so_no": case.bravo_so_no,
    }
    if kind == QUESTION:
        facts["order_status"] = case.status.value
        facts["lines"] = [_line_facts(line, language) for line in case.lines]
    elif kind == "confirmation_draft":
        facts["lines"] = [
            {
                "line_no": line.line_no,
                "customer_item_code": line.effective.customer_item_code,
                "prv_code": line.mapping.prv_code,
                "description": line.effective.description,
                "quantity": str(line.effective.quantity),
                "uom": line.effective.uom,
                "confirmed": _deliveries(line.confirmed_deliveries(), line, language),
            }
            for line in case.lines
        ]
        facts["prepared_by"] = None if case.prepared_by is None else people.name(case.prepared_by)
        facts["checked_by"] = (
            None if case.cross_checked_by is None else people.name(case.cross_checked_by)
        )
    else:
        facts["lines"] = _change_facts(case, language, asked=kind == "change_options_draft")
    return {name: value for name, value in facts.items() if value is not None}


def _line_facts(line: OrderLine, language: Language) -> dict[str, object]:
    po = line.effective
    facts: dict[str, object] = {
        "line_no": line.line_no,
        "customer_item_code": po.customer_item_code,
        "quantity": str(po.quantity),
        "uom": po.uom,
    }
    if po.requested_date is not None:
        facts["requested_date"] = day_text(po.requested_date, language)
    if line.confirmed_delivery_dates:
        facts["confirmed"] = _deliveries(line.confirmed_deliveries(), line, language)
    return facts


def _deliveries(
    deliveries: Sequence[tuple[Decimal, date]], line: OrderLine, language: Language
) -> list[dict[str, str]]:
    return [
        {"quantity": str(quantity), "uom": line.effective.uom, "date": day_text(day, language)}
        for quantity, day in deliveries
    ]


def _change_facts(case: OrderCase, language: Language, *, asked: bool) -> list[dict[str, object]]:
    """Each changed line with PC's deliveries, and what was asked where the
    template says it (6-DW3), as `order_artifacts._change_answer` fills them."""
    loop = case.update_loop
    assert loop is not None  # offered on the loop only (ORDER_GATES)
    lines: list[dict[str, object]] = []
    for held in loop.lines:
        target = case.loop_target(held)
        assert held.pc_answer is not None  # offered once PC answered every line
        line: dict[str, object] = {
            "line_no": held.line_no,
            "customer_item_code": target.customer_item_code,
            "deliveries": [
                {
                    "quantity": str(delivery.quantity),
                    "uom": target.uom,
                    "date": day_text(delivery.date, language),
                }
                for delivery in held.pc_answer.deliveries
            ],
        }
        if asked:
            line["asked"] = {
                "quantity": str(target.quantity),
                "uom": target.uom,
                **(
                    {"date": day_text(target.requested_date, language)}
                    if target.requested_date is not None
                    else {}
                ),
            }
        lines.append(line)
    return lines


def _example(subject: str, body: str) -> str:
    """The tenant's letter of the kind, its placeholders kept. Its line
    template is left out: the lines are the facts', and the confirmation's
    line names a price no fact carries."""
    return f"Subject: {subject}\n\n{body}"


@dataclass(frozen=True)
class ReplyDrafts:
    """`GET /orders/{case_id}/reply-draft` (module docstring)."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    catalog: SalesCatalogPort
    directory: MemberDirectoryPort
    # The tenant's mail copy: each kind's letter is the model's example.
    copy: ArtifactCopyPort
    rules: OrderRulesPort
    # Whether the step may run for the tenant now; None: never.
    model_steps: ModelStepGatePort | None
    model: InterpretationPort | None
    ids: IdGenerator
    worker_id: str
    worker_version: str
    # Where deployed, no example is read from copy marked mock (audit 11).
    deployed: bool = False

    async def draft(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        kind: ReplyKind,
        *,
        message_id: str | None = None,
    ) -> ReplyDraftView:
        if (kind == QUESTION) != (message_id is not None):
            raise DomainError(
                "an answer names the customer's mail, and only an answer does",
                details={"field": "message_id", "kind": kind},
            )
        await self.gate.require(
            context, SalesScopes.ORDER_PREPARE, resource_type=_ORDER, resource_id=str(case_id)
        )
        scope = sales_scope(context)
        question: tuple[str, ...] = ()
        async with self.uow(scope) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            if message_id is not None:
                question = await _asked(work, case_id, message_id)
        customer = (await self.catalog.customer_by_code(scope, case.customer_code)).data
        if customer is None:
            raise NotFoundError("no such customer", details={"customer_code": case.customer_code})
        template = ORDER_GATES.get(kind)
        if template is not None and not (
            template.open_in(case, context, self.gate)
            and template.channel in (None, customer.confirmation_channel)
        ):
            raise ConflictError(
                "this draft is not offered in the order's current state",
                details={"kind": kind, "status": case.status.value, "rule": "not_offered"},
            )
        base = {
            "case_id": case_id,
            "kind": kind,
            "to": [c.address for c in customer.contacts],
            "language": customer.language,
        }
        if not await self._on(scope):
            return ReplyDraftView(**base, status="off")
        if self.model is None:
            return ReplyDraftView(**base, status="unavailable")
        copy = (await self.copy.artifact_copy(scope, ())).emails
        if self.deployed and copy.mock:
            raise ConflictError(
                MOCK_COPY.format(ref=copy.ref), details={"copy": copy.ref, "rule": "mock_copy"}
            )
        letter = copy.template(kind, customer.language).template
        people = People({m.user_id: m for m in await self.directory.list_members(context)})
        facts = json.dumps(reply_facts(kind, case, customer, people), ensure_ascii=False, indent=1)
        inputs = {
            "facts": facts,
            "example": _example(letter.subject, letter.body),
            "question": "\n".join(question),
        }
        stamp = {
            **base,
            "prompt_ref": str(REPLY_DRAFT),
            "model_profile": self.model.model_profile,
        }
        if estimated_tokens("".join(inputs.values())) > self.model.max_input_tokens - PROMPT_TOKENS:
            return ReplyDraftView(**stamp, status="unavailable")
        try:
            answer = await self.model.interpret(
                REPLY_DRAFT,
                inputs,
                ModelFollowupMail,
                run=caller_run(
                    context,
                    run_id=self.ids.new_uuid(),
                    worker_id=self.worker_id,
                    worker_version=self.worker_version,
                    trace="sales-reply-draft",
                    subject_ref=f"{_ORDER}:{case_id}",
                ),
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except (ModelUnavailableError, QuotaExceededError):
            return ReplyDraftView(**stamp, status="unavailable")
        check = check_reply(f"{answer.subject}\n{answer.body}", facts)
        if check.refusal is not None:
            # Ids, the kind and why: never a figure the model wrote.
            _LOG.info(
                "reply draft dropped",
                extra={"case_id": str(case_id), "kind": kind, "refusal": check.refusal},
            )
            return ReplyDraftView(
                **stamp,
                status="refused",
                refusal=check.refusal,
                unsupported=list(check.unsupported),
            )
        return ReplyDraftView(
            **stamp,
            status="drafted",
            subject=answer.subject,
            body=answer.body,
            figures_checked=check.figures,
        )

    async def _on(self, scope: SalesScope) -> bool:
        """The step on in the tenant's rules in force and measured at its bar;
        never without the gate."""
        if self.model_steps is None:
            return False
        rules = await self.rules.rules(scope)
        return await self.model_steps.allows(scope, rules, ModelStep.REPLY_DRAFT)


async def _asked(work: SalesUnitOfWork, case_id: uuid.UUID, message_id: str) -> tuple[str, ...]:
    """The sentences of a customer's reply on this order that its reading
    found to ask something: any other mail, another order's or another
    customer's, is not found here; a reply with no question is refused."""
    logged = await work.messages.get(message_id)
    if (
        logged is None
        or logged.reply is None
        or logged.case_kind is not CaseKind.ORDER
        or logged.case_id != case_id
    ):
        raise NotFoundError("no such reply on this order", details={"message_id": message_id})
    reading = logged.reply.reading
    quotes = [] if reading is None else [i.quotes for i in reading.intents if i.intent == "asks"]
    if not quotes:
        raise ConflictError(
            "the customer's mail was not read as a question",
            details={"message_id": message_id, "rule": "not_asked"},
        )
    return tuple(quote.text for found in quotes for quote in found)

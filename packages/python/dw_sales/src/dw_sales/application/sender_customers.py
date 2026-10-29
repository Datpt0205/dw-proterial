"""Whose mail is this: a customer suggested for a sender no domain matched
(the AI list, item 5).

A mail from an address on no customer's domain (a buyer writing from a new
domain, a personal address, a subsidiary's) is routed `customer_unknown`, and
a person had to work out from the signature which customer wrote it, then ask
someone to add the domain to the master data. Đạt, 2026-10-29: the model does
the reading, code only checks.

- **Code narrows**: the candidates are the customers one of whose
  *distinctive* name words (held by no other customer's name: "brennic", not
  "vietnam") appears in the mail's sender, subject or newest part. None: the
  model is still asked which company the mail names, so Sales sees it.
- **The model judges** which candidate, if any, wrote the mail (a mail that
  only *mentions* a customer is not from it), and copies the words naming
  the company.
- **Code checks** the answer: the customer is a candidate, the words are in
  the mail as written, and they hold a distinctive word of that customer's
  name. Anything else is no suggestion.
- **Sales confirms** (`confirm`): the sender's address is recorded as that
  customer's (`SenderLedgerPort`; the address, never the domain, which may be
  a public mail provider's), and the message is queued to be processed again,
  now with its customer. Nothing is decided by the model.

Each suggestion is one call through the one-call door, as the caller (their
plan's allowance); nothing is stored but the confirmation.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from dw_kernel.errors import ConflictError, NotFoundError, QuotaExceededError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.model_reading import InterpretationPort, ModelUnavailableError, PromptRef
from dw_sales.application.ports import InboxPort, SalesCatalogPort, SalesScope
from dw_sales.application.runs import caller_run
from dw_sales.application.views import ProcessingJobView
from dw_sales.domain.catalog import Customer
from dw_sales.domain.dispositions import DispositionKind, RoutingReason
from dw_sales.domain.mail_parts import newest_part
from dw_sales.domain.messages import InboundMessage

# The prompt the sender's company is read with. Its file is
# `configs/prompts/sales/sender_customer@1.0.0.yaml`; a test holds the two
# together, and the rendered prompt under `PROMPT_TOKENS`.
SENDER_CUSTOMER: Final = PromptRef("sales.sender_customer", "1.0.0")
PROMPT_TOKENS: Final = 900
_OUTPUT_TOKENS: Final = 200
# The most candidates the model is shown; more means the mail's words name
# too many customers to tell, and it is asked only which company it names.
MAX_CANDIDATES: Final = 8
# The mail as the model reads it, at most this many characters.
_MAIL_CHARS: Final = 4000
_RESOURCE: Final = "sales_message"
_WORD = re.compile(r"[a-z0-9]{3,}")

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class ModelSenderCustomer(BaseModel):
    """What the model answers: the candidate that wrote the mail, and the
    words naming the company as the mail writes them."""

    model_config = _FROZEN

    customer_code: str | None = Field(default=None, max_length=16)
    company: str | None = Field(default=None, max_length=200)


class SenderCustomerView(BaseModel):
    """A suggestion, or why there is none; always marked as the model's."""

    model_config = ConfigDict(frozen=True)

    message_id: str
    sender: str
    status: Literal["suggested", "no_match", "unavailable"]
    customer_code: str | None = None
    customer_name: str | None = None
    # The words in the mail the suggestion rests on, as the mail writes them.
    evidence: str | None = None
    prompt_ref: str | None = None
    model_profile: str | None = None


class SenderLedgerPort(Protocol):
    """Where a sender Sales confirmed as a customer's is kept
    (`SnapshotSalesCatalog.learn_sender`)."""

    async def learn_sender(
        self, scope: SalesScope, address: str, customer_code: str, *, by: uuid.UUID, message_id: str
    ) -> bool: ...


class ProcessingQueuePort(Protocol):
    """Queues a message to be processed again (`ProcessingService.enqueue`)."""

    async def enqueue(self, context: AccessContext, message_id: str) -> ProcessingJobView: ...


def folded(text: str) -> str:
    """Lowercase, without accents (``đ`` as ``d``): how a name is compared."""
    decomposed = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def words(text: str) -> set[str]:
    return set(_WORD.findall(folded(text)))


def distinctive_words(customers: Sequence[Customer]) -> dict[str, set[str]]:
    """Per customer code, the words of its name no other customer's name has."""
    named = {c.code: words(c.name) for c in customers}
    return {
        code: {w for w in own if not any(w in other for o, other in named.items() if o != code)}
        for code, own in named.items()
    }


def mail_text(message: InboundMessage) -> str:
    """The sender, the subject and the newest part: what the model reads and
    the evidence must be in."""
    sender = message.sender
    return f"From: {sender.display_name} <{sender.address}>\n{newest_part(message).text}"[
        :_MAIL_CHARS
    ]


def candidates(customers: Sequence[Customer], text: str) -> list[Customer]:
    """The customers a distinctive word of whose name the mail holds."""
    held = words(text)
    own = distinctive_words(customers)
    return [c for c in customers if own[c.code] & held]


def supports(customer: Customer, evidence: str, text: str, own: set[str]) -> bool:
    """Whether the words are in the mail and name this customer distinctively."""
    flat = " ".join(folded(evidence).split())
    return bool(flat) and flat in " ".join(folded(text).split()) and bool(words(evidence) & own)


@dataclass(frozen=True)
class SenderCustomers:
    """`GET|POST /inbox/{message_id}/customer` (module docstring)."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    inbox: InboxPort
    catalog: SalesCatalogPort
    ledger: SenderLedgerPort
    processing: ProcessingQueuePort
    model: InterpretationPort | None
    clock: UtcClock
    ids: IdGenerator
    worker_id: str
    worker_version: str

    async def suggest(self, context: AccessContext, message_id: str) -> SenderCustomerView:
        scope = sales_scope(context)
        message = await self._unknown(context, scope, message_id)
        sender = message.sender.address.lower()
        if self.model is None:
            return SenderCustomerView(message_id=message_id, sender=sender, status="unavailable")
        customers = (await self.catalog.customers(scope)).data
        text = mail_text(message)
        found = candidates(customers, text)
        shown = found if len(found) <= MAX_CANDIDATES else []
        listed = "\n".join(f"{c.code}: {c.name}" for c in shown) or "(none)"
        stamp = {
            "message_id": message_id,
            "sender": sender,
            "prompt_ref": str(SENDER_CUSTOMER),
            "model_profile": self.model.model_profile,
        }
        try:
            answer = await self.model.interpret(
                SENDER_CUSTOMER,
                {"mail": text, "candidates": listed},
                ModelSenderCustomer,
                run=caller_run(
                    context,
                    run_id=self.ids.new_uuid(),
                    worker_id=self.worker_id,
                    worker_version=self.worker_version,
                    trace="sales-sender",
                    subject_ref=f"{_RESOURCE}:{message_id}",
                ),
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except (ModelUnavailableError, QuotaExceededError):
            return SenderCustomerView(**stamp, status="unavailable")
        chosen = next((c for c in shown if c.code == answer.customer_code), None)
        evidence = (answer.company or "").strip()
        if chosen is not None and supports(
            chosen, evidence, text, distinctive_words(customers)[chosen.code]
        ):
            return SenderCustomerView(
                **stamp,
                status="suggested",
                customer_code=chosen.code,
                customer_name=chosen.name,
                evidence=evidence,
            )
        # The company the mail names, when it is in the mail: a new customer,
        # perhaps. Never a customer the check did not hold.
        named = evidence if evidence and folded(evidence) in folded(text) else None
        return SenderCustomerView(**stamp, status="no_match", evidence=named)

    async def confirm(
        self, context: AccessContext, message_id: str, customer_code: str
    ) -> ProcessingJobView:
        """The sender recorded as ``customer_code``'s, and the message queued
        to be processed again with it."""
        scope = sales_scope(context)
        message = await self._unknown(context, scope, message_id)
        customer = (await self.catalog.customer_by_code(scope, customer_code)).data
        if customer is None:
            raise NotFoundError("no such customer", details={"customer_code": customer_code})
        sender = message.sender.address.lower()
        async with self.uow(scope) as work:
            await work.audit.append(
                AuditEvent(
                    id=self.ids.new_uuid(),
                    tenant_id=TenantId(context.tenant_id),
                    workspace_id=WorkspaceId(context.workspace_id),
                    actor_id=UserId(context.principal_id),
                    action="sales.message.customer_confirmed",
                    resource_type=_RESOURCE,
                    resource_id=message_id,
                    occurred_at=self.clock.now(),
                    details={"customer_code": customer.code},
                )
            )
            await work.commit()
        await self.ledger.learn_sender(
            scope, sender, customer.code, by=context.principal_id, message_id=message_id
        )
        return await self.processing.enqueue(context, message_id)

    async def _unknown(
        self, context: AccessContext, scope: SalesScope, message_id: str
    ) -> InboundMessage:
        """The message, after checking the caller may process it and that it
        was routed for want of a customer: 404, 403 or 409 otherwise."""
        await self.gate.require(
            context, SalesScopes.INBOX_PROCESS, resource_type=_RESOURCE, resource_id=message_id
        )
        message = await self.inbox.get_message(scope, message_id)
        async with self.uow(scope) as work:
            logged = await work.messages.get(message_id)
        if message is None or logged is None:
            raise NotFoundError("no such message", details={"message_id": message_id})
        if (
            logged.kind is not DispositionKind.ROUTED_TO_SALES
            or logged.reason is not RoutingReason.CUSTOMER_UNKNOWN
        ):
            raise ConflictError(
                "only a message routed for want of a customer is matched to one",
                details={"message_id": message_id, "rule": "message_not_customer_unknown"},
            )
        return message

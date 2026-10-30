"""Design's reply written in the mail itself, read by the model (the AI list,
item 6; WIV-03-023 step 4).

Design answers a YCBG with its reply form; when it writes the answer in the
mail instead ("Line 1: BP-2210-07, spec SP-2210-07, PRV CB-2006, 38.4 kg/km"),
no reader took it and Sales retyped it. Such a mail, from a Design mailbox
the mail system verified, is routed `design_reply_unmatched` ("written in the
mail"); when Sales opens it, the model reads the mail's newest part into the
reply's fields, each copied exactly as the mail writes it (one call through
the one-call door, as the caller).

- **Code checks** each value: it is found in the mail's newest part, where
  its anchor points (characters into that text, with its digest), and it
  parses into the field's own type (a BP code, a spec number, a PRV code, a
  copper weight). One value that fails and there is no reading.
- **Code matches** the reply to its case exactly as a form's is matched
  (`QuotationService.awaiting_reply`: the YCBG number, the one case waiting
  on Design under it, every requested line answered).
- **A person confirms** before anything reaches the case: the values come
  back with the press and are checked against the mail again, exactly as
  the model's were, so nothing typed in a browser can attach a value the
  mail does not hold. The case records who confirmed (`DesignReply.confirmed_by`).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dw_kernel.errors import ConflictError, NotFoundError, QuotaExceededError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.model_reading import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    estimated_tokens,
)
from dw_sales.application.ports import InboxPort, SalesScope
from dw_sales.application.quotation import QuotationService
from dw_sales.application.runs import caller_run
from dw_sales.application.support import person_event, save_quote
from dw_sales.application.views import CaseChangeView, quote_change
from dw_sales.domain.anchors import MessageText, SourceAnchor, TextRange
from dw_sales.domain.dispositions import (
    CaseKind,
    DispositionKind,
    MessageDisposition,
    RoutingReason,
)
from dw_sales.domain.mail_parts import newest_part
from dw_sales.domain.messages import InboundMessage
from dw_sales.domain.quotes import DesignReply, DesignReplyDocument
from dw_sales.domain.rfq_reading import normalised, text_digest

# The prompt the reply is read with. Its file is
# `configs/prompts/sales/design_text_reply@1.0.0.yaml`; a test holds the two
# together, and the rendered prompt under `PROMPT_TOKENS`.
DESIGN_TEXT_REPLY: Final = PromptRef("sales.design_text_reply", "1.0.0")
PROMPT_TOKENS: Final = 900
_OUTPUT_TOKENS: Final = 800
_RESOURCE: Final = "sales_message"
# A copper weight as a mail states one: a number and kg per km.
_WEIGHT: Final = re.compile(r"\d+(?:[.,]\d+)?\s*kg\s*(?:/|per|trên|mỗi)\s*km", re.IGNORECASE)

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class ModelReplyLine(BaseModel):
    model_config = _FROZEN

    line_no: int = Field(ge=1, le=200)
    bp_code: str = Field(min_length=1, max_length=40)
    spec_no: str = Field(min_length=1, max_length=40)
    prv_code: str | None = Field(default=None, max_length=40)
    copper_kg_per_km: str | None = Field(default=None, max_length=20)


class ModelDesignReply(BaseModel):
    """What the model reads, and what Sales confirms: the YCBG answered and
    each line, every value as the mail writes it."""

    model_config = _FROZEN

    ycbg_no: str = Field(min_length=1, max_length=40)
    lines: list[ModelReplyLine] = Field(min_length=1, max_length=50)


class _UnanchoredError(Exception):
    """A value the mail does not hold as written."""


def _anchor(text: str, digest: str, value: str) -> SourceAnchor:
    start = text.find(value)
    if not value or start < 0:
        raise _UnanchoredError(value)
    return SourceAnchor(
        attachment_id=None,
        attachment_sha256=digest,
        quote=value[:500],
        chars=TextRange(start=start, end=start + len(value)),
    )


def _sourced(text: str, digest: str, value: str | None) -> dict[str, object] | None:
    return None if value is None else {"value": value, "source": _anchor(text, digest, value)}


def verified(answer: ModelDesignReply, body: str, received: date) -> DesignReplyDocument | None:
    """The answer as a reply document when every value is in ``body`` as
    written and parses into its field; None otherwise. The reply's date is
    the mail's, anchored at the YCBG number it answers.

    A mail stating more copper weights than the reply has lines is
    ambiguous, and is no reading: the live eval caught a model taking the
    weight a sentence told it to report over the line's own (2026-10-29), a
    value the mail does hold, so finding it there proves nothing."""
    weights = len(_WEIGHT.findall(body))
    if any(line.copper_kg_per_km is not None for line in answer.lines) and weights > len(
        answer.lines
    ):
        return None
    digest = text_digest(body)
    try:
        ycbg = _anchor(body, digest, answer.ycbg_no)
        lines = []
        for line in answer.lines:
            copper = None
            if line.copper_kg_per_km is not None:
                copper = {
                    "value": Decimal(line.copper_kg_per_km.replace(",", ".")),
                    "source": _anchor(body, digest, line.copper_kg_per_km),
                }
            lines.append(
                {
                    "line_no": line.line_no,
                    "bp_code": _sourced(body, digest, line.bp_code),
                    "spec_no": _sourced(body, digest, line.spec_no),
                    "prv_code": _sourced(body, digest, line.prv_code),
                    "copper_kg_per_km": copper,
                }
            )
        return DesignReplyDocument.model_validate(
            {
                "ycbg_no": {"value": answer.ycbg_no, "source": ycbg},
                "reply_date": {"value": received, "source": ycbg},
                "lines": lines,
            }
        )
    except (_UnanchoredError, InvalidOperation, ValidationError, ValueError):
        return None


class DesignTextLineView(BaseModel):
    model_config = ConfigDict(frozen=True)

    line_no: int
    bp_code: str
    spec_no: str
    prv_code: str | None
    copper_kg_per_km: str | None


class DesignTextReadingView(BaseModel):
    """What DW1 read of a Design reply written in the mail, for Sales to
    confirm; always marked as the model's."""

    model_config = ConfigDict(frozen=True)

    message_id: str
    status: Literal["read", "no_case", "unavailable"]
    ycbg_no: str | None = None
    # The case it would be attached to: the one waiting on Design under it.
    case_id: uuid.UUID | None = None
    lines: list[DesignTextLineView] = []
    prompt_ref: str | None = None
    model_profile: str | None = None


def _lines(answer: ModelDesignReply) -> list[DesignTextLineView]:
    return [
        DesignTextLineView(
            line_no=line.line_no,
            bp_code=line.bp_code,
            spec_no=line.spec_no,
            prv_code=line.prv_code,
            copper_kg_per_km=line.copper_kg_per_km,
        )
        for line in sorted(answer.lines, key=lambda line: line.line_no)
    ]


def _body(message: InboundMessage) -> str:
    return normalised(newest_part(message).text)


@dataclass(frozen=True)
class DesignTextReplies:
    """`GET|POST /inbox/{message_id}/design-reply` (module docstring)."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    inbox: InboxPort
    quotation: QuotationService
    model: InterpretationPort | None
    clock: UtcClock
    ids: IdGenerator
    worker_id: str
    worker_version: str

    async def read(self, context: AccessContext, message_id: str) -> DesignTextReadingView:
        scope = sales_scope(context)
        message = await self._design_mail(context, scope, message_id)
        if self.model is None:
            return DesignTextReadingView(message_id=message_id, status="unavailable")
        body = _body(message)
        stamp = {
            "message_id": message_id,
            "prompt_ref": str(DESIGN_TEXT_REPLY),
            "model_profile": self.model.model_profile,
        }
        if not body.strip() or estimated_tokens(body) > self.model.max_input_tokens - PROMPT_TOKENS:
            return DesignTextReadingView(**stamp, status="unavailable")
        try:
            answer = await self.model.interpret(
                DESIGN_TEXT_REPLY,
                {"mail": body},
                ModelDesignReply,
                run=caller_run(
                    context,
                    run_id=self.ids.new_uuid(),
                    worker_id=self.worker_id,
                    worker_version=self.worker_version,
                    trace="sales-design-text",
                    subject_ref=f"{_RESOURCE}:{message_id}",
                ),
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except (ModelUnavailableError, QuotaExceededError):
            return DesignTextReadingView(**stamp, status="unavailable")
        document = verified(answer, body, message.received_at.date())
        if document is None:
            return DesignTextReadingView(**stamp, status="unavailable")
        case = await self.quotation.awaiting_reply(scope, document)
        if isinstance(case, str):
            return DesignTextReadingView(**stamp, status="no_case", ycbg_no=answer.ycbg_no)
        return DesignTextReadingView(
            **stamp,
            status="read",
            ycbg_no=answer.ycbg_no,
            case_id=case.case_id,
            lines=_lines(answer),
        )

    async def confirm(
        self, context: AccessContext, message_id: str, values: ModelDesignReply
    ) -> CaseChangeView:
        """The reply as Sales confirmed it, attached to its case: every value
        checked against the mail again, the case matched again."""
        scope = sales_scope(context)
        message = await self._design_mail(context, scope, message_id)
        body = _body(message)
        document = verified(values, body, message.received_at.date())
        if document is None:
            raise ConflictError(
                "một giá trị không có trong thư của Design: đọc lại thư rồi xác nhận",
                details={"rule": "value_not_in_mail", "message_id": message_id},
            )
        case = await self.quotation.awaiting_reply(scope, document)
        if isinstance(case, str):
            raise ConflictError(
                "không có hồ sơ nào đang chờ Design dưới số YCBG này, "
                "hoặc thư không trả lời đủ các dòng của hồ sơ",
                details={"rule": case, "message_id": message_id},
            )
        now = self.clock.now()
        reply = DesignReply(
            message_id=message_id,
            received_at=message.received_at,
            document=document,
            body=MessageText(text=body, sha256=text_digest(body)),
            confirmed_by=context.principal_id,
        )
        async with self.uow(scope) as work:
            stored = await work.quotes.get(case.case_id)
            if stored is None:
                raise NotFoundError("no such quote case", details={"case_id": str(case.case_id)})
            replied = stored.case.record_design_reply(reply)
            event = person_event("quote.design_replied", context, now)
            await save_quote(work, context, self.ids, stored.case, replied, event)
            await work.messages.record(
                MessageDisposition(
                    message_id=message_id,
                    kind=DispositionKind.ATTACHED_TO_CASE,
                    case_kind=CaseKind.QUOTE,
                    case_id=replied.case_id,
                    customer_code=replied.customer_code,
                ),
                now,
            )
            await work.commit()
        return quote_change(replied)

    async def _design_mail(
        self, context: AccessContext, scope: SalesScope, message_id: str
    ) -> InboundMessage:
        """The message, after checking the caller prepares quotations, that it
        was routed as a Design reply no case took, and that a verified Design
        mailbox sent it: 404, 403 or 409 otherwise."""
        await self.gate.require(
            context, SalesScopes.QUOTE_PREPARE, resource_type=_RESOURCE, resource_id=message_id
        )
        message = await self.inbox.get_message(scope, message_id)
        async with self.uow(scope) as work:
            logged = await work.messages.get(message_id)
        if message is None or logged is None:
            raise NotFoundError("no such message", details={"message_id": message_id})
        if logged.reason is not RoutingReason.DESIGN_REPLY_UNMATCHED or not (
            await self.quotation.from_design(scope, message)
        ):
            raise ConflictError(
                "chỉ thư Design chưa gắn vào hồ sơ mới được đọc theo cách này",
                details={"rule": "not_a_design_mail", "message_id": message_id},
            )
        return message

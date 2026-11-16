"""The platform's example mails a proposed skill version is replayed on
(ticket 40, `application.skill_replay`), read from the eval fixtures the
worker image ships (`infra/docker/worker.Dockerfile` copies `evals/fixtures`).

- The golden replies of `sales_reply@2.0.0`
  (`evals/fixtures/cases/sales_reply_golden.json`): fictional mails in
  Vietnamese, English and Japanese, each on one case with the intents it is
  read as; the ones tagged ``conditional`` or ``non_answer`` are also security
  cases (never ``accepts``).
- The thread agent's injections
  (`evals/fixtures/cases/sales_thread_agent_security.json`): mails that ask
  the reader to accept, to look up another customer or to break its rules,
  security cases only.

Each case is bound as the eval binds it: its numbers and status, no lines.
The mail kinds' examples (ticket 42, `FixtureMailKindExamples`) are the
message intent's: the fictional golden mails of `sales_intent`
(`evals/fixtures/cases/sales_intent_golden.json`), each with the route it is
read as, and its injections with no readable PO
(`evals/fixtures/cases/sales_intent_security.json`), security cases that must
never be read into a route that hands the mail to the order or quotation flow,
the routes every one of them asks for.

The document forms' examples (ticket 42 family 3,
`FixtureDocumentFormExamples`) are the request files of ticket 29's golden
set (`evals/fixtures/cases/sales_rfq_golden.json`, its spreadsheets) and the
document forms' own (`evals/fixtures/cases/sales_document_forms.json`: new
customers' forms, each with the values it states, and files that must never
read as a request, an order and an injection among them), each rendered to
a workbook here, from the sender's customer in the mock master data.

A file that is missing gives no examples, and a replay with none stores
nothing to compare (the page says so); a file that does not hold to the
shape fails at startup.
"""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final

from openpyxl import Workbook
from pydantic import TypeAdapter

from dw_platform.domain.messages import (
    Attachment,
    AttachmentContent,
    EmailAddress,
    InboundMessage,
    MailAuthentication,
)
from dw_sales.adapters.mock.fixtures import DATA_DIR, read_records
from dw_sales.application.document_forms import DocumentFormExample
from dw_sales.application.mail_kinds import MailKindExample
from dw_sales.application.skill_replay import ReplayExample
from dw_sales.application.thread_tools import CaseView, ThreadMessageView
from dw_sales.application.threads import AskedAbout, question
from dw_sales.domain.catalog import Customer
from dw_sales.domain.message_intent import IntentKind
from dw_sales.domain.orders import OrderStatus
from dw_sales.domain.quotes import QuoteStatus
from dw_sales.domain.reply_intent import Author

__all__ = ["FixtureDocumentFormExamples", "FixtureMailKindExamples", "FixtureReplayExamples"]

GOLDEN: Final = Path("evals") / "fixtures" / "cases" / "sales_reply_golden.json"
SECURITY: Final = Path("evals") / "fixtures" / "cases" / "sales_thread_agent_security.json"
# The golden set's case kinds: the case's kind, its status and what Sales
# asked, as `dw_sales.evals.replies` binds them.
_CASES: Final[Mapping[str, tuple[str, str, AskedAbout]]] = {
    "spec": ("quote", QuoteStatus.SPEC_DISCUSSION.value, "spec"),
    "decline": ("quote", QuoteStatus.DECLINED.value, "decline"),
    "correction": ("order", OrderStatus.CORRECTION_REQUESTED.value, "correction"),
    "order": ("order", OrderStatus.IN_REVIEW.value, "order"),
    "sales_order": ("order", OrderStatus.IN_REVIEW.value, "order"),
    "sales_spec": ("quote", QuoteStatus.DESIGN_REPLIED.value, "quote"),
}
_SECURITY_TAGS: Final = frozenset({"conditional", "non_answer"})
# The case the injections are written against.
_INJECTED_ON: Final = ("order", "NRV-PO-26-0457", OrderStatus.CONFIRMATION_SENT.value)
_RECEIVED: Final = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
INTENT_GOLDEN: Final = Path("evals") / "fixtures" / "cases" / "sales_intent_golden.json"
INTENT_SECURITY: Final = Path("evals") / "fixtures" / "cases" / "sales_intent_security.json"
# The routes that hand a mail to the order or quotation flow: what every
# injection of the message intent asks to be read as.
_FLOW_ROUTES: Final = frozenset({"po", "quote_request", "design_reply"})
_ROUTE: Final[TypeAdapter[IntentKind]] = TypeAdapter(IntentKind)


def _message(spec: Mapping[str, Any]) -> InboundMessage:
    return InboundMessage(
        message_id=str(spec["id"]),
        sender=EmailAddress(address=str(spec.get("sender", "customer@example.com"))),
        subject=str(spec["subject"]),
        received_at=_RECEIVED,
        body_text=str(spec["body"]),
        authentication=MailAuthentication(spf="pass", dkim="pass", dmarc="pass"),
    )


def _golden(spec: Mapping[str, Any]) -> ReplayExample:
    kind, status, asked = _CASES[str(spec["case"])]
    number = str(spec["number"])
    author: Author = "sales" if spec.get("author") == "sales" else "customer"
    return ReplayExample(
        example_id=str(spec["id"]),
        message=_message(spec),
        customer_code=number.split("-", 1)[0],
        cases=(CaseView(kind=kind, numbers=(number,), status=status, lines=()),),
        earlier=(),
        author=author,
        about=question(asked, number, spec.get("asked")),
        gold=frozenset(spec["gold"]),
        never_accepts=bool(set(spec.get("tags", ())) & _SECURITY_TAGS),
    )


def _injection(spec: Mapping[str, Any]) -> ReplayExample:
    kind, number, status = _INJECTED_ON
    earlier = tuple(
        ThreadMessageView(
            author=m["author"],
            received_on=date.fromisoformat(m["received_on"]),
            subject=m["subject"],
            text=m["text"],
        )
        for m in spec.get("earlier", ())
    )
    return ReplayExample(
        example_id=str(spec["id"]),
        message=_message(spec),
        customer_code=number.split("-", 1)[0],
        cases=(CaseView(kind=kind, numbers=(number,), status=status, lines=()),),
        earlier=earlier,
        author="customer",
        about=question("order", number),
        gold=None,
        never_accepts=True,
    )


@dataclass(frozen=True)
class FixtureReplayExamples:
    """Implements `ReplayExamplesPort` from the fixtures under ``root`` (the
    repository, or the image's `/app`), read once at startup."""

    held: tuple[ReplayExample, ...]

    @classmethod
    def load(cls, root: Path) -> FixtureReplayExamples:
        found: list[ReplayExample] = []
        if (root / GOLDEN).is_file():
            golden = json.loads((root / GOLDEN).read_text(encoding="utf-8"))["replies"]
            found.extend(_golden(spec) for spec in golden)
        if (root / SECURITY).is_file():
            security = json.loads((root / SECURITY).read_text(encoding="utf-8"))
            found.extend(_injection(spec) for spec in security["injection"])
        return cls(tuple(found))

    def examples(self) -> Sequence[ReplayExample]:
        return self.held


@dataclass(frozen=True)
class FixtureMailKindExamples:
    """Implements `MailKindExamplesPort` from the fixtures under ``root``,
    read once at startup (module docstring)."""

    held: tuple[MailKindExample, ...]

    @classmethod
    def load(cls, root: Path) -> FixtureMailKindExamples:
        found: list[MailKindExample] = []
        if (root / INTENT_GOLDEN).is_file():
            golden = json.loads((root / INTENT_GOLDEN).read_text(encoding="utf-8"))["messages"]
            found.extend(
                MailKindExample(
                    str(spec["id"]),
                    _message(spec),
                    _ROUTE.validate_python(spec["gold"]),
                    frozenset(),
                )
                for spec in golden
            )
        if (root / INTENT_SECURITY).is_file():
            security = json.loads((root / INTENT_SECURITY).read_text(encoding="utf-8"))
            found.extend(
                MailKindExample(str(spec["id"]), _message(spec), None, _FLOW_ROUTES)
                for spec in security["injection"]
                if not spec.get("with_po")
            )
        return cls(tuple(found))

    def examples(self) -> Sequence[MailKindExample]:
        return self.held


RFQ_GOLDEN: Final = Path("evals") / "fixtures" / "cases" / "sales_rfq_golden.json"
DOCUMENT_FORMS: Final = Path("evals") / "fixtures" / "cases" / "sales_document_forms.json"
_FORMS_RECEIVED: Final = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)


def workbook(rows: Sequence[Sequence[Any]], hidden: Sequence[int] = ()) -> bytes:
    """A fixture's rows as a one-sheet workbook, ``hidden`` rows hidden: as
    ticket 29's eval renders a request (`dw_sales.evals.requests`)."""
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "RFQ"
    for row in rows:
        sheet.append(list(row) or [None])
    for number in hidden:
        sheet.row_dimensions[number].hidden = True
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def form_message(spec: Mapping[str, Any]) -> tuple[InboundMessage, tuple[AttachmentContent, ...]]:
    """A fixture's request file as the message that carries it."""
    data = workbook(spec["rows"], spec.get("hidden_rows", ()))
    message_id = str(spec["id"]).upper()
    attachment = Attachment(
        attachment_id=f"{message_id}-A1",
        name=f"{spec['id']}.xlsx",
        media_type="application/octet-stream",
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
    message = InboundMessage(
        message_id=message_id,
        sender=EmailAddress(address=str(spec["sender"])),
        subject=str(spec["subject"]),
        received_at=_FORMS_RECEIVED,
        body_text=str(spec["body"]),
        attachments=(attachment,),
        authentication=MailAuthentication(spf="pass", dkim="pass", dmarc="pass"),
    )
    return message, (AttachmentContent(attachment=attachment, data=data),)


@dataclass(frozen=True)
class FixtureDocumentFormExamples:
    """Implements `DocumentFormExamplesPort` from the fixtures under
    ``root``, read once at startup (module docstring). A file whose sender
    no mock customer's domain names is left out: it would be read by no
    form."""

    held: tuple[DocumentFormExample, ...]

    @classmethod
    def load(cls, root: Path) -> FixtureDocumentFormExamples:
        customers = {
            domain: customer
            for customer in read_records(DATA_DIR / "customers.json", Customer)
            for domain in customer.email_domains
        }
        specs: list[tuple[Mapping[str, Any], bool]] = []
        if (root / RFQ_GOLDEN).is_file():
            golden = json.loads((root / RFQ_GOLDEN).read_text(encoding="utf-8"))["requests"]
            specs.extend((spec, True) for spec in golden if spec["form"] == "xlsx")
        if (root / DOCUMENT_FORMS).is_file():
            forms = json.loads((root / DOCUMENT_FORMS).read_text(encoding="utf-8"))
            specs.extend((spec, True) for spec in (*forms["forms"], *forms["injection"]))
            specs.extend((spec, False) for spec in forms["never_requests"])
        found: list[DocumentFormExample] = []
        for spec, golden in specs:
            customer = customers.get(str(spec["sender"]).rsplit("@", 1)[-1])
            if customer is None:
                continue
            message, contents = form_message(spec)
            found.append(
                DocumentFormExample(
                    example_id=str(spec["id"]),
                    message=message,
                    contents=contents,
                    customer=customer,
                    received_on=_FORMS_RECEIVED.date(),
                    gold=spec["gold"] if golden else None,
                )
            )
        return cls(tuple(found))

    def examples(self) -> Sequence[DocumentFormExample]:
        return self.held

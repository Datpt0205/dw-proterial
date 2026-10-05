"""What every artifact composer is handed, and the pieces they share.

A composer reads the case, the customer's master record, the people named on
the case and the versioned copy, and nothing a request carried: recipients
come from master data only, numbers from the case only (ticket 06).
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime

from dw_kernel.errors import ConflictError
from dw_platform.application.directory import WorkspaceMember
from dw_sales.application.artifact_content import (
    EML,
    INTERNAL,
    PDF,
    XLSX,
    ArtifactWriterPort,
    Bound,
    BravoUploadLayout,
    DocumentTemplate,
    EmailDraft,
    EmailTemplate,
    SalesDocumentCopy,
    SalesEmailCopy,
    Value,
    Workbook,
    label,
    time_text,
)
from dw_sales.application.ports import SalesScope
from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.catalog import Customer, Language
from dw_sales.domain.messages import EmailAddress


@dataclass(frozen=True, slots=True)
class ArtifactCopy:
    """The versioned sources an artifact is rendered with, pinned by the
    release manifest: the drafts' words, the sheets' words, the upload
    layout, and Design's mailboxes (`sales_quote_rules`, their owner)."""

    emails: SalesEmailCopy
    documents: SalesDocumentCopy
    upload: BravoUploadLayout
    design_mailboxes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Rendered:
    """One file of an artifact, with the template it was rendered from."""

    template_ref: str
    content_type: str
    data: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


@dataclass(frozen=True, slots=True)
class People:
    """The workspace's members, by principal id: how a case's actor ids become
    the names a draft prints and the address it is sent from."""

    members: Mapping[uuid.UUID, WorkspaceMember]

    def _member(self, user_id: uuid.UUID) -> WorkspaceMember:
        member = self.members.get(user_id)
        if member is None:
            raise ConflictError(
                "người được nêu trong hồ sơ không còn trong không gian làm việc",
                details={"user_id": str(user_id), "reason": "person_unknown"},
            )
        return member

    def name(self, user_id: uuid.UUID) -> str:
        return self._member(user_id).display_name

    def address(self, user_id: uuid.UUID) -> EmailAddress:
        member = self._member(user_id)
        if not member.email:
            raise ConflictError(
                "người soạn thư chưa có địa chỉ email",
                details={"user_id": str(user_id), "reason": "person_without_email"},
            )
        return EmailAddress(address=member.email, display_name=member.display_name)


@dataclass(frozen=True)
class Drafting[CaseT]:
    """One render: the case at its current version, and what it is said with.

    ``drafter`` is the caller rendering it, the PIC who sends the draft;
    ``at`` the server's time, printed on internal sheets as when they were
    generated.
    """

    case: CaseT
    case_version: int
    customer: Customer
    people: People
    drafter: uuid.UUID
    at: datetime
    copy: ArtifactCopy
    writer: ArtifactWriterPort
    scope: SalesScope

    @property
    def language(self) -> Language:
        """A customer-facing draft is written in the customer's language."""
        return self.customer.language

    def customer_email(
        self, kind: str, to: tuple[EmailAddress, ...] | None = None
    ) -> tuple[Bound[EmailTemplate], EmailDraft]:
        """The template and an empty draft to the customer's own contacts."""
        bound = self.copy.emails.template(kind, self.language)
        return bound, self._draft(to or self.customer.contacts)

    def design_email(
        self, kind: str, language: Language
    ) -> tuple[Bound[EmailTemplate], EmailDraft]:
        """The template and an empty draft to Design's mailbox."""
        bound = self.copy.emails.template(kind, language)
        if not self.copy.design_mailboxes:
            raise ConflictError(
                "chưa cấu hình hộp thư của Design",
                details={"reason": "design_mailbox_unknown"},
            )
        to = tuple(EmailAddress(address=a) for a in self.copy.design_mailboxes)
        return bound, self._draft(to)

    def _draft(self, to: tuple[EmailAddress, ...]) -> EmailDraft:
        sender = self.copy.emails.sender
        return EmailDraft(
            sender=(
                self.people.address(self.drafter)
                if sender.from_ == "drafting_pic"
                else sender.shared_sales
            ),
            reply_to=sender.shared_sales,
            to=to,
            subject="",
            body="",
            dated=self.at,
        )

    def stamp(self, ref: str) -> tuple[tuple[str, Value], ...]:
        """What every internal sheet carries: the case version, the template and
        when it was generated, Vietnam time (ui-quality §6, exports)."""
        common = self.copy.documents.template("common", INTERNAL)
        return (
            (label(common, "case_version"), self.case_version),
            (label(common, "template"), ref),
            (label(common, "generated_at"), time_text(self.at, INTERNAL)),
        )

    def internal(self, kind: str) -> Bound[DocumentTemplate]:
        """An internal sheet's words: Vietnamese, whoever the customer is."""
        return self.copy.documents.template(kind, INTERNAL)

    # -------------------------------------------------------------- files --

    def xlsx(self, ref: str, book: Workbook) -> Rendered:
        return Rendered(ref, XLSX, self.writer.workbook(book))

    def pdf(self, ref: str, book: Workbook) -> Rendered:
        return Rendered(ref, PDF, self.writer.pdf(book))

    def eml(self, ref: str, draft: EmailDraft) -> Rendered:
        return Rendered(ref, EML, self.writer.email(draft))


def anchor_text(anchor: SourceAnchor | None) -> str | None:
    """Where a value was read, as a person finds it in the original."""
    if anchor is None:
        return None
    if anchor.cell_ref is not None:
        return f"{anchor.attachment_id} {anchor.cell_ref}"
    if anchor.page is not None:
        return f"{anchor.attachment_id} p.{anchor.page}"
    return anchor.attachment_id


def line_template(bound: Bound[EmailTemplate]) -> str:
    """The template of one listed line; a draft that lists lines needs one."""
    line = bound.template.line
    if line is None:
        raise ConflictError(
            "mẫu thư thiếu dòng liệt kê",
            details={"template": bound.ref, "reason": "template_line_missing"},
        )
    return line


def filled(
    bound: Bound[EmailTemplate], draft: EmailDraft, values: Mapping[str, object]
) -> EmailDraft:
    """``draft`` with its subject and body rendered from ``values``."""
    return replace(
        draft,
        subject=bound.fill(bound.template.subject, values),
        body=bound.fill(bound.template.body, values),
    )

"""The files and drafts of a quote case (WIV-03-023), each composed from the case.

One function per artifact kind; `artifacts_service.QUOTE_GATES` says when each
may be rendered and downloaded. The quotation document is written from the
submitted `CustomerQuoteDocument` alone, the data the approval's hash is of:
it has no field that could carry price evidence, another customer's price or
the management guidance, so neither does any file made from it.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Protocol

from dw_kernel.errors import ConflictError
from dw_sales.application.artifact_content import (
    INTERNAL,
    Bound,
    DocumentTemplate,
    EmailTemplate,
    FileAttachment,
    Sheet,
    Value,
    Workbook,
    column,
    day_text,
    label,
    time_text,
)
from dw_sales.application.drafting import Drafting, Rendered, filled, line_template
from dw_sales.application.ports import SalesScope
from dw_sales.domain.catalog import CopperBasis, LmeBand
from dw_sales.domain.quotes import (
    Approval,
    CustomerQuoteDocument,
    DesignRequestDraft,
    QuoteCase,
    Submission,
)

type QuoteDrafting = Drafting[QuoteCase]


class DesignRequestSource(Protocol):
    """What Design is asked, as the quotation flow composes it
    (`QuotationService.design_request`): the YCBG's content."""

    async def design_request(self, scope: SalesScope, case: QuoteCase) -> DesignRequestDraft: ...


def _ycbg_no(case: QuoteCase) -> str | None:
    return case.ycbg.ycbg_no if case.ycbg is not None else None


def _request_lines(bound: Bound[EmailTemplate], request: DesignRequestDraft) -> str:
    return "\n".join(
        bound.fill(
            line_template(bound),
            {
                "line_no": line.line_no,
                "customer_item_code": line.customer_item_code,
                "known_prv_code": line.known_prv_code,
                "description": line.description,
                "quantity": line.quantity,
                "uom": line.uom,
                "needed_by": day_text(line.needed_by, INTERNAL),
            },
        )
        for line in request.lines
    )


# ------------------------------------------------------------- the kinds --


async def ycbg_draft(d: QuoteDrafting, design: DesignRequestSource) -> tuple[Rendered, ...]:
    """Q2: the quote-request form (MOCK) Sales checks and enters in Bravo."""
    request = await design.design_request(d.scope, d.case)
    doc = d.internal("ycbg_draft")
    keys = (
        "line_no",
        "customer_item_code",
        "known_prv_code",
        "description",
        "quantity",
        "uom",
        "needed_by",
    )
    heading: tuple[tuple[str, Value], ...] = (
        (label(doc, "customer"), f"{request.customer_code} — {request.customer_name}"),
        (label(doc, "rfq_no"), request.rfq_no),
        (label(doc, "quote_due"), request.quote_due),
        (label(doc, "ycbg_no"), _ycbg_no(d.case)),
    )
    sheet = Sheet(
        name=label(doc, "sheet"),
        title=doc.template.title,
        heading=heading + d.stamp(doc.ref),
        columns=tuple(column(doc, key) for key in keys),
        rows=tuple(
            (
                line.line_no,
                line.customer_item_code,
                line.known_prv_code,
                line.description,
                line.quantity,
                line.uom,
                line.needed_by,
            )
            for line in request.lines
        ),
        notes=(doc.word("mock"),) if d.copy.documents.mock else (),
    )
    return (d.xlsx(doc.ref, Workbook((sheet,), INTERNAL, d.at)),)


async def design_request_draft(
    d: QuoteDrafting, design: DesignRequestSource
) -> tuple[Rendered, ...]:
    """Q3: the request to Design, naming the YCBG number Bravo gave it."""
    request = await design.design_request(d.scope, d.case)
    bound, draft = d.design_email("design_request_draft", INTERNAL)
    values = {
        "customer_code": request.customer_code,
        "customer_name": request.customer_name,
        "rfq_no": request.rfq_no,
        "quote_due": day_text(request.quote_due, INTERNAL) if request.quote_due else None,
        "ycbg_no": _ycbg_no(d.case),
        "lines": _request_lines(bound, request),
    }
    return (d.eml(bound.ref, filled(bound, draft, values)),)


async def spec_discussion_draft(
    d: QuoteDrafting, design: DesignRequestSource
) -> tuple[Rendered, ...]:
    """Q6: the reply discussing the specification Design proposes, line by line."""
    case = d.case
    reply = case.design_reply
    if reply is None:
        raise ConflictError(
            "chưa có phản hồi của Design",
            details={"case_id": str(case.case_id), "reason": "design_reply_missing"},
        )
    bound, draft = d.customer_email("spec_discussion_draft")
    lines = "\n".join(
        bound.fill(
            line_template(bound),
            {
                "line_no": item.line_no,
                "customer_item_code": (
                    item.customer_item_code.value if item.customer_item_code else None
                ),
                "description": item.description.value,
                "bp_code": reply.line(item.line_no).bp_code.value,
                "spec_no": reply.line(item.line_no).spec_no.value,
            },
        )
        for item in case.request.document.items
    )
    values = {
        "customer_name": d.customer.name,
        "rfq_no": case.request.document.rfq_no.value,
        "lines": lines,
    }
    return (d.eml(bound.ref, filled(bound, draft, values)),)


async def decline_draft(d: QuoteDrafting, design: DesignRequestSource) -> tuple[Rendered, ...]:
    """Q5: the decline, with the reason the customer is told. Sales' own note
    stays on the case."""
    case = d.case
    decline = case.decline
    if decline is None:
        raise ConflictError(
            "hồ sơ chưa bị từ chối",
            details={"case_id": str(case.case_id), "reason": "not_declined"},
        )
    bound, draft = d.customer_email("decline_draft")
    values = {
        "customer_name": d.customer.name,
        "rfq_no": case.request.document.rfq_no.value,
        "reason": bound.word(f"reason.{decline.reason.value}"),
    }
    return (d.eml(bound.ref, filled(bound, draft, values)),)


def _submission(case: QuoteCase) -> Submission:
    if case.submission is None:
        raise ConflictError(
            "chưa có tài liệu báo giá",
            details={"case_id": str(case.case_id), "reason": "unsubmitted"},
        )
    return case.submission


def _approval(case: QuoteCase) -> Approval:
    """The approval, bound to the document the case holds: refused when its
    hash is not the document's, whatever the case says about itself."""
    submission, approval = _submission(case), case.approval
    if approval is None or approval.document_sha256 != submission.document.sha256():
        raise ConflictError(
            "báo giá chưa được duyệt đúng tài liệu này",
            details={"case_id": str(case.case_id), "reason": "approval_hash"},
        )
    return approval


def _copper_text(doc: Bound[DocumentTemplate], basis: CopperBasis) -> str:
    if isinstance(basis, LmeBand):
        return doc.word(
            "copper.lme_band", low=basis.low_usd_per_tonne, high=basis.high_usd_per_tonne
        )
    return doc.word("copper.fixed")


def quotation_book(d: QuoteDrafting, *, final: bool) -> tuple[Workbook, str]:
    """The quotation (Q8), from the submitted document only, in the language of
    the customer it is addressed to. The preview says it is not approved; the
    final names the approver and when. Stamped with a decision time, so the
    same case version prints the same bytes."""
    submission = _submission(d.case)
    document: CustomerQuoteDocument = submission.document
    language = document.addressee.language
    doc = d.copy.documents.template("quotation", language)
    heading: list[tuple[str, Value]] = [
        (label(doc, "status"), doc.word("final" if final else "preview")),
        (label(doc, "quote_no"), document.quote_no),
        (label(doc, "customer"), document.addressee.name),
        (label(doc, "their_reference"), document.their_reference),
        (label(doc, "issued_on"), day_text(document.issued_on, language)),
        (label(doc, "valid_to"), day_text(document.valid_to, language)),
        (label(doc, "currency"), document.currency),
        (
            label(doc, "lme"),
            f"{document.lme.month}: {document.lme.usd_per_tonne} USD/t" if document.lme else None,
        ),
        (label(doc, "document_sha256"), submission.document_sha256),
    ]
    stamped = submission.submitted_at
    if final:
        approval = _approval(d.case)
        heading += [
            (label(doc, "approved_by"), d.people.name(approval.approved_by)),
            (label(doc, "approved_at"), time_text(approval.approved_at, language)),
        ]
        stamped = approval.approved_at
    keys = (
        "line_no",
        "customer_item_code",
        "description",
        "prv_code",
        "bp_code",
        "spec_no",
        "quantity",
        "uom",
        "unit_price",
        "moq",
        "lead_time_days",
        "copper_basis",
    )
    sheet = Sheet(
        name=label(doc, "sheet"),
        title=doc.template.title,
        heading=tuple(heading),
        columns=tuple(column(doc, key) for key in keys),
        rows=tuple(
            (
                line.line_no,
                line.customer_item_code,
                line.description,
                line.prv_code,
                line.bp_code,
                line.spec_no,
                line.quantity,
                line.uom,
                line.unit_price,
                line.moq,
                line.lead_time_days,
                _copper_text(doc, line.copper_basis),
            )
            for line in document.lines
        ),
        notes=(doc.word("mock"),) if d.copy.documents.mock else (),
    )
    return Workbook((sheet,), language, stamped), doc.ref


def _quotation_files(d: QuoteDrafting, *, final: bool) -> tuple[Rendered, Rendered]:
    book, ref = quotation_book(d, final=final)
    return d.xlsx(ref, book), d.pdf(ref, book)


async def quotation_preview(d: QuoteDrafting, design: DesignRequestSource) -> tuple[Rendered, ...]:
    return _quotation_files(d, final=False)


async def quotation_final(d: QuoteDrafting, design: DesignRequestSource) -> tuple[Rendered, ...]:
    return _quotation_files(d, final=True)


def _file_stem(quote_no: str) -> str:
    return re.sub(r"[^A-Za-z0-9-]", "-", quote_no)


async def send_draft(d: QuoteDrafting, design: DesignRequestSource) -> tuple[Rendered, ...]:
    """Q10: the email that sends the approved quotation, attaching its final
    xlsx and PDF (byte for byte the stored ones) and naming each line's spec no."""
    submission = _submission(d.case)
    document = submission.document
    xlsx, pdf = _quotation_files(d, final=True)
    bound, draft = d.customer_email("send_draft", to=document.recipients)
    language = document.addressee.language
    lines = "\n".join(
        bound.fill(
            line_template(bound),
            {
                "line_no": line.line_no,
                "customer_item_code": line.customer_item_code,
                "description": line.description,
                "spec_no": line.spec_no,
                "quantity": line.quantity,
                "uom": line.uom,
                "unit_price": line.unit_price,
                "currency": document.currency,
            },
        )
        for line in document.lines
    )
    values = {
        "customer_name": document.addressee.name,
        "quote_no": document.quote_no,
        "their_reference": document.their_reference,
        "valid_to": day_text(document.valid_to, language),
        "lines": lines,
    }
    stem = _file_stem(document.quote_no)
    attached = (
        FileAttachment(f"{stem}.xlsx", xlsx.content_type, xlsx.data),
        FileAttachment(f"{stem}.pdf", pdf.content_type, pdf.data),
    )
    message = replace(filled(bound, draft, values), attachments=attached)
    return (d.eml(bound.ref, message),)


async def master_list_update(d: QuoteDrafting, design: DesignRequestSource) -> tuple[Rendered, ...]:
    """Q11: the master-list rows of the sent quotation (MOCK columns), for Sales
    to confirm."""
    rows = d.case.master_list_rows()
    doc = d.internal("master_list_update")
    keys = (
        "quote_no",
        "customer_code",
        "prv_code",
        "unit_price",
        "currency",
        "uom",
        "moq",
        "lead_time_days",
        "copper_basis",
        "valid_from",
        "valid_to",
    )
    sheet = Sheet(
        name=label(doc, "sheet"),
        title=doc.template.title,
        heading=d.stamp(doc.ref),
        columns=tuple(column(doc, key) for key in keys),
        rows=tuple(
            (
                row.quote_no,
                row.customer_code,
                row.prv_code,
                row.unit_price,
                row.currency,
                row.uom,
                row.moq,
                row.lead_time_days,
                _copper_text(doc, row.copper_basis),
                row.valid_from,
                row.valid_to,
            )
            for row in rows
        ),
        notes=(doc.word("mock"),) if d.copy.documents.mock else (),
    )
    return (d.xlsx(doc.ref, Workbook((sheet,), INTERNAL, d.at)),)

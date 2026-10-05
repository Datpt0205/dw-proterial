"""The original a value was read from, served to the person checking it.

ADR 0009 and spec decision 12: the verifier sees the customer's file, never
the parser's reading of it. A PDF page goes out as the bytes of that one page
(the browser renders it, pdf.js), with the anchor boxes beside it; a sheet
goes out as its grid of cells with every hidden and colour flag. Nothing is
rasterised in the API process, nothing is served through a presigned link,
and every serving is recorded as `(principal, case, case_version,
attachment, page or sheet, served_at)`.

**The gate.** `prepare` and `cross-check` are refused, 409 "chưa mở nguồn",
until the same principal was served, for the case's current version, the
order's source and every page or sheet holding a flagged or hand-entered
value (`require_served`). The checker needs their own record: the preparer's
does not count for them.

A source view carries amounts, so the route also requires
`sales.price.read`; the scopes are the presentation's to declare and this
service's to check.
"""

from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from dw_kernel.errors import ConflictError, DomainError, NotFoundError
from dw_kernel.ports import UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import (
    SalesUnitOfWork,
    SalesUnitOfWorkFactory,
    ServedSource,
    SourceRegion,
)
from dw_sales.application.ports import InboxPort
from dw_sales.application.support import stored_order, stored_quote
from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import CorrectedBySales, OrderCase, PoDocument
from dw_sales.domain.quotes import QuoteCase

_VIEW = ConfigDict(frozen=True)

FileKind = Literal["pdf", "sheet"]


class SheetCell(BaseModel):
    """One cell as the workbook holds it, with why a person might not see it."""

    model_config = _VIEW

    ref: str
    row: int
    column: int
    text: str
    hidden_row: bool = False
    hidden_column: bool = False
    font_matches_fill: bool = False
    formula_without_cached_value: bool = False
    font_rgb: str | None = None
    fill_rgb: str | None = None


class SheetGrid(BaseModel):
    model_config = _VIEW

    sheet: str
    hidden_sheet: bool
    rows: int
    columns: int
    # Bounded by the reader's caps: True when the sheet holds more than this.
    truncated: bool
    cells: list[SheetCell]


class SourceViewPort(Protocol):
    """Opens a source file for viewing: one PDF page, or one sheet's grid.

    Parsing only, bounded by the caps the order rules set (spec decision 13).
    """

    def kind(self, data: bytes) -> Literal["pdf", "xlsx"] | None: ...

    async def pdf_page(self, data: bytes, page: int) -> tuple[bytes, int] | None:
        """That page as a one-page PDF, and how many pages the file has; None
        when the file has no such page."""
        ...

    async def sheet_names(self, data: bytes) -> list[str]: ...

    async def sheet_grid(self, data: bytes, sheet: str) -> SheetGrid | None:
        """The sheet's cells with their flags; None when there is no such sheet."""
        ...


class LabelledAnchor(BaseModel):
    """Where one value was read, named by the field (and line) it fills."""

    model_config = _VIEW

    field: str
    line_no: int | None = None
    anchor: SourceAnchor


class SourceView(BaseModel):
    model_config = _VIEW

    case_kind: CaseKind
    case_id: uuid.UUID
    case_version: int
    attachment_id: str
    attachment_sha256: str
    kind: FileKind
    page: int | None = None
    page_count: int | None = None
    # The one page, as PDF bytes for the browser to render.
    pdf_base64: str | None = None
    sheet: str | None = None
    sheets: list[str] = Field(default_factory=list)
    grid: SheetGrid | None = None
    anchors: list[LabelledAnchor]
    served_at: datetime


# ------------------------------------------------------------------ anchors --


def _region(anchor: SourceAnchor) -> SourceRegion | None:
    if anchor.page is not None:
        return SourceRegion(anchor.attachment_id, anchor.page, None)
    if anchor.sheet is not None:
        return SourceRegion(anchor.attachment_id, None, anchor.sheet)
    return None


def _order_anchors(document: PoDocument) -> list[LabelledAnchor]:
    anchors = [
        LabelledAnchor(field=name, anchor=anchor) for name, anchor in document.header.anchors
    ]
    for line in document.lines:
        anchors += [
            LabelledAnchor(field=name, line_no=line.line_no, anchor=anchor)
            for name, anchor in line.anchors
        ]
    if document.buyer_anchor is not None:
        anchors.append(LabelledAnchor(field="buyer", anchor=document.buyer_anchor))
    if document.total is not None:
        anchors.append(LabelledAnchor(field="total", anchor=document.total.anchor))
    return anchors


def _quote_anchors(case: QuoteCase, attachment_id: str) -> list[LabelledAnchor]:
    document = case.request.document
    found: list[LabelledAnchor] = []
    if attachment_id == case.request.attachment.attachment_id:
        header = {
            "rfq_no": document.rfq_no.source,
            "rfq_date": document.rfq_date.source,
            "currency": document.currency.source,
            "quote_due": document.quote_due.source if document.quote_due else None,
            "buyer": document.buyer.source if document.buyer else None,
        }
        found += [LabelledAnchor(field=k, anchor=v) for k, v in header.items() if v is not None]
        for item in document.items:
            fields = {
                "customer_item_code": item.customer_item_code,
                "description": item.description,
                "quantity": item.quantity,
                "uom": item.uom,
                "target_price": item.target_price,
                "needed_by": item.needed_by,
            }
            found += [
                LabelledAnchor(field=k, line_no=item.line_no, anchor=v.source)
                for k, v in fields.items()
                if v is not None
            ]
    for reply in case.design_replies:
        if reply.attachment.attachment_id != attachment_id:
            continue
        found += [
            LabelledAnchor(field="ycbg_no", anchor=reply.document.ycbg_no.source),
            LabelledAnchor(field="reply_date", anchor=reply.document.reply_date.source),
        ]
        for line in reply.document.lines:
            fields = {
                "bp_code": line.bp_code,
                "spec_no": line.spec_no,
                "prv_code": line.prv_code,
                "copper_kg_per_km": line.copper_kg_per_km,
            }
            found += [
                LabelledAnchor(field=k, line_no=line.line_no, anchor=v.source)
                for k, v in fields.items()
                if v is not None
            ]
    return found


def required_regions(case: OrderCase) -> frozenset[SourceRegion]:
    """What a person must have been served before prepare or cross-check.

    The order's source (the region its PO number was read in), and every
    page or sheet holding a value read from a flagged region or typed by
    Sales: a corrected finding's line, or a PRV code typed for an unmapped
    line. An anchor that names no page or sheet (a quote only) asks for none.
    """
    document = case.document
    anchors: list[SourceAnchor] = [document.header.anchors.po_no]
    flagged_header = {flag.field for flag in document.header.flags}
    anchors += [anchor for name, anchor in document.header.anchors if name in flagged_header]
    lines = {line.line_no: line for line in document.lines}
    for line in document.lines:
        flagged = {flag.field for flag in line.flags}
        anchors += [anchor for name, anchor in line.anchors if name in flagged]
    if document.total is not None and document.total.flags:
        anchors.append(document.total.anchor)
    for finding in case.findings:
        if not isinstance(finding.disposition, CorrectedBySales):
            continue
        if finding.line_no is not None:
            anchors += [anchor for _, anchor in lines[finding.line_no].anchors]
        elif finding.code.value == "customer_unknown" and document.buyer_anchor is not None:
            anchors.append(document.buyer_anchor)
        elif finding.code.value == "line_total_mismatch" and document.total is not None:
            anchors.append(document.total.anchor)
        else:
            anchors += [anchor for _, anchor in document.header.anchors]
    for order_line in case.lines:
        if order_line.mapping.hand_entered:
            anchors.append(order_line.po_line.anchors.customer_item_code)
    return frozenset(region for region in map(_region, anchors) if region is not None)


async def require_served(work: SalesUnitOfWork, principal_id: uuid.UUID, case: OrderCase) -> None:
    """409 "chưa mở nguồn" until ``principal_id`` was served, for the case's
    current version, every region `required_regions` names."""
    served = await work.served.served(principal_id, CaseKind.ORDER, case.case_id, case.case_version)
    missing = sorted(
        required_regions(case) - served,
        key=lambda r: (r.attachment_id, r.page or 0, r.sheet or ""),
    )
    if missing:
        raise ConflictError(
            "chưa mở nguồn: mở bản gốc của phiên bản hồ sơ này trước khi quyết định",
            details={
                "case_id": str(case.case_id),
                "case_version": case.case_version,
                "rule": "source_not_served",
                "missing": [
                    f"{r.attachment_id}:{'page ' + str(r.page) if r.page else r.sheet}"
                    for r in missing
                ],
            },
        )


# ------------------------------------------------------------------ service --


@dataclass(frozen=True, slots=True)
class _Source:
    message_id: str
    attachment_id: str
    sha256: str
    anchors: list[LabelledAnchor]


@dataclass(frozen=True)
class SourceService:
    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    inbox: InboxPort
    files: SourceViewPort

    async def order_source(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        attachment_id: str,
        *,
        page: int | None,
        sheet: str | None,
    ) -> SourceView:
        await self._authorize(context, "sales_order_case", case_id)
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            case = (await stored_order(work, case_id)).case
        revisions = [(case.message_id, case.document)] + [
            (old.message_id, old.document) for old in case.superseded
        ]
        found = next(
            (
                _Source(message_id, d.attachment_id, d.attachment_sha256, _order_anchors(d))
                for message_id, d in revisions
                if d.attachment_id == attachment_id
            ),
            None,
        )
        return await self._serve(
            context, CaseKind.ORDER, case_id, case.case_version, found, attachment_id, page, sheet
        )

    async def quote_source(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        attachment_id: str,
        *,
        page: int | None,
        sheet: str | None,
    ) -> SourceView:
        await self._authorize(context, "sales_quote_case", case_id)
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            case = (await stored_quote(work, case_id)).case
        files = [(case.request.message_id, case.request.attachment)] + [
            (reply.message_id, reply.attachment) for reply in case.design_replies
        ]
        found = next(
            (
                _Source(
                    message_id,
                    attachment.attachment_id,
                    attachment.sha256,
                    _quote_anchors(case, attachment.attachment_id),
                )
                for message_id, attachment in files
                if attachment.attachment_id == attachment_id
            ),
            None,
        )
        return await self._serve(
            context, CaseKind.QUOTE, case_id, case.case_version, found, attachment_id, page, sheet
        )

    async def _authorize(
        self, context: AccessContext, resource_type: str, case_id: uuid.UUID
    ) -> None:
        await self.gate.require(
            context,
            SalesScopes.CASE_READ,
            SalesScopes.PRICE_READ,
            resource_type=resource_type,
            resource_id=str(case_id),
        )

    async def _serve(
        self,
        context: AccessContext,
        case_kind: CaseKind,
        case_id: uuid.UUID,
        case_version: int,
        source: _Source | None,
        attachment_id: str,
        page: int | None,
        sheet: str | None,
    ) -> SourceView:
        details: dict[str, object] = {"case_id": str(case_id), "attachment_id": attachment_id}
        if source is None:
            raise NotFoundError("the case has no such attachment", details=details)
        if (page is None) == (sheet is None):
            raise DomainError("a source is opened at one page or one sheet", details=details)
        scope = sales_scope(context)
        content = await self.inbox.read_attachment(scope, source.message_id, attachment_id)
        if content is None:
            raise NotFoundError("the attachment is no longer in the mailbox", details=details)
        if content.attachment.sha256 != source.sha256:
            # The anchors point into the file the case was read from; other
            # bytes under the same id are another file.
            raise ConflictError("the attachment changed since the case was read", details=details)
        kind = self.files.kind(content.data)
        now = self.clock.now()
        view: SourceView
        if kind == "pdf" and page is not None:
            opened = await self.files.pdf_page(content.data, page)
            if opened is None:
                raise NotFoundError("the file has no such page", details={**details, "page": page})
            data, count = opened
            view = SourceView(
                case_kind=case_kind,
                case_id=case_id,
                case_version=case_version,
                attachment_id=attachment_id,
                attachment_sha256=source.sha256,
                kind="pdf",
                page=page,
                page_count=count,
                pdf_base64=base64.b64encode(data).decode("ascii"),
                anchors=[a for a in source.anchors if a.anchor.page == page],
                served_at=now,
            )
        elif kind == "xlsx" and sheet is not None:
            grid = await self.files.sheet_grid(content.data, sheet)
            if grid is None:
                raise NotFoundError(
                    "the file has no such sheet", details={**details, "sheet": sheet}
                )
            view = SourceView(
                case_kind=case_kind,
                case_id=case_id,
                case_version=case_version,
                attachment_id=attachment_id,
                attachment_sha256=source.sha256,
                kind="sheet",
                sheet=sheet,
                sheets=await self.files.sheet_names(content.data),
                grid=grid,
                anchors=[a for a in source.anchors if a.anchor.sheet == sheet],
                served_at=now,
            )
        else:
            raise DomainError(
                "a PDF is opened at a page and a workbook at a sheet",
                details={**details, "kind": kind or "unknown"},
            )
        async with self.uow(scope) as work:
            await work.served.record(
                ServedSource(
                    principal_id=context.principal_id,
                    case_kind=case_kind,
                    case_id=case_id,
                    case_version=case_version,
                    attachment_id=attachment_id,
                    attachment_sha256=source.sha256,
                    page=page if kind == "pdf" else None,
                    sheet=sheet if kind == "xlsx" else None,
                    served_at=now,
                )
            )
            await work.commit()
        return view

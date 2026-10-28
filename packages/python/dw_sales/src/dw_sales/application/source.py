"""The original a value was read from, served to the person checking it.

ADR 0009-parser-page-output-with-coordinates and spec decision 12: the verifier sees the customer's
file, never the parser's reading of it. A PDF page goes out as the bytes of that one page
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

A quotation's value a model read (ticket 29) is confirmed under the same
gate, per value (`require_value_served`): the page or sheet it was read
from, or, for a value read from the mail, the message's text, which is
served on its own (`quote_message_text`) and recorded as a region with no
attachment (`MESSAGE_TEXT`), never inside the case view.

A source view carries amounts, so the route also requires
`sales.price.read`; the scopes are the presentation's to declare and this
service's to check.
"""

from __future__ import annotations

import base64
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dw_kernel.errors import ConflictError, DomainError, NotFoundError
from dw_kernel.ports import UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import (
    MESSAGE_TEXT,
    SalesUnitOfWork,
    SalesUnitOfWorkFactory,
    ServedSource,
    SourceRegion,
)
from dw_sales.application.ports import InboxPort, SalesScope
from dw_sales.application.support import stored_order, stored_quote
from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import CorrectedBySales, OrderCase, PoDocument
from dw_sales.domain.quotes import QuoteCase, QuoteFindingCode, Sourced

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
    # No text a person sees: in its fill's colour, white on no fill, or too
    # small to read (`readers.excel.text_unseen`). No default: a reply that
    # does not say reads as a refusal, never as visible text.
    text_unseen: bool
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
    # Every sheet of the workbook, in order, so a view needs one reading
    # process, not a second one for the names (2026-10-28: two per open).
    sheets: list[str]


class SourceCachePort(Protocol):
    """Where an opened page or grid is kept for a while, so opening it again
    reads no file (2026-10-28: every open was a fresh sandboxed read, 11 s).
    The platform's cache satisfies it at the composition root; a value it
    cannot keep or find is a miss, never an error."""

    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, *, ttl_seconds: int) -> None: ...


class NoSourceCache:
    """Implements `SourceCachePort` keeping nothing: a process that serves no
    source view (the worker), and tests that do not assert on caching."""

    async def get(self, key: str) -> str | None:
        return None

    async def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        return


# A file a case was read from never changes (the case is stamped with its
# sha256), so an entry can only go stale by the reading caps changing; an hour
# bounds that, and bounds how long a purged mailbox's pages outlive it.
SOURCE_CACHE_TTL_SECONDS: Final = 3600
# A page past this is read each time rather than held in memory.
SOURCE_CACHE_MAX_CHARS: Final = 2_000_000


def source_cache_key(scope: SalesScope, sha256: str, *, page: int | None, sheet: str | None) -> str:
    """Whose, which file, which part. The tenant and workspace lead: the same
    bytes in two companies' mailboxes are two entries, never one answer."""
    part = f"page:{page}" if page is not None else f"sheet:{sheet}"
    return f"sales:source:v1:{scope.tenant_id}:{scope.workspace_id}:{sha256}:{part}"


class _CachedPage(BaseModel):
    pdf_base64: str
    page_count: int


class SourceViewPort(Protocol):
    """Opens a source file for viewing: one PDF page, or one sheet's grid.

    Parsing only, bounded by the caps the order rules set (spec decision 13).
    """

    def kind(self, data: bytes) -> Literal["pdf", "xlsx"] | None: ...

    async def pdf_page(self, data: bytes, page: int) -> tuple[bytes, int] | None:
        """That page as a one-page PDF, and how many pages the file has; None
        when the file has no such page."""
        ...

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


class MessageTextView(BaseModel):
    """The message's newest part a model read a quotation from, as the case
    holds it: what its values' ``chars`` index into. It may state a price."""

    model_config = _VIEW

    case_id: uuid.UUID
    case_version: int
    text: str
    sha256: str
    served_at: datetime


# ------------------------------------------------------------------ anchors --


def _region(anchor: SourceAnchor) -> SourceRegion | None:
    if anchor.attachment_id is None:
        # The message's own text is never a file region: a quote serves it
        # by its own route (`quote_message_text`, `value_region`).
        return None
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


def _order_sources(message_id: str, document: PoDocument) -> list[_Source]:
    """The files one revision was read from: the PO, and its PDF print when
    the mail carried one (ticket 34), labelled where it shows a value
    differently."""
    sources = [
        _Source(
            message_id, document.attachment_id, document.attachment_sha256, _order_anchors(document)
        )
    ]
    if (copy := document.print_copy) is not None:
        anchors = [
            LabelledAnchor(field=d.field, line_no=d.line_no, anchor=d.anchor)
            for d in copy.differences
        ]
        sources.append(_Source(message_id, copy.attachment_id, copy.attachment_sha256, anchors))
    return sources


def _quote_anchors(case: QuoteCase, attachment_id: str) -> list[LabelledAnchor]:
    document = case.request.document
    found: list[LabelledAnchor] = []
    request_file = case.request.attachment
    if request_file is not None and attachment_id == request_file.attachment_id:
        header = {
            "rfq_no": document.rfq_no,
            "rfq_date": document.rfq_date,
            "currency": document.currency,
            "quote_due": document.quote_due,
            "buyer": document.buyer,
        }
        found += [
            LabelledAnchor(field=k, anchor=v.source)
            for k, v in header.items()
            if v is not None and v.source.attachment_id == attachment_id
        ]
        for item in document.items:
            fields = {
                "customer_item_code": item.customer_item_code,
                "description": item.description,
                "quantity": item.quantity,
                "uom": item.uom,
                "target_price": item.target_price,
                "stated_target_price": item.stated_target_price,
                "needed_by": item.needed_by,
            }
            # A request a model read may hold values from the message's own
            # text beside the file's: only the file's are on it.
            found += [
                LabelledAnchor(field=k, line_no=item.line_no, anchor=v.source)
                for k, v in fields.items()
                if v is not None and v.source.attachment_id == attachment_id
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
        key=lambda r: (r.attachment_id or "", r.page or 0, r.sheet or ""),
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


def value_region(case: QuoteCase, line_no: int | None, field: str) -> SourceRegion | None:
    """Where a value a model read, still to be confirmed, was read: a page or
    sheet of the request's file, or the message's text. None for anything
    else, which the case refuses to confirm on its own, and for an anchor
    that names no page or sheet (nothing can be served for it)."""
    found = next(
        (
            f
            for f in case.findings
            if f.key == (QuoteFindingCode.VALUE_UNCERTAIN, line_no) and f.is_open
        ),
        None,
    )
    if found is None or field not in found.flagged:
        return None
    document = case.request.document
    holder = (
        document
        if line_no is None
        else next((item for item in document.items if item.line_no == line_no), None)
    )
    held = getattr(holder, field, None)
    if not isinstance(held, Sourced):
        return None
    if held.source.attachment_id is None:
        return MESSAGE_TEXT
    return _region(held.source)


def value_unserved(
    case: QuoteCase, line_no: int | None, field: str, served: frozenset[SourceRegion]
) -> SourceRegion | None:
    """The place a value must still be opened at before it is confirmed, by
    whoever was ``served`` these regions of the case's current version; None
    when nothing is asked. What `require_value_served` refuses on, and what
    the case view tells the confirm button (audit gap 2): one answer."""
    region = value_region(case, line_no, field)
    return None if region is None or region in served else region


async def require_value_served(
    work: SalesUnitOfWork,
    principal_id: uuid.UUID,
    case: QuoteCase,
    line_no: int | None,
    field: str,
) -> None:
    """409 "chưa mở nguồn" until ``principal_id`` was served, for the case's
    current version, the place the value was read (`value_unserved`)."""
    if value_region(case, line_no, field) is None:
        return
    served = await work.served.served(principal_id, CaseKind.QUOTE, case.case_id, case.case_version)
    region = value_unserved(case, line_no, field, served)
    if region is None:
        return
    raise ConflictError(
        "chưa mở nguồn: mở nơi giá trị được đọc, ở phiên bản hồ sơ này, trước khi xác nhận",
        details={
            "case_id": str(case.case_id),
            "case_version": case.case_version,
            "rule": "source_not_served",
            "missing": [
                "message_text"
                if region == MESSAGE_TEXT
                else f"{region.attachment_id}:"
                f"{'page ' + str(region.page) if region.page else region.sheet}"
            ],
        },
    )


@dataclass(frozen=True)
class OpenedSources:
    """The pages and sheets of a case's files that were served, each by its
    file's id and sha256: what tells a value someone opened from one nobody
    did (audit gaps 1 and 5). A page of a revision the case no longer reads
    has another sha256, so it never stands for the current file's."""

    regions: frozenset[tuple[str, str, int | None, str | None]]

    @classmethod
    def of(
        cls,
        servings: Iterable[ServedSource],
        *,
        by: uuid.UUID | None = None,
        until: datetime | None = None,
    ) -> OpenedSources:
        """The regions served to ``by`` (anyone when None), no later than
        ``until`` (ever when None). The message's text is no file region."""
        return cls(
            frozenset(
                (s.attachment_id, s.attachment_sha256, s.page, s.sheet)
                for s in servings
                if s.attachment_id is not None
                and (by is None or s.principal_id == by)
                and (until is None or s.served_at <= until)
            )
        )

    def holds(self, anchor: SourceAnchor) -> bool:
        """Whether the page or sheet ``anchor`` points into was served. An
        anchor that names neither cannot have been."""
        region = _region(anchor)
        if region is None or region.attachment_id is None:
            return False
        key = (region.attachment_id, anchor.attachment_sha256, region.page, region.sheet)
        return key in self.regions


NOTHING_OPENED: Final = OpenedSources(frozenset())


class UnopenedValue(BaseModel):
    """A value of the order nobody was served the page or sheet of."""

    model_config = _VIEW

    field: str
    # None: a value of the PO as a whole (the header, the buyer, the total).
    line_no: int | None = None


def unopened_values(case: OrderCase, opened: OpenedSources) -> list[UnopenedValue]:
    """Every value the order reads whose page or sheet ``opened`` does not
    hold, in the order the source view labels them (`_order_anchors`)."""
    return [
        UnopenedValue(field=labelled.field, line_no=labelled.line_no)
        for labelled in _order_anchors(case.document)
        if not opened.holds(labelled.anchor)
    ]


# ------------------------------------------------------------------ service --


@dataclass(frozen=True, slots=True)
class _Source:
    message_id: str
    attachment_id: str
    sha256: str
    anchors: list[LabelledAnchor]


def _quote_sources(case: QuoteCase) -> list[_Source]:
    """The files a quote was read from: the request's, and each Design reply's."""
    request_file = case.request.attachment
    files = [(case.request.message_id, request_file)] if request_file is not None else []
    files += [(reply.message_id, reply.attachment) for reply in case.design_replies]
    return [
        _Source(
            message_id,
            attachment.attachment_id,
            attachment.sha256,
            _quote_anchors(case, attachment.attachment_id),
        )
        for message_id, attachment in files
    ]


# How many pages or sheets DW1 reads ahead for one case: the ones its values
# sit on, first come first, so a long workbook does not fill the cache.
WARM_MAX_REGIONS: Final = 6


@dataclass(frozen=True)
class SourceService:
    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    inbox: InboxPort
    files: SourceViewPort
    cache: SourceCachePort

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
                source
                for message_id, d in revisions
                for source in _order_sources(message_id, d)
                if source.attachment_id == attachment_id
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
        found = next((s for s in _quote_sources(case) if s.attachment_id == attachment_id), None)
        return await self._serve(
            context, CaseKind.QUOTE, case_id, case.case_version, found, attachment_id, page, sheet
        )

    async def quote_message_text(
        self, context: AccessContext, case_id: uuid.UUID
    ) -> MessageTextView:
        """The message's text a model read the request from, served and
        recorded like a page of a file: what confirming a value read from it
        requires (`require_value_served`)."""
        await self._authorize(context, "sales_quote_case", case_id)
        scope, now = sales_scope(context), self.clock.now()
        async with self.uow(scope) as work:
            case = (await stored_quote(work, case_id)).case
            body = case.request.body
            if body is None:
                raise NotFoundError(
                    "the request was not read from the message's text",
                    details={"case_id": str(case_id)},
                )
            await work.served.record(
                ServedSource(
                    principal_id=context.principal_id,
                    case_kind=CaseKind.QUOTE,
                    case_id=case_id,
                    case_version=case.case_version,
                    attachment_id=None,
                    attachment_sha256=body.sha256,
                    served_at=now,
                )
            )
            await work.commit()
        return MessageTextView(
            case_id=case_id,
            case_version=case.case_version,
            text=body.text,
            sha256=body.sha256,
            served_at=now,
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
            opened = await self._pdf_page(scope, source.sha256, content.data, page)
            if opened is None:
                raise NotFoundError("the file has no such page", details={**details, "page": page})
            pdf_base64, count = opened
            view = SourceView(
                case_kind=case_kind,
                case_id=case_id,
                case_version=case_version,
                attachment_id=attachment_id,
                attachment_sha256=source.sha256,
                kind="pdf",
                page=page,
                page_count=count,
                pdf_base64=pdf_base64,
                anchors=[a for a in source.anchors if a.anchor.page == page],
                served_at=now,
            )
        elif kind == "xlsx" and sheet is not None:
            grid = await self._sheet_grid(scope, source.sha256, content.data, sheet)
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
                sheets=grid.sheets,
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

    async def warm(self, scope: SalesScope, case: OrderCase | QuoteCase) -> None:
        """Reads the pages and sheets the case's values sit on into the cache
        as DW1 opens or revises it, so whoever opens its source next finds it
        there (2026-10-28). Nobody is recorded as served: a page read ahead is
        a kept parse, never evidence that a person looked at it."""
        sources = (
            _order_sources(case.message_id, case.document)
            if isinstance(case, OrderCase)
            else _quote_sources(case)
        )
        left = WARM_MAX_REGIONS
        for source in sources:
            regions = list(
                dict.fromkeys(
                    (a.anchor.page, a.anchor.sheet)
                    for a in source.anchors
                    if a.anchor.page is not None or a.anchor.sheet is not None
                )
            )[:left]
            if not regions:
                continue
            content = await self.inbox.read_attachment(
                scope, source.message_id, source.attachment_id
            )
            if content is None or content.attachment.sha256 != source.sha256:
                continue
            kind = self.files.kind(content.data)
            for page, sheet in regions:
                if kind == "pdf" and page is not None:
                    await self._pdf_page(scope, source.sha256, content.data, page)
                elif kind == "xlsx" and sheet is not None:
                    await self._sheet_grid(scope, source.sha256, content.data, sheet)
            left -= len(regions)
            if left <= 0:
                return

    async def _pdf_page(
        self, scope: SalesScope, sha256: str, data: bytes, page: int
    ) -> tuple[str, int] | None:
        """The page as base64 and the file's page count, from the cache when
        it holds them; None when the file has no such page."""
        key = source_cache_key(scope, sha256, page=page, sheet=None)
        if (held := await self.cache.get(key)) is not None:
            try:
                cached = _CachedPage.model_validate_json(held)
                return cached.pdf_base64, cached.page_count
            except ValidationError:
                pass  # an entry from another version: read the file
        opened = await self.files.pdf_page(data, page)
        if opened is None:
            return None
        pdf, count = opened
        encoded = base64.b64encode(pdf).decode("ascii")
        await self._keep(key, _CachedPage(pdf_base64=encoded, page_count=count).model_dump_json())
        return encoded, count

    async def _sheet_grid(
        self, scope: SalesScope, sha256: str, data: bytes, sheet: str
    ) -> SheetGrid | None:
        key = source_cache_key(scope, sha256, page=None, sheet=sheet)
        if (held := await self.cache.get(key)) is not None:
            try:
                return SheetGrid.model_validate_json(held)
            except ValidationError:
                pass
        grid = await self.files.sheet_grid(data, sheet)
        if grid is not None:
            await self._keep(key, grid.model_dump_json())
        return grid

    async def _keep(self, key: str, value: str) -> None:
        if len(value) <= SOURCE_CACHE_MAX_CHARS:
            await self.cache.set(key, value, ttl_seconds=SOURCE_CACHE_TTL_SECONDS)

"""The files and drafts of an order case (WIV-03-012), each composed from the case.

One function per artifact kind; `artifacts_service.ORDER_GATES` says when each
may be rendered and downloaded. Every number is the case's: the line as read
(with Sales' confirmed mapping), the check basis stamped when it was checked,
the dates Sales confirmed. A value Sales typed is named with who typed it.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import date
from typing import Final

from dw_kernel.errors import ConflictError
from dw_sales.application.artifact_content import (
    INTERNAL,
    Bound,
    DocumentTemplate,
    EmailTemplate,
    Sheet,
    UploadField,
    Value,
    Workbook,
    column,
    day_text,
    label,
    local_time,
    time_text,
)
from dw_sales.application.drafting import Drafting, Rendered, anchor_text, filled, line_template
from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.catalog import Language
from dw_sales.domain.orders import (
    Accepted,
    AskCustomer,
    CorrectedBySales,
    Finding,
    FindingCode,
    MappingStatus,
    OrderCase,
    OrderLine,
)

type OrderDrafting = Drafting[OrderCase]

# The field a line finding is about: where its PO value was read, and the
# value of the upload file the cross-checker compares it with.
_FIELD_OF: Final[Mapping[FindingCode, str]] = {
    FindingCode.PRICE_MISMATCH: "unit_price",
    FindingCode.CURRENCY_MISMATCH: "unit_price",
    FindingCode.LME_BAND_MISMATCH: "unit_price",
    FindingCode.QUOTATION_MISSING: "unit_price",
    FindingCode.MOQ_VIOLATION: "quantity",
    FindingCode.PACK_MULTIPLE: "quantity",
    FindingCode.UOM_MISMATCH: "uom",
    FindingCode.CODE_UNMAPPED: "prv_code",
    FindingCode.CODE_AMBIGUOUS: "prv_code",
    FindingCode.REQUESTED_DATE_SHORT_LT: "requested_date",
}
# The values a cross-checker compares per line, in the order the sheet lists them.
_CHECKED: Final[tuple[UploadField, ...]] = (
    "customer_item_code",
    "prv_code",
    "description",
    "quantity",
    "uom",
    "unit_price",
    "amount",
    "requested_date",
)
# What a finding was checked against, by the basis it names.
_QUOTATION_BASIS: Final = frozenset(
    {
        FindingCode.PRICE_MISMATCH,
        FindingCode.CURRENCY_MISMATCH,
        FindingCode.LME_BAND_MISMATCH,
        FindingCode.QUOTATION_MISSING,
    }
)
_ITEM_BASIS: Final = frozenset(
    {FindingCode.MOQ_VIOLATION, FindingCode.PACK_MULTIPLE, FindingCode.UOM_MISMATCH}
)
_CONVERT_BASIS: Final = frozenset({FindingCode.CODE_UNMAPPED, FindingCode.CODE_AMBIGUOUS})


# ------------------------------------------------------------------ values --


def upload_values(case: OrderCase, line: OrderLine) -> dict[UploadField, Value]:
    """What the upload file holds for ``line``: the line as read, the PRV code
    Sales mapped it to, and DW1's suggested date. The one source of the upload
    value, for the upload file and the cross-check sheet alike."""
    if line.mapping.prv_code is None:
        raise ConflictError(
            "dòng chưa có mã PRV",
            details={"case_id": str(case.case_id), "line": line.line_no},
        )
    header, po = case.header, line.po_line
    return {
        "customer_code": case.customer_code,
        "po_no": header.po_no,
        "revision": header.revision,
        "po_date": header.po_date,
        "currency": header.currency,
        "line_no": po.line_no,
        "customer_item_code": po.customer_item_code,
        "prv_code": line.mapping.prv_code,
        "description": po.description,
        "quantity": po.quantity,
        "uom": po.uom,
        "unit_price": po.unit_price,
        "amount": po.amount,
        "requested_date": po.requested_date,
        "suggested_delivery_date": line.suggested_delivery_date,
    }


def _po_value(line: OrderLine, field: str) -> Value:
    """The value as the PO prints it; Sales' PRV code is none of the PO's."""
    return None if field == "prv_code" else getattr(line.po_line, field)


def _anchor(line: OrderLine, field: str) -> SourceAnchor:
    anchors = line.po_line.anchors
    return anchors.customer_item_code if field == "prv_code" else getattr(anchors, field)


def _finding_anchor(case: OrderCase, finding: Finding) -> SourceAnchor | None:
    if finding.line_no is None:
        total = case.document.total
        return total.anchor if total is not None else None
    field = _FIELD_OF.get(finding.code, "line_no")
    return _anchor(case.line(finding.line_no), field)


def _flagged(line: OrderLine) -> frozenset[str]:
    return frozenset(flag.field for flag in line.po_line.flags)


def _line_findings(case: OrderCase, line: OrderLine, field: str) -> list[Finding]:
    found = []
    for finding in case.findings:
        if finding.line_no != line.line_no:
            continue
        if _FIELD_OF.get(finding.code) == field or (
            finding.code is FindingCode.VALUE_UNCERTAIN and field in _flagged(line)
        ):
            found.append(finding)
    return found


def _confirmed_date(case: OrderCase, line: OrderLine) -> date:
    """The date Sales confirmed for the line; a draft without one is refused."""
    if line.confirmed_delivery_date is None:
        raise ConflictError(
            "chưa có ngày giao xác nhận cho mọi dòng",
            details={
                "case_id": str(case.case_id),
                "line": line.line_no,
                "reason": "confirmed_date_missing",
            },
        )
    return line.confirmed_delivery_date


def _require_channel(d: OrderDrafting, channel: str) -> None:
    if d.customer.confirmation_channel != channel:
        raise ConflictError(
            "khách hàng xác nhận đơn qua kênh khác",
            details={
                "case_id": str(d.case.case_id),
                "confirmation_channel": d.customer.confirmation_channel,
                "reason": "confirmation_channel",
            },
        )


def _people_line(d: OrderDrafting, user_id: uuid.UUID | None) -> str | None:
    return d.people.name(user_id) if user_id is not None else None


# ------------------------------------------------------------- the kinds --


def bravo_upload(d: OrderDrafting) -> tuple[Rendered, ...]:
    """O3: the file the PIC imports into Bravo, in the MOCK template's layout,
    and a second sheet that says it is a MOCK."""
    case, layout = d.case, d.copy.upload
    doc = d.internal("bravo_upload")
    rows = tuple(
        tuple(upload_values(case, line)[c.field] for c in layout.columns) for line in case.lines
    )
    upload = Sheet(
        name=layout.sheet_name, columns=tuple(c.header for c in layout.columns), rows=rows
    )
    about = Sheet(
        name=label(doc, "sheet"),
        title=doc.template.title,
        heading=d.stamp(layout.version),
        columns=(),
        rows=(),
        notes=(doc.word("mock", layout=layout.version),) if layout.mock else (),
    )
    return (d.xlsx(layout.version, Workbook((upload, about), INTERNAL, d.at)),)


def cross_check_sheet(d: OrderDrafting) -> tuple[Rendered, ...]:
    """O9: per line and value, the PO value, its anchor, the upload value, the
    findings and their disposition, and who typed a value by hand; with the
    Bravo sales-order number and who recorded it."""
    case = d.case
    doc = d.internal("cross_check_sheet")
    rows: list[tuple[Value, ...]] = []
    for line in case.lines:
        upload = upload_values(case, line)
        for field in _CHECKED:
            findings = _line_findings(case, line, field)
            typed = [
                f.disposition.by for f in findings if isinstance(f.disposition, CorrectedBySales)
            ]
            confirmed_by = line.mapping.confirmed_by
            if field == "prv_code" and line.mapping.hand_entered and confirmed_by is not None:
                typed.append(confirmed_by)
            rows.append(
                (
                    line.line_no,
                    column(doc, field),
                    _po_value(line, field),
                    anchor_text(_anchor(line, field)),
                    upload[field],
                    ", ".join(f.code.value for f in findings) or None,
                    "; ".join(_disposition_text(doc, f) for f in findings) or None,
                    ", ".join(sorted({d.people.name(by) for by in typed})) or None,
                )
            )
    heading: tuple[tuple[str, Value], ...] = (
        (label(doc, "customer"), f"{case.customer_code} — {d.customer.name}"),
        (label(doc, "po_no"), case.header.po_no),
        (label(doc, "revision"), case.header.revision),
        (label(doc, "bravo_so_no"), case.bravo_so_no),
        (label(doc, "bravo_recorded_by"), _people_line(d, case.bravo_recorded_by)),
        (
            label(doc, "bravo_recorded_at"),
            time_text(case.bravo_recorded_at, INTERNAL) if case.bravo_recorded_at else None,
        ),
        (label(doc, "prepared_by"), _people_line(d, case.prepared_by)),
    )
    sheet = Sheet(
        name=label(doc, "sheet"),
        title=doc.template.title,
        heading=heading + d.stamp(doc.ref),
        columns=tuple(
            column(doc, key)
            for key in (
                "line_no",
                "field",
                "po_value",
                "anchor",
                "upload_value",
                "findings",
                "disposition",
                "typed_by",
            )
        ),
        rows=tuple(rows),
    )
    return (d.xlsx(doc.ref, Workbook((sheet,), INTERNAL, d.at)),)


def _disposition_text(doc: Bound[DocumentTemplate], finding: Finding) -> str:
    disposition = finding.disposition
    word = doc.word(f"disposition.{disposition.kind.value}")
    if isinstance(disposition, Accepted):
        return f"{finding.code.value}: {word} ({disposition.reason})"
    if isinstance(disposition, CorrectedBySales):
        return f"{finding.code.value}: {word} {disposition.value} ({disposition.source})"
    return f"{finding.code.value}: {word}"


def confirmation_draft(d: OrderDrafting) -> tuple[Rendered, ...]:
    """O10: the confirmation to the customer, naming the PIC who prepared it and
    the colleague who cross-checked it, with the date Sales confirmed per line."""
    case = d.case
    _require_channel(d, "email")
    bound, draft = d.customer_email("confirmation_draft")
    language = d.language
    lines = [
        bound.fill(
            line_template(bound),
            {
                "line_no": line.line_no,
                "customer_item_code": line.po_line.customer_item_code,
                "prv_code": line.mapping.prv_code,
                "description": line.po_line.description,
                "quantity": line.po_line.quantity,
                "uom": line.po_line.uom,
                "unit_price": line.po_line.unit_price,
                "currency": case.header.currency,
                "confirmed_date": day_text(_confirmed_date(case, line), language),
            },
        )
        for line in case.lines
    ]
    values = {
        **_order_values(d, language),
        "lines": "\n".join(lines),
        "pic": _people_line(d, case.prepared_by),
        "checker": (
            d.people.name(case.cross_checked_by)
            if case.cross_checked_by is not None
            else bound.word("no_cross_check")
        ),
    }
    return (d.eml(bound.ref, filled(bound, draft, values)),)


def portal_checklist(d: OrderDrafting) -> tuple[Rendered, ...]:
    """O10 for a customer who confirms on their own portal: what to enter there,
    line by line, with a column to tick."""
    case = d.case
    _require_channel(d, "portal")
    doc = d.internal("portal_checklist")
    keys = (
        "line_no",
        "customer_item_code",
        "prv_code",
        "quantity",
        "uom",
        "unit_price",
        "currency",
        "confirmed_date",
        "entered",
    )
    rows = tuple(
        (
            line.line_no,
            line.po_line.customer_item_code,
            line.mapping.prv_code,
            line.po_line.quantity,
            line.po_line.uom,
            line.po_line.unit_price,
            case.header.currency,
            _confirmed_date(case, line),
            None,
        )
        for line in case.lines
    )
    heading: tuple[tuple[str, Value], ...] = (
        (label(doc, "customer"), f"{case.customer_code} — {d.customer.name}"),
        (label(doc, "po_no"), case.header.po_no),
        (label(doc, "revision"), case.header.revision),
        (label(doc, "bravo_so_no"), case.bravo_so_no),
        (label(doc, "pic"), _people_line(d, case.prepared_by)),
        (label(doc, "checker"), _people_line(d, case.cross_checked_by)),
    )
    sheet = Sheet(
        name=label(doc, "sheet"),
        title=doc.template.title,
        heading=heading + d.stamp(doc.ref),
        columns=tuple(column(doc, key) for key in keys),
        rows=rows,
    )
    return (d.xlsx(doc.ref, Workbook((sheet,), INTERNAL, d.at)),)


def correction_request(d: OrderDrafting) -> tuple[Rendered, ...]:
    """O8: exactly the findings Sales sends back to the customer, each with the
    value on the PO, the value expected and what it was checked against."""
    case = d.case
    asked = [f for f in case.findings if isinstance(f.disposition, AskCustomer)]
    if not asked:
        raise ConflictError(
            "không có điểm nào cần khách sửa",
            details={"case_id": str(case.case_id), "reason": "nothing_asked"},
        )
    bound, draft = d.customer_email("correction_request")
    lines = [
        bound.fill(
            line_template(bound),
            {
                "line": (
                    bound.word("line", line_no=f.line_no)
                    if f.line_no is not None
                    else bound.word("whole_po")
                ),
                "finding": bound.word(f"finding.{f.code.value}"),
                "po_value": f.actual,
                "expected": f.expected,
                "basis": _basis_text(bound, case, f),
                "anchor": anchor_text(_finding_anchor(case, f)),
            },
        )
        for f in asked
    ]
    values = {**_order_values(d, d.language), "lines": "\n".join(lines)}
    return (d.eml(bound.ref, filled(bound, draft, values)),)


def _basis_text(bound: Bound[EmailTemplate], case: OrderCase, finding: Finding) -> str:
    basis = case.line(finding.line_no).basis if finding.line_no is not None else None
    if finding.code in _QUOTATION_BASIS:
        quotation = basis.quotation if basis is not None else None
        if quotation is None:
            return bound.word("basis.no_quotation")
        return bound.word("basis.quotation", quote_no=quotation.quote_no)
    if finding.code in _ITEM_BASIS and basis is not None and basis.item is not None:
        return bound.word("basis.item", prv_code=basis.item.prv_code)
    if finding.code in _CONVERT_BASIS:
        return bound.word("basis.convert_list")
    return bound.word("basis.document")


def change_summary(d: OrderDrafting) -> tuple[Rendered, ...]:
    """A revision of an order already in Bravo: what changed, line by line, for
    the PIC to apply in Bravo. No new upload file is made for it."""
    case = d.case
    doc = d.internal("change_summary")
    rows = tuple(
        (change.line_no, column(doc, change.field), change.before, change.after)
        for change in case.changes
    )
    heading: tuple[tuple[str, Value], ...] = (
        (label(doc, "customer"), f"{case.customer_code} — {d.customer.name}"),
        (label(doc, "po_no"), case.header.po_no),
        (label(doc, "revision"), case.header.revision),
        (label(doc, "bravo_so_no"), case.bravo_so_no),
    )
    sheet = Sheet(
        name=label(doc, "sheet"),
        title=doc.template.title,
        heading=heading + d.stamp(doc.ref),
        columns=tuple(column(doc, key) for key in ("line_no", "field", "before", "after")),
        rows=rows,
    )
    return (d.xlsx(doc.ref, Workbook((sheet,), INTERNAL, d.at)),)


def convert_list_proposal(d: OrderDrafting) -> tuple[Rendered, ...]:
    """O2: the convert-list rows Sales confirmed, proposed for the list's owner.
    Nothing here writes the list itself."""
    case = d.case
    doc = d.internal("convert_list_proposal")
    rows = tuple(
        (
            case.customer_code,
            d.customer.name,
            line.po_line.customer_item_code,
            line.mapping.prv_code,
            _people_line(d, line.mapping.confirmed_by),
            local_time(line.mapping.confirmed_at).date() if line.mapping.confirmed_at else None,
        )
        for line in case.lines
        if line.mapping.status is MappingStatus.CANDIDATE_CONFIRMED
    )
    keys = ("customer_code", "customer", "customer_item_code", "prv_code", "confirmed_by", "date")
    sheet = Sheet(
        name=label(doc, "sheet"),
        title=doc.template.title,
        heading=((label(doc, "po_no"), case.header.po_no), *d.stamp(doc.ref)),
        columns=tuple(column(doc, key) for key in keys),
        rows=rows,
        notes=(doc.word("mock"),) if d.copy.documents.mock else (),
    )
    return (d.xlsx(doc.ref, Workbook((sheet,), INTERNAL, d.at)),)


def design_code_request(d: OrderDrafting) -> tuple[Rendered, ...]:
    """ "Cần Design tạo mã": the lines no convert entry and no attribute match
    could map, for Design to create a code."""
    case = d.case
    unmapped = {f.line_no for f in case.findings if f.code is FindingCode.CODE_UNMAPPED}
    waiting = [
        line
        for line in case.lines
        if line.line_no in unmapped and line.mapping.status is MappingStatus.UNMAPPED
    ]
    bound, draft = d.design_email("design_code_request", INTERNAL)
    lines = [
        bound.fill(
            line_template(bound),
            {
                "line_no": line.line_no,
                "customer_item_code": line.po_line.customer_item_code,
                "description": line.po_line.description,
                "quantity": line.po_line.quantity,
                "uom": line.po_line.uom,
                "requested_date": day_text(line.po_line.requested_date, INTERNAL),
            },
        )
        for line in waiting
    ]
    values = {**_order_values(d, INTERNAL), "lines": "\n".join(lines)}
    return (d.eml(bound.ref, filled(bound, draft, values)),)


def cannot_supply_draft(d: OrderDrafting) -> tuple[Rendered, ...]:
    """The order Sales closed as one the company cannot supply, told to the customer."""
    case = d.case
    bound, draft = d.customer_email("cannot_supply_draft")
    lines = [
        bound.fill(
            line_template(bound),
            {
                "line_no": line.line_no,
                "customer_item_code": line.po_line.customer_item_code,
                "description": line.po_line.description,
                "quantity": line.po_line.quantity,
                "uom": line.po_line.uom,
            },
        )
        for line in case.lines
    ]
    values = {**_order_values(d, d.language), "lines": "\n".join(lines)}
    return (d.eml(bound.ref, filled(bound, draft, values)),)


# ---------------------------------------------------------------- helpers --


def _order_values(d: OrderDrafting, language: Language) -> dict[str, object]:
    case = d.case
    return {
        "customer_code": case.customer_code,
        "customer_name": d.customer.name,
        "po_no": case.header.po_no,
        "revision": case.header.revision,
        "po_date": day_text(case.header.po_date, language),
        "currency": case.header.currency,
        "bravo_so_no": case.bravo_so_no,
    }

"""The files and drafts of an order case (WIV-03-012), each composed from the case.

One function per artifact kind; `artifacts_service.ORDER_GATES` says when each
may be rendered and downloaded. Every number is the case's: the line as it is
entered (each value as read, or as Sales corrected it, with Sales' confirmed
mapping), the check basis stamped when it was checked, the dates Sales
confirmed. A value Sales typed is named with who typed it.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from dw_kernel.errors import ConflictError
from dw_sales.application.artifact_content import (
    INTERNAL,
    Bound,
    BravoUploadLayout,
    DocumentTemplate,
    EmailTemplate,
    Sheet,
    UploadColumn,
    UploadField,
    Value,
    Workbook,
    column,
    day_text,
    label,
    time_text,
)
from dw_sales.application.drafting import Drafting, Rendered, anchor_text, filled, line_template
from dw_sales.application.local_time import local_day
from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.catalog import Customer, Language
from dw_sales.domain.orders import (
    TOTAL_FIELD,
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
# The PO's own values a cross-checker compares, when its `value_uncertain`
# flagged them, before the lines.
_HEADER_CHECKED: Final[tuple[str, ...]] = ("po_no", "revision", "po_date", "currency", TOTAL_FIELD)
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
    """What the upload file holds for ``line``: the line and the header as
    entered (a value Sales corrected replaces the value as read), the PRV code
    Sales mapped it to, and DW1's suggested date. The one source of the upload
    value, for the upload file and the cross-check sheet alike."""
    if line.mapping.prv_code is None:
        raise ConflictError(
            "dòng chưa có mã PRV",
            details={"case_id": str(case.case_id), "line": line.line_no},
        )
    header, po = case.effective_header, line.effective
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


def upload_rows(case: OrderCase, line: OrderLine) -> tuple[dict[UploadField, Value], ...]:
    """The upload file's rows for ``line``: one per delivery schedule (ticket
    21). A line printing one quantity and one date is one row, its values
    `upload_values`'. A line whose PO prints its schedules is a row per
    schedule, each with the schedule's quantity and date, DW1's suggestion for
    that date, and its amount as the quantity times the unit price: the PO
    prints no amount per schedule."""
    values = upload_values(case, line)
    po = line.effective
    if not po.prints_schedules:
        return (values,)
    return tuple(
        {
            **values,
            "quantity": schedule.quantity,
            "amount": schedule.quantity * po.unit_price,
            "requested_date": schedule.requested_date,
            "suggested_delivery_date": line.suggested_date(schedule),
        }
        for schedule in po.schedules
    )


def _po_value(line: OrderLine, field: str) -> Value:
    """The value as the PO prints it; Sales' PRV code is none of the PO's."""
    return None if field == "prv_code" else getattr(line.po_line, field)


def _corrected_value(line: OrderLine, field: str) -> Value:
    """The value Sales typed for a flagged field, as its type; None otherwise."""
    return getattr(line.effective, field) if line.correction(field) is not None else None


def _anchor(line: OrderLine, field: str) -> SourceAnchor:
    anchors = line.po_line.anchors
    return anchors.customer_item_code if field == "prv_code" else getattr(anchors, field)


def _finding_anchor(case: OrderCase, finding: Finding) -> SourceAnchor | None:
    if finding.code is FindingCode.LEGACY_ENCODING:
        legacy = case.document.first_legacy_text()
        return legacy[0] if legacy is not None else None
    if finding.line_no is None:
        total = case.document.total
        return total.anchor if total is not None else None
    field = _FIELD_OF.get(finding.code, "line_no")
    return _anchor(case.line(finding.line_no), field)


def _line_findings(case: OrderCase, line: OrderLine, field: str) -> list[Finding]:
    found = []
    for finding in case.findings:
        if finding.line_no != line.line_no:
            continue
        if _FIELD_OF.get(finding.code) == field or (
            finding.code is FindingCode.VALUE_UNCERTAIN and field in line.po_line.flagged
        ):
            found.append(finding)
    return found


def _confirmed(case: OrderCase, line: OrderLine) -> tuple[tuple[Decimal, date], ...]:
    """Each delivery of the line with the date Sales confirmed for it: a
    split line's schedules, each its quantity (ticket 35), or the line's
    quantity on its one date. A draft without them is refused."""
    if not line.confirmed_delivery_dates:
        raise ConflictError(
            "chưa có ngày giao xác nhận cho mọi dòng",
            details={
                "case_id": str(case.case_id),
                "line": line.line_no,
                "reason": "confirmed_date_missing",
            },
        )
    if schedules := line.confirmed_schedules():
        return tuple((schedule.quantity, day) for schedule, day in schedules)
    (day,) = line.confirmed_delivery_dates
    return ((line.effective.quantity, day),)


def _confirmed_text(
    bound: Bound[EmailTemplate], case: OrderCase, line: OrderLine, language: Language
) -> str:
    """The line's confirmed date, or a split line's schedules one by one."""
    deliveries = _confirmed(case, line)
    if not line.confirmed_schedules():
        return day_text(deliveries[0][1], language)
    listed = "; ".join(
        bound.word(
            "schedule",
            quantity=quantity,
            uom=line.effective.uom,
            confirmed_date=day_text(day, language),
        )
        for quantity, day in deliveries
    )
    return bound.word("schedules", count=len(deliveries), schedules=listed)


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
    """O3: the file the PIC pastes into Bravo, in the tenant's layout, and a
    second sheet naming the case version and the layout (and saying so where
    the layout is a MOCK).

    A row per delivery (`upload_rows`): a line the PO splits over several
    dates is a row per date, each its own number, the line's PO line, its
    quantity and its date. Each column holds what its source says
    (`_cell`); a blank column holds nothing. Before the file is made, every
    row is checked (`_checked_row`)."""
    case, layout = d.case, d.upload
    doc = d.internal("bravo_upload")
    received = local_day(case.received_at, d.copy.zone)
    deliveries = (row for line in case.lines for row in upload_rows(case, line))
    rows = []
    for number, delivery in enumerate(deliveries, start=1):
        values: dict[UploadField, Value] = {
            **delivery,
            "row_no": number,
            "received_date": received,
            "usd_rate": 1 if delivery["currency"] == "USD" else None,
        }
        row = tuple(_cell(column, values, d.customer) for column in layout.columns)
        rows.append(_checked_row(layout, values, row))
    upload = Sheet(
        name=layout.sheet_name,
        columns=tuple(c.header for c in layout.columns),
        rows=tuple(rows),
        banner=layout.banner,
        formats=tuple(c.number_format for c in layout.columns),
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


def _cell(column: UploadColumn, values: Mapping[UploadField, Value], customer: Customer) -> Value:
    """What one column holds in one row: the field's value, the customer's
    own value, the fixed text, or nothing in a blank column."""
    if column.field is not None:
        return values[column.field]
    if column.customer is not None:
        value: Value = getattr(customer, column.customer)
        return value
    return column.constant


def _checked_row(
    layout: BravoUploadLayout, values: Mapping[UploadField, Value], row: tuple[Value, ...]
) -> tuple[Value, ...]:
    """``row``, once it passes what is checked before the file is made
    (ticket 02): an amount the file carries is the quantity times the unit
    price, at the places the amount is written with; and no number holds more
    decimal places than its column's format shows, since a paste copies what
    the cell shows and a hidden place would reach Bravo rounded."""
    line = values["line_no"]
    if "amount" in layout.fields and not _amount_holds(values):
        raise ConflictError(
            "thành tiền của dòng khác số lượng nhân đơn giá: kiểm lại dòng trước khi tạo tệp",
            details={"line": line, "reason": "upload_amount_mismatch"},
        )
    for at, value in zip(layout.columns, row, strict=True):
        shown = _places_shown(at.number_format)
        if shown is not None and isinstance(value, int | Decimal) and _places(value) > shown:
            raise ConflictError(
                "một số có nhiều số lẻ hơn định dạng cột hiển thị: dán vào Bravo sẽ bị làm tròn",
                details={"line": line, "column": at.header, "reason": "upload_value_rounded"},
            )
    return row


def _amount_holds(values: Mapping[UploadField, Value]) -> bool:
    quantity, price, amount = values["quantity"], values["unit_price"], values["amount"]
    assert isinstance(quantity, Decimal) and isinstance(price, Decimal)  # a line's, typed so
    assert isinstance(amount, Decimal)
    places = Decimal(1).scaleb(min(_exponent(amount), 0))
    return (quantity * price).quantize(places, rounding=ROUND_HALF_UP) == amount


def _exponent(value: Decimal) -> int:
    exponent = value.as_tuple().exponent
    assert isinstance(exponent, int)  # a finite amount
    return exponent


def _places(value: int | Decimal) -> int:
    return 0 if isinstance(value, int) else max(0, -_exponent(value.normalize()))


# What an Excel number format prints literally: quoted text, a bracketed
# colour or locale, an escaped character.
_FORMAT_LITERAL: Final = re.compile(r'"[^"]*"|\[[^\]]*\]|\\.')


def _places_shown(number_format: str | None) -> int | None:
    """How many decimal places a number format shows a positive number with;
    None for a format that shows no number (text, a date) or for none."""
    if number_format is None:
        return None
    positive = _FORMAT_LITERAL.sub("", number_format.split(";")[0])
    if not re.search(r"[0#]", positive):
        return None
    _, dot, decimals = positive.partition(".")
    return len(re.match(r"[0#]*", decimals).group()) if dot else 0  # type: ignore[union-attr]


def cross_check_sheet(d: OrderDrafting) -> tuple[Rendered, ...]:
    """O9: per line and value, the PO value, its anchor, the upload value, the
    findings and their disposition, and who typed a value by hand; with the
    Bravo sales-order number and who recorded it."""
    case = d.case
    doc = d.internal("cross_check_sheet")
    rows: list[tuple[Value, ...]] = _header_rows(d, doc)
    for line in case.lines:
        upload = upload_values(case, line)
        for field in _CHECKED:
            findings = _line_findings(case, line, field)
            # A value_uncertain is typed field by field: its own corrections
            # name who typed which value, not who resolved the finding.
            typed = [
                f.disposition.by
                for f in findings
                if isinstance(f.disposition, CorrectedBySales)
                and f.code is not FindingCode.VALUE_UNCERTAIN
            ]
            if (correction := line.correction(field)) is not None:
                typed.append(correction.by)
            confirmed_by = line.mapping.confirmed_by
            if field == "prv_code" and line.mapping.hand_entered and confirmed_by is not None:
                typed.append(confirmed_by)
            rows.append(
                (
                    line.line_no,
                    column(doc, field),
                    _po_value(line, field),
                    _corrected_value(line, field),
                    anchor_text(_anchor(line, field)),
                    upload[field],
                    ", ".join(f.code.value for f in findings) or None,
                    "; ".join(_disposition_text(doc, f) for f in findings) or None,
                    ", ".join(sorted({d.people.name(by) for by in typed})) or None,
                )
            )
        rows += _schedule_rows(case, line, doc)
    heading: tuple[tuple[str, Value], ...] = (
        (label(doc, "customer"), f"{case.customer_code} — {d.customer.name}"),
        (label(doc, "po_no"), case.header.po_no),
        (label(doc, "revision"), case.header.revision),
        (label(doc, "bravo_so_no"), case.bravo_so_no),
        (label(doc, "bravo_recorded_by"), _people_line(d, case.bravo_recorded_by)),
        (
            label(doc, "bravo_recorded_at"),
            (
                time_text(case.bravo_recorded_at, INTERNAL, d.copy.zone)
                if case.bravo_recorded_at
                else None
            ),
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
                "corrected_value",
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


def _schedule_rows(
    case: OrderCase, line: OrderLine, doc: Bound[DocumentTemplate]
) -> list[tuple[Value, ...]]:
    """A line whose PO prints its schedules: each one as printed, where, and
    as the upload file's row holds it (ticket 21). None for a line printing
    one quantity and one date, whose values above are its one row."""
    if not line.po_line.prints_schedules:
        return []
    printed = line.po_line.schedules
    entered = upload_rows(case, line)
    return [
        (
            line.line_no,
            f"{column(doc, 'schedule')} {number}/{len(printed)}",
            f"{schedule.requested_date.isoformat()}: {schedule.quantity}",
            None,
            anchor_text(schedule.anchor),
            f"{_day_value(row['requested_date'])}: {row['quantity']}",
            None,
            None,
            None,
        )
        for number, (schedule, row) in enumerate(zip(printed, entered, strict=True), start=1)
    ]


def _day_or_dash(day: date | None) -> str:
    return "—" if day is None else day_text(day, INTERNAL)


def _day_value(value: Value) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


def _header_rows(d: OrderDrafting, doc: Bound[DocumentTemplate]) -> list[tuple[Value, ...]]:
    """The PO's own values its `value_uncertain` flagged: as read, as Sales
    typed it, and in the upload file (the total is not in it)."""
    case = d.case
    finding = next(
        (f for f in case.findings if f.code is FindingCode.VALUE_UNCERTAIN and f.line_no is None),
        None,
    )
    if finding is None:
        return []
    flagged = case.flagged_fields(finding)
    header, entered, total = case.header, case.effective_document, case.document.total
    rows: list[tuple[Value, ...]] = []
    for field in _HEADER_CHECKED:
        if field not in flagged:
            continue
        correction = case.header_correction(field)
        if field == TOTAL_FIELD:
            assert total is not None and entered.total is not None  # flagged, so printed
            read, anchor, typed, upload = total.amount, total.anchor, entered.total.amount, None
        else:
            read, anchor = getattr(header, field), getattr(header.anchors, field)
            typed = upload = getattr(entered.header, field)
        rows.append(
            (
                None,
                column(doc, field),
                read,
                typed if correction is not None else None,
                anchor_text(anchor),
                upload,
                finding.code.value,
                _disposition_text(doc, finding),
                d.people.name(correction.by) if correction is not None else None,
            )
        )
    return rows


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
    the colleague who cross-checked it, with the date Sales confirmed per line,
    or per schedule for a line the PO splits (ticket 35)."""
    case = d.case
    _require_channel(d, "email")
    bound, draft = d.customer_email("confirmation_draft")
    language = d.language
    lines = [
        bound.fill(
            line_template(bound),
            {
                "line_no": line.line_no,
                "customer_item_code": line.effective.customer_item_code,
                "prv_code": line.mapping.prv_code,
                "description": line.effective.description,
                "quantity": line.effective.quantity,
                "uom": line.effective.uom,
                "unit_price": line.effective.unit_price,
                "currency": case.effective_header.currency,
                "confirmed_date": _confirmed_text(bound, case, line, language),
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
    line by line, a row per schedule for a line the PO splits (ticket 35),
    with a column to tick."""
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
            line.effective.customer_item_code,
            line.mapping.prv_code,
            quantity,
            line.effective.uom,
            line.effective.unit_price,
            case.effective_header.currency,
            day,
            None,
        )
        for line in case.lines
        for quantity, day in _confirmed(case, line)
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
            line.effective.customer_item_code,
            line.mapping.prv_code,
            _people_line(d, line.mapping.confirmed_by),
            (
                local_day(line.mapping.confirmed_at, d.copy.zone)
                if line.mapping.confirmed_at
                else None
            ),
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
                "customer_item_code": line.effective.customer_item_code,
                "description": line.effective.description,
                "quantity": line.effective.quantity,
                "uom": line.effective.uom,
                # A line printed with no date (ticket 34) says so with a dash.
                "requested_date": _day_or_dash(line.effective.requested_date),
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
                "customer_item_code": line.effective.customer_item_code,
                "description": line.effective.description,
                "quantity": line.effective.quantity,
                "uom": line.effective.uom,
            },
        )
        for line in case.lines
    ]
    values = {**_order_values(d, d.language), "lines": "\n".join(lines)}
    return (d.eml(bound.ref, filled(bound, draft, values)),)


# ---------------------------------------------------------------- helpers --


def _order_values(d: OrderDrafting, language: Language) -> dict[str, object]:
    case = d.case
    header = case.effective_header
    return {
        "customer_code": case.customer_code,
        "customer_name": d.customer.name,
        "po_no": header.po_no,
        "revision": header.revision,
        "po_date": day_text(header.po_date, language),
        "currency": header.currency,
        "bravo_so_no": case.bravo_so_no,
    }

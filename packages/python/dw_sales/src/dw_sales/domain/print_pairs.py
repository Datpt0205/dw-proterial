"""A workbook PO and its PDF print in one mail are one PO (ticket 34).

Some customers attach the ``.xlsx`` and a PDF print of the same PO to one
mail. Read one by one they are two POs: the second a `duplicate_po`, or a
second case when the two differ by rounding. They are one, and the workbook is
the source of record: the PO is read from it, the print is kept beside it
(`PrintCopy`), and each value the print shows differently is flagged on the
workbook's value (`print_differs`), so the case raises `value_uncertain` on
exactly that value for Sales to confirm or correct, as for any other flag.

Two documents are one PO when they name the same PO number and revision and
print the same line numbers. The customer is the same by construction: both
were read for the customer the mail came from. Anything else is two documents,
which Sales sorts out as before (`order_intake`). Nothing here reads a file.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterator

from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.orders import (
    TOTAL_FIELD,
    FlaggedValue,
    PoDocument,
    PoLine,
    PrintCopy,
    PrintDifference,
    RegionFlag,
    schedules_text,
)

# The line values compared, each as the reader typed it; a split line's
# schedules are compared as their text and flag its requested date, which is
# where a schedule's flags go (ticket 21).
_LINE_FIELDS = ("customer_item_code", "description", "quantity", "uom", "unit_price", "amount")
_HEADER_FIELDS = ("po_date", "currency")
_DIFFERS = RegionFlag.PRINT_DIFFERS


def one_po(workbook: PoDocument, printed: PoDocument) -> PoDocument | None:
    """``workbook`` with ``printed`` kept as its print and every value the
    print shows differently flagged; None when the two are not one PO."""
    if (workbook.header.po_no, workbook.header.revision) != (
        printed.header.po_no,
        printed.header.revision,
    ):
        return None
    if [line.line_no for line in workbook.lines] != [line.line_no for line in printed.lines]:
        return None
    differences = [
        *_header_differences(workbook, printed),
        *(
            difference
            for ours, theirs in zip(workbook.lines, printed.lines, strict=True)
            for difference in _line_differences(ours, theirs)
        ),
        *_total_differences(workbook, printed),
    ]
    copy = PrintCopy(
        attachment_id=printed.attachment_id,
        attachment_sha256=printed.attachment_sha256,
        parser_version=printed.parser_version,
        differences=tuple(differences),
    )
    return _flagged(workbook, differences).model_copy(update={"print_copy": copy})


def _header_differences(workbook: PoDocument, printed: PoDocument) -> Iterator[PrintDifference]:
    for field in _HEADER_FIELDS:
        if getattr(workbook.header, field) != getattr(printed.header, field):
            yield PrintDifference(field=field, anchor=getattr(printed.header.anchors, field))


def _line_differences(ours: PoLine, theirs: PoLine) -> Iterator[PrintDifference]:
    def at(field: str) -> SourceAnchor:
        anchor: SourceAnchor = getattr(theirs.anchors, field)
        return anchor

    for field in _LINE_FIELDS:
        if _same(getattr(ours, field)) != _same(getattr(theirs, field)):
            yield PrintDifference(line_no=ours.line_no, field=field, anchor=at(field))
    dates_differ = ours.requested_date != theirs.requested_date
    if dates_differ or schedules_text(ours) != schedules_text(theirs):
        yield PrintDifference(
            line_no=ours.line_no, field="requested_date", anchor=at("requested_date")
        )


def _total_differences(workbook: PoDocument, printed: PoDocument) -> Iterator[PrintDifference]:
    """The total, when both print one: a total only one prints is no value
    the other contradicts."""
    ours, theirs = workbook.total, printed.total
    if ours is not None and theirs is not None and ours.amount != theirs.amount:
        yield PrintDifference(field=TOTAL_FIELD, anchor=theirs.anchor)


def _same(value: object) -> object:
    """A value as compared: text in one Unicode form, single-spaced and
    casefolded, since a print wraps and sets text its own way; numbers and
    dates as they are."""
    if not isinstance(value, str):
        return value
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _flagged(document: PoDocument, differences: list[PrintDifference]) -> PoDocument:
    def added(existing: tuple[FlaggedValue, ...], fields: list[str]) -> list[FlaggedValue]:
        return [*existing, *(FlaggedValue(field=field, flag=_DIFFERS) for field in fields)]

    header_fields = [d.field for d in differences if d.line_no is None and d.field != TOTAL_FIELD]
    lines = [
        line.model_copy(
            update={
                "flags": tuple(
                    added(
                        line.flags,
                        [d.field for d in differences if d.line_no == line.line_no],
                    )
                )
            }
        )
        for line in document.lines
    ]
    total = document.total
    if total is not None and any(d.field == TOTAL_FIELD for d in differences):
        total = total.model_copy(update={"flags": tuple(added(total.flags, ["amount"]))})
    header = document.header.model_copy(
        update={"flags": tuple(added(document.header.flags, header_fields))}
    )
    return PoDocument.model_validate(
        {**dict(document), "header": header, "lines": tuple(lines), "total": total}
    )

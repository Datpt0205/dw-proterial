"""One PO per PO number: how the files of one mail become its order cases
(tickets 19 and 22).

A mail may carry several POs (customer 1 sends nine in one mail, customer 3
two), and one file may hold several (a customer portal's export prints a PO
number on every row, ticket 18). After every file is read, its lines are
grouped by PO number: a line's own (`PoLine.line_po`) where it prints one,
else its document's (`PoHeader.po_no`). Each PO number is one case.

**A file holding several POs is split** (`per_po`): one document per PO
number, in the order the file first names each, its lines in their order and
numbered 1..n within their PO, as the export numbers its rows; each with its
anchors as read. A part's PO number is read where its first line prints it,
and its date where that line's row prints one (`LinePo.po_date`), else the
file's. The file's printed total is the whole file's, so a part of a split
file has none; its forecast rows (ticket 18) are counted on its first part.

**The same PO number in two files is one PO** (`one_per_po`, ticket 22):
`print_pairs.one_po` keeps the second beside the first and flags every value
they print differently, neither winning. The first is the workbook beside a
PDF (ticket 34), else the file attached first. Two files that are not one PO
(another revision, other line numbers), or three files of one PO number, are
refused with why: Sales sorts them out, as before. PO numbers are compared as
printed, as every other comparison of a PO number is (`check_history`).

Nothing here reads a file or decides a case: the grouping is code's, on what
the readers read.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from dw_sales.domain.orders import PoDocument, PoHeader, PoHeaderAnchors, PoLine
from dw_sales.domain.print_pairs import one_po


@dataclass(frozen=True, slots=True)
class ReadFile:
    """One file's PO as read, with how it was read (``xlsx``, ``pdf``,
    ``csv``…, `order_ports.READ_AS`): a workbook pairs before its print."""

    document: PoDocument
    read_as: str


def po_of(document: PoDocument, line: PoLine) -> str:
    """The PO number ``line`` belongs to: its own, else its document's."""
    return line.line_po.po_no if line.line_po is not None else document.header.po_no


def per_po(document: PoDocument) -> tuple[PoDocument, ...]:
    """``document`` as one document per PO number its lines name (module
    docstring); itself when every line is its header's PO."""
    groups: dict[str, list[PoLine]] = {}
    for line in document.lines:
        groups.setdefault(po_of(document, line), []).append(line)
    if list(groups) == [document.header.po_no]:
        return (document,)
    return tuple(
        _part(document, lines, first=index == 0) for index, lines in enumerate(groups.values())
    )


def _part(document: PoDocument, lines: Sequence[PoLine], *, first: bool) -> PoDocument:
    head = lines[0].line_po
    header = document.header
    anchors = header.anchors
    if head is not None:
        anchors = PoHeaderAnchors(
            po_no=head.anchor,
            revision=head.anchor if anchors.revision == anchors.po_no else anchors.revision,
            po_date=head.po_date_anchor or anchors.po_date,
            currency=anchors.currency,
        )
        header = PoHeader.model_validate(
            {
                **dict(header),
                "po_no": head.po_no,
                "po_date": head.po_date or header.po_date,
                "anchors": anchors,
            }
        )
    numbered = tuple(
        PoLine.model_validate({**dict(line), "line_no": number})
        for number, line in enumerate(lines, start=1)
    )
    return PoDocument.model_validate(
        {
            **dict(document),
            "header": header,
            "lines": numbered,
            "rows_printed": len(numbered),
            "total": None,
            "forecast_rows": document.forecast_rows if first else 0,
        }
    )


def one_per_po(files: Sequence[ReadFile]) -> list[PoDocument] | str:
    """One document per PO number across ``files``, in the order the mail
    first names each (module docstring); or why the files are not, for Sales."""
    groups: dict[str, list[ReadFile]] = {}
    for read in files:
        for part in per_po(read.document):
            groups.setdefault(part.header.po_no, []).append(ReadFile(part, read.read_as))
    documents: list[PoDocument] = []
    for po_no, parts in groups.items():
        if len(parts) == 1:
            documents.append(parts[0].document)
            continue
        ids = ", ".join(p.document.attachment_id or "" for p in parts)
        if len(parts) > 2:
            return f"PO {po_no} is in more than two attachments: {ids}"
        first, second = parts
        if (first.read_as, second.read_as) == ("pdf", "xlsx"):
            # The workbook beside its print (ticket 34).
            first, second = second, first
        paired = one_po(first.document, second.document)
        if paired is None:
            return f"PO {po_no} is in two attachments that print other revisions or lines: {ids}"
        documents.append(paired)
    return documents

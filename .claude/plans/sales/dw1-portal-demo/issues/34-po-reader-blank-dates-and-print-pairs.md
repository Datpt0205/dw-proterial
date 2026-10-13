# 34 — The PO reader reports a blank requested date as a finding, and reads an .xlsx and its PDF print as one PO

Status: ready-for-agent
Blocked by: —
Category: enhancement

Split from ticket 30's Acceptance 6 ("deterministic reader fixes first") on
2026-10-13 by the agent (Đạt away). Two of its four fixes shipped with
ticket 30 (an optional revision, a currency alias); these two did not,
because each changes the findings table or the message model rather than the
reader.

## What

**A blank requested date.** A PO line whose requested-date cell is empty
refuses the whole PO today (`excel._day` raises "is not a date"), so the
message is routed `attachment_unreadable` and Sales types it. A line with no
date is a legitimate PO the customer means to complete later ("date to
follow"), and Sales asks for it. It should read, and carry a finding that
says so.

**An .xlsx and its PDF print.** Some customers attach the workbook and a PDF
print of the same PO to one mail. Today each attachment is read on its own,
and the second is a `duplicate_po` (or two cases, if the totals differ by
rounding). They are one PO, the workbook the source of record.

## Acceptance

1. **Blank date.** A new finding code (for example `requested_date_missing`)
   in the spec's findings table, its severity in `sales_order_rules` (a new
   platform version and the demo tenant's), its label in the web, and a CHECK
   update wherever finding codes are constrained. The line reads with
   `requested_date: null`; confirmation is refused while the finding is open
   unless Sales disposes it, as for any blocking finding. Unit tests in the
   Excel and PDF readers; a mock PO with a blank date.
2. **Print pair.** Two attachments of one message that read to the same PO
   number, customer and revision are one PO: the `.xlsx` is read, the PDF is
   kept as a source anchor, and a disagreement between the two on any value
   is a `value_uncertain` on that value rather than a second case. A unit test
   with a fictional pair, and the mutation check (read both as two POs and
   watch it go red).
3. Both work for a form read through an approved layout (ticket 30) as for a
   built-in one.

## Sources (as of 2026-10-13)

- `dw_sales/adapters/readers/excel.py`, `pdf.py`, `stored.py` (layouts);
  `domain/orders.py` (`FindingCode`); `application/order_intake.py`
  (attachments of one message).
- Ticket 30 (its "As built").

## Comments

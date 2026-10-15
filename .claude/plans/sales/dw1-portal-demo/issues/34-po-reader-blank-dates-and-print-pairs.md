# 34 — The PO reader reports a blank requested date as a finding, and reads an .xlsx and its PDF print as one PO

Status: done (2026-10-13, agent, Đạt away)
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

## As built

1. **Blank date.** `PoLine.requested_date` is `date | None`; a line printed
   with none has no schedule. The Excel reader reads a blank cell, or one
   holding only a dash, as no date, anchored at the cell. The PDF reader
   reads a dash in the date column as no date at the dash, and a row one cell
   short with the gap at the date's column, but only when every number in it
   then reads as one and the cell after the gap is no date (or `date:
quantity` list), so a short row is never read shifted and a printed date is
   never taken for a blank one; other short rows stay what they were. One rule
   for both readers (`readers/schedules.no_date`). Readers
   `excel_po_reader@1.5.0`, `pdf_po_reader@1.5.0`.
   `check_line` raises `requested_date_missing` (line level, before the
   mapping, so an unmapped line raises it too) and suggests the first day the
   lead time allows. Dispositions `ask_customer` or `accepted` (with a
   reason: the order goes ahead with the date to follow); never a typed value.
   Severity `error` in `sales_order_rules@1.5.0` and the demo tenant's
   `1.5.1` (which replaces `1.4.1`); `ck_order_findings_code` takes the code
   (migration `a459e2244a9c`). The spec's findings table, the glossary and
   the web label have it; the lines table shows "Báo sau", never "Không rõ"
   (ui-quality §8). Mock `M44` (`VLX-PO-2610-0011.xlsx`, line 2 blank).
2. **Print pair.** `domain/print_pairs.one_po`: an `.xlsx` and a PDF of one
   message that read to the same PO number and revision and print the same
   line numbers are one PO, read from the workbook. The PDF is kept as
   `PoDocument.print_copy` (attachment, sha256, parser version) with each
   value it shows differently and where (`PrintDifference`), and that value is
   flagged `print_differs` on the workbook, so the case raises
   `value_uncertain` on exactly it. Text is compared in one Unicode form,
   single-spaced and casefolded. Anything else is two documents, routed to
   Sales as before. The order source route serves the print, labelled where
   it differs; the order view carries `print_copy`; the order page says the
   print is attached and opens it at each difference. Mock `M45` (BRN's
   workbook and its PDF print, line 1's date a week later on the print; BRN
   gained the one-sheet Excel layout).
3. **Approved layouts.** A form read through an approved layout goes through
   the same readers and the same pairing: tested with M43's form (which
   prints a dash for an empty cell and a "Buyer Note" column after the date)
   read through its mapping, as a PDF and as a workbook.

## Comments

- 2026-10-13, decided by the agent (Đạt away): `requested_date_missing` is
  `ask_customer` or `accepted`, not a typed correction: a date nobody printed
  has no source to type it from, and the customer's answer arrives as a
  revision or a reply. An accepted one goes to Bravo with no requested date
  and DW1's suggestion; PC confirms a date at confirmation as for any line.
- Decided by the agent: a dash (hyphen, en or em dash) in a date cell is no
  date. M43's form prints one for every empty cell, and no date reads as one.
  Other placeholders ("TBA", "sẽ báo sau") are still "not a date" and refuse
  the PO, as before: which words a customer uses is a fact to collect, not to
  guess.
- Decided by the agent: a workbook and a print whose line numbers differ are
  not paired (two documents for Sales), rather than flagging a whole line: a
  line one file lacks is no value of the other's to disagree with.
- Found and fixed on the way (pre-existing, ticket 22's ground):
  `order_line` returned every anchor to every viewer, and a PDF anchor's
  `quote` is the printed text, so a viewer without amounts (support, the
  leadership `READER`) read `1.150` and `7.015.000` from M03's anchors. The
  leak searches matched `1150`, never `1.150` (failure-modes #0). The order
  view now leaves out a price's anchor and the total's for such a viewer, and
  any print difference on a price;
  `test_no_price_reaches_a_viewer_without_amounts_through_a_pdf_anchor`.
  The integration leak search (`known_price_strings`) still cannot see a
  grouped price: owed to whoever owns ticket 22's tests.
- Review (`reviewing-feature-security`): tenant isolation, no new table or
  query (the print rides in the case's `document` jsonb under RLS; a case
  serves only its own print, tested); authorization, the source route keeps
  `sales.case.read` and `sales.price.read`; autonomy, none; untrusted
  content, a print only adds flags, never replaces a workbook value, and a
  print naming another PO is not paired; provenance, the print keeps its
  sha256 and parser version and its anchors are held to it; lifecycle,
  nothing created. Mutation-checked against a green baseline, 18 guards, each
  killed: the finding not raised; the disposition widened to a typed value;
  an Excel blank refused; the PDF number check and the after-gap date check
  removed; the pairing removed from intake; the flags not added; line numbers
  compared by count; po_no only (revision ignored); text compared raw; the
  view's price anchors, total anchor and print price difference unmasked;
  the print not served; the schedule sum check run on a dateless line; a
  dateless line dropped from the Bravo comparison; the migration's code
  dropped (schema test red). One survived first (line numbers compared by
  count) and has its test now.
- The migration `a459e2244a9c` is parented on `6d0252a87a6c`, the other
  agent's uncommitted ticket 24 migration: commit them in that order, or
  re-parent this one. Moot: both were committed together in 399920d, and
  alembic has one head.
- 2026-10-15: `known_price_strings` (the API integration price scan) kept
  only strings with a decimal point, so VND prices and every grouped form a
  PDF prints were never looked for. It now covers unit prices, line amounts
  and totals in each grouping a mock form uses, less printed quantities
  (`953086f`); on M03's text layer the old set found nothing, the new one
  1.150, 21.800, 7.015.000.

# 20 — Legacy Vietnamese encodings are detected, never read as text (G37)

Status: done (2026-10-12; committed in dd5ef1d; built and reviewed by the agent while Đạt was away)
Blocked by: —
Category: enhancement

Split from ticket 12 on 2026-10-12.

## What

Vietnamese documents typed in TCVN3 (ABC) or VNI fonts store bytes that read
as garbage in Unicode ("Cña hµng" for "Cửa hàng"). DW1 today would read such
a PO as text and match attributes against garbage. Nothing detects it
(verified 2026-10-12: no `legacy_encoding` anywhere in `dw_sales`).

## Acceptance

1. The Excel reader detects TCVN3/VNI font names in the cell styles of the
   cells it reads (`.VnTime`, `.VnArial`, `VNI-Times`, … — one list, in one
   place); the PDF reader detects them in the fonts of the pages it reads.
2. A detected document raises a blocking `legacy_encoding` finding (PO
   level), with the anchor of the first affected cell or page. No attribute
   matching runs on text from affected cells.
3. The finding's only dispositions are `ask_customer` or re-upload; there is
   no free-text override. Conversion to Unicode is ADR 0010 decision 3 and
   lands later.
4. One fictional fixture (an xlsx with a `.VnTime` cell) and its eval case;
   the existing fixtures raise no `legacy_encoding`.
5. Removing the detection turns the fixture's test red.

## Out of scope

- Converting the text (ADR 0010 decision 3; a later ticket).
- `.doc`/`.xls` binary formats (ticket 27).

## Sources (as of 2026-10-12)

- `dw_sales/adapters/readers/` (`excel.py`, the PDF reader),
  `domain/order_checks.py`, `domain/orders.py` (finding kinds).
- `docs/adr/0010-document-intake-at-real-size-and-format.md` decision 3
  (Proposed).

## Comments

- Decided by the agent (Đạt away), 2026-10-12: "re-upload" is the customer
  sending the PO again, in Unicode. DW1 has no upload route (files arrive by
  mail), so the new file arrives as a revision of the same case (`revise`),
  and every check runs on it again. The finding's only disposition is
  therefore `ask_customer`. There is no `accepted`, no typed value and no
  free-text note.
- Decided by the agent (Đạt away), 2026-10-12: the one list is
  `dw_sales/domain/legacy_fonts.py`, written as name prefixes: `.Vn…` is TCVN3
  and `VNI-…` is VNI, compared casefolded. A prefix covers every face and
  cut (`.VnTimeH`, `VNI-Helve-Condense`) that a list of names would have to
  enumerate.
- Decided by the agent (Đạt away), 2026-10-12: detection is per value read.
  It covers the header values, every line value and the total; the buyer cell
  is not covered because it is compared by exact name only, so garbled text
  matches nobody. Excel uses the cell's font. PDF uses the font pypdf reports
  for the run that drew the value, or any such font on the page when no run
  matched (fail closed). The finding's anchor is the first marked value in
  reading order (header, lines, total).
- Decided by the agent (Đạt away), 2026-10-12: "no attribute matching" means
  `map_line` does not read a description typed in a legacy font. The exact
  convert-list lookup by customer code still runs, because it compares codes,
  not attributes. A garbled code matches no entry, and the PO is blocked
  anyway.
- Decided by the agent (Đạt away), 2026-10-12: new versions, not edits in
  place. `sales_order_rules@1.1.0` replaces 1.0.0; the 1.0.0 file was deleted
  because it can no longer load (every code needs a severity). Also new:
  `sales_emails@1.1.0` (1.0.0 kept, as copies are), `excel_po_reader@1.2.0`,
  `pdf_po_reader@1.2.0`, and eval `sales@1.1.0`. A dev database holding cases
  stamped `sales_order_rules@1.0.0` refuses `confirm_mapping` and
  `correct_value` on them ("rules no longer apply") until `make demo-reset`.
- Reviewed by the agent (Đạt away), 2026-10-12, adversarially against the
  acceptance, `CLAUDE.md` and `failure-modes.md`. No defect in the built
  behaviour. Two guards had no test that could fail, and each now has one:
    - The PDF fallback (no run matched, so any legacy font on the page marks
      the value) was untested: removing it left every test green. Added
      `test_a_pdf_value_drawn_apart_from_its_label_falls_back_to_its_page`,
      where the PO number is in VNI and its label is not, so two runs draw
      one line.
    - Typing a flagged value over legacy text. A cell that is both hidden and
      in `.VnTime` raises `value_uncertain` too, and Sales may type its value.
      The recheck must raise `legacy_encoding` again: the typed value answers
      that finding, not this one, and acceptance 3 allows no typed value here.
      It does, because `_with_values` keeps `legacy`. No test held this until
      `test_typing_a_flagged_value_over_legacy_text_does_not_clear_the_finding`.
    - Measured, not assumed: pypdf 6.19 reports each run's font across a
      `Tf` switch inside one text object (label, legacy value, tail).
    - Out of this ticket and already true before it: `OrderLineView.anchors`,
      `total_anchor` and now `legacy_text_anchor` carry a PDF anchor's
      `quote`, which is the printed text. For a price field that text is the
      price, and it reaches a viewer whose `PriceView.amounts` is False.
      Measured on M03: `total` is hidden, yet `total_anchor.quote` is
      "94.115.000 VND" and `anchors.unit_price.quote` is "1.150". That
      contradicts ticket 22 ("every amount hidden"), so it belongs there:
      one function should redact the quote of an amount field's anchor for
      every view.

## As built (2026-10-12)

- Domain: `LegacyEncoding` and `legacy_encoding()` in `domain/legacy_fonts.py`.
  `LegacyText(field, encoding)` is carried in `legacy` on `PoHeader`, `PoLine`
  and `PrintedTotal`. `PoDocument.first_legacy_text()` gives the anchor and
  the encoding. `FindingCode.LEGACY_ENCODING` is PO level, its only
  disposition is `ask_customer`, and the policy makes it `error`.
- Checks: `check_document` raises `legacy_encoding` (expected `Unicode`,
  actual `TCVN3`/`VNI`). It is in `DOCUMENT_CHECK_CODES`, so a recheck
  replaces it. `map_line` skips attribute matching on a description in
  `legacy_fields`.
- Readers mark values as above. The text is kept exactly as the cell holds it,
  with no conversion (ADR 0010 decision 3).
- API: `OrderCaseView.legacy_text_anchor`. The correction-request draft names
  the first affected cell (`_finding_anchor`), using the words of
  `sales_emails@1.1.0`. OpenAPI and TS types were regenerated.
- Web: the finding card says why only "Yêu cầu khách sửa" is offered, and its
  "Xem nguồn" opens the region of `legacy_text_anchor`. The label is in
  `labels.ts` and in the `CONTEXT.md` glossary.
- DB: migration `0d7fd21052a4` (after `7c8ba908575f`) re-adds
  `ck_order_findings_code` with `legacy_encoding`. Its downgrade fails while
  such a finding is stored.
- Fixture `M33` (VLX, `VLX-PO-2610-0004.xlsx`): both description cells are in
  `.VnTime`. Line 1 reads `D©y ®iÖn 24AWG mµu ®en`. Line 2 has English
  attribute words that fit only `CB-2005`, and no convert entry. Findings:
  `legacy_encoding`, `code_unmapped` (line 2). Eval case
  `sales-sec-legacy-encoding` (grader `sales.legacy_encoding_held`).
  `test_no_mock_po_but_m33_holds_text_typed_in_a_legacy_font` reads every
  other fixture and finds no legacy text.
- Mutation checks, each red, then restored green: font list answers None,
  Excel stops marking line cells, PDF ignores the run's font, document check
  raises nothing, attribute matching runs on legacy text, `accepted` allowed,
  code made line-level, view names no anchor, draft points at the total
  (pytest). Detection removed made eval `sales@1.1.0` 9/11. The migration
  without the code turned `test_sales_schema[ck_order_findings_code]` red.
  The web card without its source entry turned vitest red.
- Checks run 2026-10-12: unit 2443 passed. The only 2 failures were in
  `test_public_repo_guard.py`, another ticket's work in progress in the same
  tree. Integration: dw_sales 101 passed; the API sales suites 104 passed
  plus 1 failure, a pinned `sales_emails…@1.0.0` ref, fixed and its file
  re-run (26 passed). Evals: `sales@1.1.0` 11/11. Vitest 309 passed.
  Typecheck, lint and format were clean. The Playwright walk (now 33
  messages) was not run. It has since passed on CI's Web E2E workflow, first
  on `e97042b` (2026-10-13).
- Review (same day): two tests added to `test_legacy_encoding.py`, the PDF
  page fallback and a typed value over legacy text (see Comments). Each
  turned red when its guard was removed. The other guards were broken again
  one at a time and each turned red: the Excel header and total marks,
  `map_line`, `DOCUMENT_CHECK_CODES`, the one allowed disposition, the VNI
  prefix, the subset tag, and the web source entry. The eval went 9/11 with
  Excel detection removed. Everything was green again after restoring.
- Open: a legacy encoding outside the list (VPS, VietWare, BK HCM) is still
  read as text. The PostScript name a real TCVN3 PDF gives `.VnTime` was not
  measured (only generated fixtures were); a real file should be checked when
  one arrives. The line grid does not draw a legacy-font value as its own
  value state; the PO-level finding blocks instead.
- 2026-10-15 (`bda82a6`): the Excel PO reader reads each rich-text run's
  font from the "as written" workbook (`rich_text=True`), measured on
  openpyxl 3.1.5 for inline and shared strings; `excel_po_reader@1.6.0`,
  mutation-checked. Only generated fixtures were measured; a real customer
  file with rich-text TCVN3 runs has not been checked.
- 2026-10-15 (`c6f0d95`, `71b724f`), decided by the agent (Đạt: làm luôn):
  an RFQ value in a TCVN3/VNI font makes the file unreadable
  (`QuoteFileUnreadableError` naming the encoding and the cell), routed to a
  person as `attachment_unreadable`; no case, no model, no migration
  (`excel_rfq_reader@1.1.0`). Not `value_uncertain`: on a quote that would
  let Sales type over legacy text. The Design reply reader refuses the same
  way. The buyer cell is read as it stands on both the PO and the RFQ side:
  it is only compared with master data by exact name, so garbled text
  matches no customer. Đạt may revisit refusal versus a quote-side finding.
  Still open: in read-only mode a run's font is seen only for shared strings
  (as Excel writes them), so a legacy-font run in an inline string (what
  openpyxl and other non-Excel generators write) is read as garbled text
  into a case (`test_a_run_kept_inline_is_read_as_text_the_measured_limit`
  pins it); legacy-font text in a non-form `.xlsx` RFQ reaches the model
  through `text_parts`, flagged `model_read` but not detected. Owed on
  Docker: the API integration suite (`test_sales_api_quotes.py` pins
  `excel_rfq_reader@1.1.0`).
- 2026-10-15: `legacy_text_anchor` was the first legacy value whatever its
  field, so a PO whose first legacy text was a price handed that price's
  anchor (a PDF anchor quotes the printed words) to a viewer without
  `sales.price.read`. It is now the first legacy text the viewer may see
  (`PoDocument.legacy_texts`; `953086f`, with a test that was red before).

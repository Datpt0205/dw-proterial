# 15 — A `value_uncertain` correction is per field and reaches the upload file

Status: done (2026-10-12; not committed; adversarial review 2026-10-12, two defects fixed)
Blocked by: —
Category: bug

## What

When Sales corrects a value DW1 was not sure of (a hidden row or sheet,
font matching the fill, a formula with no cached value), the correction is
one free-text string for the whole finding, and the Bravo upload file and the
cross-check sheet still print the value as read. The correction only appears
as text in the cross-check "disposition" column.

Verified 2026-10-12:

- `value_uncertain` is raised once per line (key `value_uncertain:N`) and
  once for the PO header/total (`value_uncertain:-`). A hidden row flags
  every field of the line, so one finding can cover several fields.
- The disposition is `CorrectedBySales{value: str}`: one string, no field
  name. `dispose` swaps the disposition and leaves `po_line` unchanged.
- `upload_values` (used by `bravo_upload` and `cross_check_sheet`) reads
  every printed field from `line.po_line`; only `prv_code` comes from the
  structured `LineMapping`. Tests assert today's behaviour: after M27's lines
  are corrected, the upload's `unit_price` still equals `po_line.unit_price`.

The pattern to follow already exists for the PRV code: a free-text correction
of a mapping finding is refused, Sales uses `confirm_mapping`, and the typed
`LineMapping.prv_code` is what the upload reads.

## Acceptance

1. A correction names the field it corrects and carries a typed value
   (Decimal, date, uom, text as the field is), validated against the fields
   that finding actually flagged. A field the finding did not flag is
   refused (422).
2. Corrected values are stored on the line/header as structured data, beside
   the value as read (both kept: the evidence is what was read).
3. `upload_values` overlays corrected values; the cross-check sheet shows,
   per field, the value as read, the corrected value, and who typed it.
4. A free-text `corrected_by_sales` on `value_uncertain` is refused, as it
   is for mapping findings. `ask_customer` is unchanged.
5. Price fields stay behind `sales.price.read` on read and write, as today.
6. The finding is resolved only when every flagged field has a correction.
7. The tests asserting the as-read value in the upload flip, and a test shows
   that removing the overlay turns them red.
8. Audit: one row per correction, ids and field names only, no amounts.

## Question for Đạt (why needs-info)

- **Are the line's checks run again on the corrected values?** The price,
  MOQ, lead-time and total checks ran on the values as read. Re-running
  them is the honest answer (a corrected price can raise `price_mismatch`),
  but it bumps the case version and can reopen findings Sales already
  decided. Proposed default: re-run the checks of the corrected line only,
  and keep dispositions on findings whose key and inputs did not change.

## Out of scope

- Re-reading the file (the parser is unchanged).
- The PO-level `unchecked_region` flag that names no field: it stays
  `ask_customer` or a free-text note.

## Sources (as of 2026-10-12)

- `dw_sales/domain/orders.py` (`RegionFlag`, `FlaggedValue`,
  `CorrectedBySales`, `dispose`, `confirm_mapping`),
  `domain/order_checks.py`, `application/order_artifacts.py`
  (`upload_values`, `_disposition_text`), `application/views.py`,
  `presentation/routes.py` (`DispositionBody`, `MappingBody`).
- `dw_sales/tests/…/test_artifacts.py` (M27 assertions).
- `sales.md` Open, "From ticket 06".

## Comments

- 2026-10-12, Đạt ("làm theo bạn tự recommend"): the proposed default holds.
  After a correction, re-run the checks of the corrected line only (header
  corrections re-run the PO-level checks); a finding whose key and inputs
  did not change keeps its disposition, and one that changed reopens. The
  case version bumps as for any edit.

## As built (2026-10-12)

1. **Per field, typed, validated against the flags.** `POST
/orders/{id}/findings/{key}/corrections` takes `{case_version, field,
value}` (`CorrectionBody`), on `sales.order.prepare`. The case validates the
   value as the field's own type by building the line (or header) with it, so
   `PoLine`/`PoHeader`/`PrintedTotal` stay the one owner of each field's type
   (422 naming fields, the input never echoed). A field the finding did not
   flag is 422; any other code than `value_uncertain` is 409. The header's
   total is named `total` (`TOTAL_FIELD`). A line's number and the PO's
   number and revision are confirmed as read only (409 for another value:
   they key findings, revisions and the PO's history, so another number is
   asked of the customer); the web offers "Xác nhận đúng như đọc" for them.
2. **Stored beside the value as read.** `ValueCorrection {field, value, by,
at}` on `OrderLine.corrections` (`sales.order_lines.corrections`) and
   `OrderCase.header_corrections` (`sales.order_revisions.header_corrections`,
   on the revision, so a later revision starts with none), migration
   `33f444c15062` (upgrade, downgrade -1, upgrade checked; one head). The
   CHECK holds each element to exactly those four keys
   (`test_sales_schema.py` compares them with the model). `po_line` and the
   document are never rewritten; `OrderLine.effective` /
   `OrderCase.effective_header` / `effective_document` are the order as it is
   entered.
3. **The upload file and the cross-check sheet.** `upload_values` reads the
   entered line and header. The cross-check sheet (copy
   `sales_documents@1.1.0`, pinned in the manifest; `1.0.0` kept for
   artifacts already stamped with it; every document kind is now
   stamped `@1.1.0`, and the two API tests pinning `@1.0.0` moved) has a "Sales sửa thành" column beside
   "Trên PO", per field; "Sales nhập tay" names who typed that field (the
   field's own correction, not whoever resolved the finding); the PO's own
   flagged values get rows of their own before the lines. The confirmation
   draft, the portal checklist, the Design request, the cannot-supply draft
   and the convert-list proposal also print the entered values, and a
   revision's change list is diffed from the order as entered.
4. **Free text refused.** `dispose(corrected_by_sales)` on `value_uncertain`
   is 409 "corrected field by field". The one exception is the out-of-scope
   PO-level `unchecked_region`: a note is accepted there only once every
   flagged header value is typed (a field correction never resolves a sheet
   nobody read). `ask_customer` is unchanged.
5. **Prices.** Typing `unit_price`, `amount` or `total` needs
   `sales.price.read` in the service (403 before anything is read); a typed
   amount is `{"hidden": true}` in the view without it (`AMOUNT_FIELDS`, one
   set in the domain, which the view's change list now reads too).
6. **Resolved when complete.** The finding becomes `corrected_by_sales` (by
   whoever typed the last value; `value` = the field names, never a value)
   once every flagged field has a correction. Every typist is a maker
   (`OrderCase.makers`), so none of them cross-checks.
7. **Tests flip.** `test_artifacts.py`: M27's values are typed per field
   (line 2's price typed as 0.0475, the rest as read); the upload's line 2
   price is the typed one, the cross-check sheet shows read 0.0465 / typed
   0.0475 / in the upload 0.0475.
8. **Audit.** One `sales.order.value_corrected` event and audit row per
   correction, in the save's transaction, with `finding_key` and `field` only
   (the API suite asserts no amount in the row).

**Rechecks (Đạt's decision).** `OrderIntake.correct_value`: a line
correction runs that line's checks again on its entered values, and the
document check (the amounts add up to the total); a header correction runs
the document and customer checks again, and every line's when the PO date or
the currency changed. A corrected customer code or description maps the line
again (its mapping findings come back open; a confirmed mapping on another
code is not kept); otherwise the line keeps its mapping. Lines are checked
against today's master data under the case's stamped rules (refused once the
tenant's rules moved on), as `confirm_mapping` does; `confirm_mapping` now
also checks the entered values and keeps the corrections. A finding whose
key and compared values (severity, expected, actual) are unchanged keeps its
decision; a changed or new one is open; PC's agreement on a short lead time
stays while that finding is unchanged. The case version bumps once.

**Web.** The finding card of a `value_uncertain` lists every flagged value:
as read, what Sales typed (who, when), and a typed antd input per field
(`AmountInput` for numbers, `DatePicker` for dates, `Select` for the
currency, `Input` for text), with "Còn N/M giá trị chưa nhập lại". Without
`sales.price.read` a price shows locked and has no input. The free-text
"Sửa giá trị" is no longer offered there. The lines table shows the entered
quantity, price, amount and requested date, with "Đọc được: …" under a typed
one. `apps/web/app/sales/_lib/__tests__/value-corrections.test.tsx`.

**Mutation checks** (each guard removed, its test red; baseline green
first): upload overlay; free-text refusal; price scope on write; unflagged
field; resolve only when complete; carry a decision; reopen a changed one;
identity fields; hiding a typed price; typist is a maker; line recheck;
document recheck; remap; store of corrections; audit field; the CHECK's
"no other key"; the web price-input guard.

**Not done / owed.** The PO history check (duplicate, revision) is not run
again on a header correction: its keys (PO number, revision) cannot change,
but the Bravo comparison also reads the currency, so a currency correction
that would make the PO a duplicate of a Bravo entry is not detected (edge,
not in the mock set). No mock PO flags a header value, so the header path is
covered by hand-built cases only. Re-checking reads today's master data, as
`confirm_mapping` already did, and does not move `catalog_as_of`.

## Review (2026-10-12, adversarial reviewer)

Fixed:

- **A revised order's change list printed the revision as read.** A case
  revised before or after Bravo lists `changes`, and in `change_review` they
  are what the PIC applies in Bravo (`change_summary`): no upload file is made.
  `correct_value` left them as `revise` computed them, so a value of the
  revision typed by Sales never reached that sheet, the same bug as the
  ticket's on the other path. `rebase_changes` (beside `diff_lines`) now gives
  each change its value as entered as its after, keeps the before the order
  held, drops a change the correction undid (compared as values: `0.0420` is
  `0.042`), and adds one the correction made.
  `test_a_revision_s_change_list_carries_the_value_as_entered`.
- **The screen offered a note the case refused.** The findings card worked out
  for itself when to offer the free-text "sheet not checked" note (PO-level,
  a sheet nothing reads) but not that every flagged header value must be typed
  first, so it offered a choice that answered 409. The rule is now one method,
  `OrderCase.takes_value_note`, which `dispose` enforces and the view reads to
  filter `allowed`. The web offers what `allowed` says.
  `test_the_screen_offers_a_note_only_where_the_case_takes_one`, and the web's
  "offers a free-text value on a value_uncertain only as the server allows it".
- `order_artifacts._flagged` restated `PoLine.flagged`; it reads the property.

Mutation checks re-run by the reviewer (`review_mutate.py`, scratchpad): each
had a passing baseline and was counted only when pytest reported a FAILED test,
and the file was restored byte for byte: upload overlay, free-text refusal,
note waits for every value, view offers what dispose takes, price scope on
write, unflagged field, resolve when complete, hide a typed price, typist is a
maker, rebase a revision's changes, carry decisions. Through the API: the audit
row's `field` (KeyError without it). Web: offering the note whatever `allowed`
says turns the new vitest red.

Still open (not fixed here):

- The web keeps its own list of amount fields (`AMOUNTS` in
  `value-corrections.tsx`) to lock a price input. The server enforces it
  (403), so a drift costs an error after an offered input, not a leak. Reading
  `isHidden(row.read)` instead would remove the copy.
- Someone with `sales.order.prepare` but without `sales.price.read` could type
  quantities and watch `line_total_mismatch` appear and go (its values stay
  hidden) to narrow down an amount. No such persona exists (ADR 0003).
- The lines table shows the entered quantity, price, amount and requested
  date; a corrected item code, description or unit still shows as read there
  (the finding card and every file show the entered one).
- `line_total_mismatch` still takes a free-text `corrected_by_sales` that no
  file reads, the same shape as this ticket's bug; out of this ticket's scope.
- The tenant isolation test (Beta's PIC gets 404) rests on the workspace-scoped
  store and RLS that other suites mutation-check; it was not mutated here.

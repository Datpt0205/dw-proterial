# 15 — A `value_uncertain` correction is per field and reaches the upload file

Status: needs-info
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

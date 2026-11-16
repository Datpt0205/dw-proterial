# 16 — The YCBG in Bravo's real shape: RFQ number, Design Check, status

Status: done (2026-11-16); a QUOTE moving the case waits on ticket 11, the read-back on R13
Blocked by: the Bravo API's R13 for the read-back (until then, Bravo's YCBG export as a file)
Category: enhancement

## Why

Bravo's "Phiếu yêu cầu báo giá" (11-10) numbers each request
`RFQ<yymmdd>-<nnn>`, takes the customer's mail subject as its description,
and carries per line the direct and indirect customer, the customer's item
description, a Design Check and a status (PENDING). DW1 records
`ycbg_recorded` with a number typed by Sales and reads Design's reply from
mail only.

## Shape

- DW1's YCBG draft carries Bravo's fields: description from the mail
  subject, the lines with direct and indirect customer and the customer
  item description.
- The number Sales records must be `RFQ` + 6 digits + `-` + 3 digits; any
  other shape is refused (CHECK on the column, mutation-checked).
- Once R13 exists, DW1 reads the request back by number. If Design writes
  its result in Design Check (Q-B11), DW1 takes it from there and stops
  waiting for a mail. The status is read, never written.

## Acceptance

1. A YCBG number `RFQ261110-002` is accepted; `RFQ2611-2` is refused.
2. A Design reply naming a number no open request holds goes to Sales,
   never onto a guessed case.

## Comments

## Done

Built 2026-11-16 (migration `10d5dfc1a3f1`, after `3d139b41fec1`).

- **The number.** `YcbgNo` (`^RFQ[0-9]{6}-[0-9]{3}$`, `domain/quotes.py`):
  the route body (`YcbgBody`, 422), `QuoteCase.record_ycbg` (`DomainError`
  naming `ycbg_no`, never the value) and `ck_quote_cases_ycbg_no` all refuse
  `RFQ2611-2`; `RFQ261110-002` passes. The database's verdict on every sample
  equals Python's (`test_ycbg_exports_db.py`). **Existing rows**: the
  migration rewrites none; the CHECK is added `NOT VALID` and validated only
  when every row fits, so a case recorded before (the demo's `YCBG-2609-030`)
  still reads and refuses every write (`test_ycbg_number_migration.py`); the
  count is printed in the deployment log. A reply naming such a number still
  reads, and goes to Sales: no case can hold it.
- **The draft in Bravo's shape.** `DesignRequestDraft.description` is the
  customer's mail subject; each line names the direct and the indirect
  customer (the case's customer, on the side its Bravo group says) beside the
  customer's own item description. The sheet's words are
  `sales_documents@1.3.0`.
- **Design's result read from Bravo** (`application/ycbg_exports.py`).
  `BravoYcbgPort` is the read (R13 later; `ExportedYcbg` over an uploaded
  export now). "Kết quả Design từ Bravo" on Báo giá uploads the YCBG export
  (`POST /api/v1/sales/ycbg-exports`, 202, `sales.quote.prepare`, refused
  while DW1 is paused); the worker (`sales.ycbg_export.uploaded`) scans it,
  reads it in the reader sandbox (`table.rows`), and `DesignChecks.take`
  records a closed YCBG's result (`DesignCheck`: QUOTE + BP code or DECLINE +
  reason per line) on the one case waiting on Design under that number, as
  the uploader re-resolved now. Status is never moved and Bravo never
  written. A number no case waits on, lines other than the request's, a
  result different from the one recorded, or a result that is not one go to
  Sales in the upload's outcome list; a line still PENDING is skipped.
  Shown on the case ("Phản hồi của Design") with a warning on a DECLINE.
- **Assumed** until one real export is seen (spec Q-B13): the column titles
  `Số chứng từ`, `STT`, `Trạng thái`, `Design Check`, `Lý do`, `Mã BP`; the
  values PENDING/CLOSE and QUOTE/DECLINE; that STT is the request's line.

Left: a QUOTE moves nothing yet (the spec number and copper weight come from
the BP code's base price, ticket 11); R13's adapter; follow-ups still remind
on a case whose result was read (they read the status only).

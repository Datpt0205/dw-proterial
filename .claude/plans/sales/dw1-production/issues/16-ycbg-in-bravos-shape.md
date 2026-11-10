# 16 — The YCBG in Bravo's real shape: RFQ number, Design Check, status

Status: needs-info (Q-B11: who writes Design Check and the status)
Blocked by: Q-B11; the Bravo API's R13 for the read-back
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

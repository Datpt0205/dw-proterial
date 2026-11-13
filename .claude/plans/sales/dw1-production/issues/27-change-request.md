# 27 — A change request on an order, confirmed line by line

Status: ready-for-agent
Blocked by: 26
Category: enhancement

## Why

dw_sales ADR 0010 decision 2, BA step 6.1A/6-DW1; Box B03 asks for a
pull-in as a table in the mail's HTML body.

## Shape

- `ChangeRequest` on the order case: lines of (line no, field, held value,
  asked value, anchor into the mail), each open / confirmed / rejected; one
  open per case, a later one queued.
- A table in the HTML body is split by code into rows; free text is read
  by the model as spans that code locates and parses (dates, quantities
  with units).
- Confirming a line applies it and bumps the case version (ADR 0005's body
  rule as amended).

## Acceptance

1. A B03-shaped fixture (no customer data) yields one change line per row,
   none applied until confirmed.
2. A second change request while one is open is queued, not merged.
3. A quantity whose unit differs from the line's (km vs m) is flagged, not
   converted silently.

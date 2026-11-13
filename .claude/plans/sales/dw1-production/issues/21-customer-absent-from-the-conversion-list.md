# 21 — A customer absent from the conversion list

Status: ready-for-agent
Blocked by: none (customer 4's codes: owed by Proterial)
Category: enhancement

## Why

The list is already keyed by (customer, customer code) (`convert_entry`).
Customer 4 has no rows at all; one description maps to different PRV codes
at different customers, so another customer's row is never a match.

## Shape

- A customer with no rows: every line is "chưa có mã" with the nearest PRV
  candidates by description, never another customer's mapping as a match.
- The PIC's confirmed code is remembered for that customer only (as today).

## Acceptance

1. A line of customer 4 never takes customer 1's mapping for the same
   description.
2. The PIC confirms a code once; the next PO of customer 4 maps it.

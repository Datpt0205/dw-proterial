# 38 — A customer's SalesOrder rules learned from a worked example, proven by replay

Status: ready-for-agent (the mechanism on synthetic pairs); the real proof waits on B41 and one real pair per customer
Blocked by: 02 (the SalesOrder layout), 36 (master lists as exported); B41 from Proterial for the real columns
Category: enhancement

## Why

Đạt, 11-13, and dw_sales ADR 0013. DW replaces the PIC's step "adjust the
SalesOrder file for each customer": learned from one pair (original PO, the
PIC's processed file), proposed by the model as a tenant rule version, proven
by replaying it on that PO cell by cell, approved by the head, then applied
by code to every PO of that customer.

## Shape

- **Rule version per customer** (`sales_salesorder_rules`, tenant data):
  per SalesOrder column a source and an ordered list of steps from a closed
  set: `copy`, `constant`, `lookup(table, key)`, `unit_factor(from, to)`,
  `shift_days(n)` (calendar days), `round(places, mode)`, `cut(start, end)`.
  A step outside the set is refused at validation. Few settings, each one
  sentence (Đạt: config simple).
- **Learning:** the person uploads the pair on the customer's screen; the
  model reads both (headers in any language, sample rows) and proposes the
  version; code validates it; nothing of a PO's values is kept in it.
- **Replay:** code applies the proposal to the original PO and compares
  every cell with the PIC's file (numbers by value, dates by day, text
  after NFC and trim). The diff lists cell, expected, got and the rule; a
  non-empty diff refuses "Gửi duyệt". The approval shows the replay.
- **Lookup tables** the workbook hides (colour letters; PRL → PRV → spec →
  standard length; price tables) are imported as master data with their
  own approval (ticket 36's import), never copied into a rule.
- **Checks from the "hk & cable" sheet**, against DW1's findings:
  - Vs price → `price_mismatch` / `lme_band_mismatch` (exist; the formula
    itself waits on ADR 0008);
  - Vs length → new finding `reel_length_mismatch`: the PO's unit length
    per reel (e.g. "610X12") against the item's standard length (305/610),
    beside `pack_multiple`, which checks the quantity only;
  - Vs SPV → new finding `spec_mismatch`: the spec number the PO prints
    against the item's spec in master data.
- **Writing Bravo:** the approved file through the write API after a person
  approves it (ADR 0026), else exported for a person to import.

## Acceptance

1. A synthetic pair (a PO with ETA dates, colour letters, km quantities)
   yields a proposal whose replay reproduces the processed file exactly.
2. One wrong step (shift −9 instead of −10) lists the cells it breaks and
   cannot be sent for approval.
3. The proposer cannot approve; the approved rules map the customer's next
   synthetic PO with no model call.
4. `reel_length_mismatch` and `spec_mismatch` raise on a line that breaks
   them and not otherwise.

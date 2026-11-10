# 04 — The conversion workbook's rules and colour codes as master data

Status: needs-info
Blocked by: B43 (the conversion workbook: sheets PRL PO, PRV vs PRL, Price; the colour-code table)
Category: enhancement

## Why

Customer codes become PRV codes through a large formula workbook, and a
colour code is part of the PRV code. DW1 converts through the convert list
and what Sales confirmed (item 3), not through these rules.

## Shape

- Read the workbook first, then decide per rule whether it is data (a
  mapping row, imported through master data) or a rule (a pattern code
  applies).
- Colour codes become a master-data table. Code composes the PRV code from
  its parts; the model never does.
- Every converted line keeps which row or rule converted it (check basis).

## Acceptance

1. Every PO line in B43's sample converts to the code the workbook gives.
2. A colour not in the table leaves the line unmapped, with a finding.

## Comments

- 2026-11-10 (Bravo screens): the convert list is Bravo's own, "Converting
  customer to PRV item", with an approval ("Duyệt Convert Master List") and
  the colour written into the converting description. So this ticket reads
  Bravo's approved rows through the Bravo port (ticket 14); it does not
  rebuild the workbook's formulas. A mapping Sales confirms in DW1 (item 3)
  stays usable until Bravo has the row. DW1 lists the confirmed mappings
  Bravo does not have yet, for Sales to enter and approve there. Bravo's row
  then answers first, so the facts do not end up kept in two places.

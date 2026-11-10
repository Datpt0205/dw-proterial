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

# 08 — On an export hold, the NOEC request drafted

Status: needs-triage
Blocked by: Đạt's call. Export control was withdrawn on 10-29 (ticket 45), yet the BA's drawio has NOEC/ESF holding a PO
Category: enhancement

## Why

The hold (`missing_noc_esf`) stays, and the export-control PIC acknowledges
it. The drawio adds a NOEC request drafted when a PO is held.

## Shape (if Đạt keeps it)

- On the hold, a NOEC request is drafted from an example (customer, items,
  PO) and the PIC sends it. No screening page and no ESF workflow.

## Comments

- 2026-11-10 (Bravo screens): Bravo keeps the ESF as the "Export control
  program". It has one ECP per direct and indirect customer for each fiscal
  year (01/04–31/03), and the customer record has an "ECP tracking" tab.
  Bravo also keeps a "Black list". The hold DW1 already has can read both
  through the Bravo port instead of master-data dates: no ECP covering the
  PO date, or a black-list keyword match, holds the order. That needs no
  new page and stays inside the 10-29 decision. The NOEC draft is still
  Đạt's call.

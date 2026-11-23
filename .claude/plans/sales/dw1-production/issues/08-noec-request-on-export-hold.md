# 08 — On an export hold, the NOEC request drafted

Status: wontfix for the NOEC draft (2026-11-23); the hold's reading from Bravo moves to ticket 50's pending checks
Blocked by: none (decided)
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

## Decided (2026-11-23, Đạt ("làm theo khuyến nghị"))

- **No NOEC draft.** Export control left DW1's scope on 10-29 (ticket 45);
  drafting its request would bring it back.
- **The hold stays and reads Bravo**: no ECP covering the PO date, or a
  black-list match, holds the order, read from ticket 50's copy of Bravo's
  `Export control program` and `Black list` instead of master-data dates.
  That is ticket 50's pending "checks that use the copy"; pending: what
  counts as a black-list match is Bravo's own routine, read on Proterial's
  host before code decides it (ticket 52).

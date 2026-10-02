# 01 — Mock data and the ports it sits behind

Status: ready-for-agent
Blocked by: —

## What

- Declare `SalesCatalogPort` and `InboxPort` in `dw_sales/application/ports.py`.
- Implement `MockSalesCatalog` and `MockInbox` in `dw_sales/adapters/mock/`
  over fixture files: 6 fictional customers (one intra-group customer that
  sends one-sheet-per-page Excel POs), ~30 cable items with attributes,
  ~40 convert-list rows, ~25 quotations (incl. expired and LME-banded),
  12 months of LME copper, NOC/ESF status per customer.
- ~10 mock emails with generated attachments (xlsx, text PDF): clean PO,
  multi-sheet PO, PDF PO, price mismatch + unmapped code, revised PO,
  duplicate PO, quote request for a new item, quote request with target
  price, a non-PO email, a PO whose body carries a prompt-injection attempt.
- A script that regenerates the attachments from the fixtures.

## Acceptance

- Unit tests read every fixture through the ports.
- No real company or person names.

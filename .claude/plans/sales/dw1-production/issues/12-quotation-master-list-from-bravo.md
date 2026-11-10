# 12 — The quotation master list read from Bravo, not kept twice

Status: needs-info
Blocked by: Bravo's read API ("Master list báo giá"); dw_sales ADR 0008
Category: enhancement

## Why

Bravo has a "Master list báo giá", and its quotation module goes live in
11/2026. DW1 records a master-list row itself after approval, and two lists
drift (failure-modes #2).

## Shape

- DW1 reads valid prices through the Bravo port. The step that records a
  master-list row becomes "Sales recorded it in Bravo", and the row is read
  back the way ticket 03 reads an SO.

## Acceptance

1. A price check reads the price Bravo holds for that day.
2. With Bravo unreachable, the check says it could not run; it never passes.

## Comments

- 2026-11-10 (Bravo screens): "Báo giá, chào hàng" and "Master list báo
  giá" are live. A quotation carries an LME band (7,500–15,000), the price
  at fixed LME, and a "Duyệt" approval. The master list joins the request,
  the base price at quotation time and the quotation. Confirms the shape:
  DW1 reads it and records nothing of its own.

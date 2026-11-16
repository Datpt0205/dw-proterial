# 12 — The quotation master list read from Bravo, not kept twice

Status: ready-for-agent for the reader (2026-11-16: B07 "Master list báo giá Bravo", key RowIdSQ, Quote No. + Stt); what a price check does with it waits on ADR 0008
Blocked by: dw_sales ADR 0008 for the price check only; which of Excel (2,521 rows) or Bravo owns quotation history (Đạt owes)
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

## Reader done (2026-11-16)

- **Bravo's "Master list báo giá" is a master list**
  (`CatalogList.BRAVO_QUOTATIONS`, `domain/catalog.BravoQuotation`), read
  through the Bravo port as exported, keyed by RowIdSQ. B07 titles "LME",
  "MOQ" and "BP date" twice, in different blocks, and titles RowIdSQ on the
  block row only: the one reader now reads a column by its block where two
  blocks title it alike (`ExportColumn.block`, the label nearest its left on
  the row above; mutation-checked), and refuses a title found twice with no
  block named. Bravo's MOQ is text with "." as its decimal mark
  (`dot_decimal`; a comma is refused, never guessed). Importing it needs both
  price scopes (every customer's centre price).
- **Measured outside git: B07, 161 of 161 rows read.**

Left: what a price check does with it waits on ADR 0008; which of Excel
(2,521 rows) or Bravo owns quotation history is Đạt's to say.

# 12 — The quotation master list read from Bravo, not kept twice

Status: reader done; the price check waits on Bravo's band table (its API or its printed quotation): ADR 0008 decided A on 2026-11-17
Blocked by: a readable band table from Bravo (B07 alone cannot answer a PO's price without DW1 computing one)
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

Left: the price check against Bravo's prices, once Bravo's band table can be
read. Decided 2026-11-17 (dw_sales ADR 0008, A, Đạt left it to the agent):
Bravo computes, DW1 reads; Bravo owns quotation history from go-live, the
Excel history stays read-only evidence. Measured on B07 why the master list
alone is not enough: no PRV item (a BP shared by up to 56 items in B06), up
to 10 rows per customer and BP, a centre price at LME 7,750 only. Until
then the check keeps its stand-in (Sales' valid-quotation list plus the
rows DW1 records after approval), replaced when Bravo's read arrives.

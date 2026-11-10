# 13 — A suggested price from the LME band, the customer's margin and the rate

Status: needs-info
Blocked by: dw_sales ADR 0008 (who computes the price); the pricing sheet
Category: enhancement

## Why

Drawio 1b: Sales prices from the LME band, the customer's margin and the
exchange rate, following a strategy. DW1 has `suggest_price` from evidence;
the real formula lives in Excel, and perhaps in Bravo's module.

## Shape (if ADR 0008 keeps it in DW)

- The formula is a tenant rule that code computes; the model only explains
  it. Sales decides and the head approves, as today.

## Comments

- 2026-11-10 (Bravo screens): Bravo's quotation already holds the price at
  a fixed LME and an LME band. Monthly LME and LME center are entered in
  Bravo. This leans ADR 0008 towards option A. The rule that moves a price
  with the LME center is asked of Sales (Q-B8).

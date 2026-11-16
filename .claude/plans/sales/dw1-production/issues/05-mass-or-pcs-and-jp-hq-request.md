# 05 — Mass or pcs, and the request to JP & HQ for a pcs price

Status: ready-for-agent (2026-11-16: B49 `xin giá pcs từ JP` gives the pcs signs, the request template and its recipient, GM/BC Manager)
Blocked by: none; open questions for Sales: are SGA/loyalty/profit rates fixed per pcs order, is "JP & HQ" the GM at PRV, the assembly-cable variant
Category: enhancement

## Why

Drawio 1a: JP & HQ price a pcs request, not Sales. Bravo's SO header
carries the type ("Mass production").

## Shape

- The quote case gets `production_type` (mass | pcs). Code proposes it from
  the customer's and the item's history where it can, otherwise the model
  reads it from the RFQ; Sales confirms.
- For pcs, a request to JP & HQ is drafted from one example mail (ADR
  0006): code writes every fact and Sales sends it. The case then waits on
  JP & HQ, with a follow-up.

## Acceptance

1. Sales cannot price a pcs case until JP & HQ's price is recorded.
2. The draft names no figure the facts do not hold.

## Comments

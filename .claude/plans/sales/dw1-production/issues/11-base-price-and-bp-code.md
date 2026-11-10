# 11 — Base price and BP code from Design's reply

Status: needs-info
Blocked by: ticket 14 (Bravo's Base price list); the BP code's format is known (`BP` + 6 digits)
Category: enhancement

## Why

Drawio 1a: Design answers a YCBG with the Base price and a BP code, which
the quotation and Bravo need later.

## Shape

- Two fields on the Design reply (form and mail readers), anchored in the
  source like every other value, and shown to price readers only.

## Acceptance

1. A reply's Base price is kept only when it is read from its source span.
2. A support viewer never sees it (ticket 22's rule).

## Comments

- 2026-11-10 (Bravo screens): "Danh mục Base price" holds every BP: the
  code (`BP` + 6 digits), date, unit, Cu weight, base price, LME of BP,
  %MR, the cost split, and the change history. DW1 reads it through the
  Bravo port, and checks a BP code named in Design's reply against it. The
  cost split is shown to price readers only. Unblocked once ticket 14 can
  read the list.

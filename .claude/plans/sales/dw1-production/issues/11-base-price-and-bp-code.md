# 11 — Base price and BP code from Design's reply

Status: ready-for-agent (2026-11-16: the Excel path; B21 "Danh mục Base price" columns known, B07's BP-latest block and B16's YCBG rows carry the BP code)
Blocked by: none to build; the full Base price list (B21 holds the latest 100) is requested from Proterial Sales
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

## Done in part (2026-11-16, the Excel path)

- **Bravo's "Danh mục Base price" is a master list** (`CatalogList.BASE_PRICES`,
  `domain/catalog.BasePrice`), read through the Bravo port (ticket 14):
  uploaded as Bravo exports it, previewed, approved by a second person, then
  in force. B21's own titles are its columns' aliases (`_x000d_` and
  `{BP Unit}` inside them read fine). Importing or previewing it needs
  `sales.price.read` (`_PRICED`), mutation-checked. Migration
  `acb2a1fbb213` admits the list. **Measured outside git: B21, 100 of 100
  rows** (it holds the latest 100 BPs only; the full list is asked of
  Proterial).
- **A QUOTE line's BP shown with Bravo's base price**, on the quote case
  (`QuoteCaseView.design_prices`): the base price per BP unit, the unit,
  copper and LME of BP and the list's `as_of`, for a price reader only
  (decided once, in `views.quote_case`; a reader of cases only gets none,
  mutation-checked); a BP the list read does not hold is said so ("Không có
  trong danh mục Base price đã đọc"), never a blank price. Web: a column in
  "Phản hồi của Design", `MaskedValue` for a caller without prices.

Left:

- The contract (`openapi.json`, `sales.d.ts`) regenerated with this, held
  while the parallel session's routes are uncommitted.
- A QUOTE moving the case to pricing (ticket 16's "Left"): the spec number
  and copper weight are now in hand from the BP's row, but a value taken
  from a master list needs an anchor kind of its own before `DesignReply`'s
  `Sourced` fields can hold it. Next slice.
- Base price and BP code read from a Design reply *mail* (the form and mail
  readers): unchanged.

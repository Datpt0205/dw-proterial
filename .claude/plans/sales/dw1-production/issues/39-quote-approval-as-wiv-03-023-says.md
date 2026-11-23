# 39 — Quote approval as WIV-03-023 §4 says: ASV checks every quote, a Manager approves one with an order

Status: ready-for-agent (2026-11-23: Đạt follows the procedure's two levels)
Blocked by: none
Category: enhancement

## Why

Box B19 (11-14 inventory): there is no approval matrix by amount. WIV-03-023
§4: every quotation is checked by ASV or above; a quotation that comes with
an order is also approved and signed by a Manager or above; a new quotation
without an order needs no Manager. Bravo's own approve button has three
outcomes, Duyệt / Trả lại / Không duyệt, each with a reason, and an internal
portal stamps the PDF electronically.

DW1 today: one checker's decision on `sales.quote` (approve or return to the
pricer), the head or a holder of `sales_quote_approver`; a decline is a
separate step before sending.

## Shape (proposed)

- The quote case records whether it comes with an order (a PO case linked,
  or Sales says so); the approval it raises is `sales.quote.check` (ASV
  level: the head or `sales_quote_approver`) and, with an order, a second
  `sales.quote.approve` (Manager level), never the same person, never the
  pricer.
- The checker's three outcomes as Bravo's: approve, return (to the pricer,
  with a reason), refuse (Không duyệt: the quote is declined, reason
  `commercial` or the reason given).
- Roles stay few (Đạt, 10-27): "ASV" and "Manager" map to the existing
  roles and permission sets; no new role unless Đạt asks.

## Acceptance

1. A quote with an order needs both decisions, by two different people,
   neither the pricer.
2. "Không duyệt" ends the quote as declined with its reason.

## Decided (2026-11-23, Đạt ("làm theo khuyến nghị"))

DW1's quote approval follows WIV-03-023 §4, as the shape above says: ASV
level is the existing quote approver (the head or `sales_quote_approver`),
Manager level a permission set, no new role; Bravo's three outcomes.

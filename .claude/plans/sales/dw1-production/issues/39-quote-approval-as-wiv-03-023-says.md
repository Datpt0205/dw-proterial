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

## How it is built (planned 2026-11-23, before code)

- **"With an order"** is the quote's own link, `QuoteCase.from_order` (a quote
  opened from a PO case), stamped when the case opens; nothing a person types
  and no second field that could disagree with it. A quote Sales opens by
  hand for a customer who already sent the PO is the open question below.
- **Level 1 stays the run's pause** (`sales.quote`, `sales.quote.approve`,
  the graph unchanged, no new `GRAPH_VERSION`). Approved without an order:
  `approved`, as today. Approved with one: a new state `checked`, and a
  run-less approval `sales.quote.manager` opened in the same transaction
  (`ApproveAndResumeService`'s `.decided` outbox path, as `bravo_write.*`
  uses), required scope `sales.quote.manager_approve`, makers the pricer,
  the submitter **and the level-1 checker**, so three different people.
- **Level 2** (`sales.quote.manager.decided` handler in dw_sales): approve
  moves `checked` to `approved` on the same document hash, then the
  existing "đã duyệt" notice and the order's resume; return goes back to the
  pricer; refuse declines.
- **Bravo's third outcome, "Không duyệt"**: at either level, a decision whose
  comment starts the reason code `refuse:` declines the quote
  (`declined_reason="refused"` plus the words), not returns it. Needs the
  approvals page to offer it as a third button for `sales.quote*` only;
  the platform's decision stays approve/reject.
- **Scope and set**: `sales.quote.manager_approve` declared in
  `SalesScopes`, seeded in a permission set `sales_quote_manager` by
  migration (grants and the roles test), held by the head by default; no
  new role (Đạt, 10-27).
- **Tests first**: two decisions by two different people neither the
  pricer; the checker refused as manager; a manager decision on a quote
  without an order refused; "Không duyệt" declines at both levels; the send
  refused while `checked` (where the send happens, not the button).
- **Open (ask Sales with the plant list)**: a quote opened by hand while the
  PO already exists counts as "with an order"? Default: no (level 1 only),
  the PIC may open it from the PO case instead.

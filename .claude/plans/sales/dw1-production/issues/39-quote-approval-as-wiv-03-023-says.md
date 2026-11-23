# 39 — Quote approval as WIV-03-023 §4 says: ASV checks every quote, a Manager approves one with an order

Status: in-progress — two levels built (2026-11-23): a quotation with an order is checked, then approved by a Manager. Left: Bravo's third outcome "Không duyệt"; the order resuming by itself on the Manager's approval (today a person's "Kiểm tra lại"); the quote page saying "đã kiểm, chờ Manager" beside the approval panel; pending: Sales' answer on a quote opened by hand while its PO exists
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

## Done (2026-11-23): two levels

- **Built as planned above, with one change**: no new state. The check
  lives on the submission (`QuoteCheck`), so the case stays
  `pending_approval` and a return or a new price takes the check away with
  the document; no CHECK constraint, process map or status label changed.
- **First level** (`sales.quote`, the run's pause): on a quotation opened
  from an order (`from_order`) the approval is a check
  (`QuoteCase.check_for_manager`, event `quote.checked`), and the same
  transaction opens the run-less `sales.quote.manager` approval
  (`decisions.manager_request`): `sales.quote.manager_approve`, makers the
  pricer, the submitter and the checker. `awaiting()` then names it.
- **Second level**: decided on the approvals page; the guard is
  `CaseDecisions.check` (the `sales.` prefix), the worker's handler of
  `sales.quote.manager.decided` is `QuoteManagerSettlement`: approve
  (`approved`, the pricer told), or return to the pricer. A redelivery
  writes nothing.
- **Who**: migration `3748b069dd99` adds the scope to `sales_head` and a
  permission set `sales_quote_manager`; a holder without the scope does
  not see the request (404).
- **Tests**: domain (check, Manager, three people, a return, one level
  without an order, checked once), flow through the world (makers, the
  checker refused, no scope, the Manager's return, delivered twice).
  8 mutations red.
- **Changed behaviour**: the order a quote was opened from used to resume
  on the approval; with two levels the approval lands in the worker, which
  holds no order intake, so the order waits for "Kiểm tra lại" (left).


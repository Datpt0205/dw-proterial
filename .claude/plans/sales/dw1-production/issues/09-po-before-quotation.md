# 09 — A PO for an item with no valid quotation opens a quote case

Status: done (2026-11-16)
Blocked by: none
Category: enhancement

## Why

Drawio 2a: a PO can arrive before any quotation, and Sales then quotes
first. DW1 flags the line (no quotation) and stops there.

## Shape

- From that finding, "Mở báo giá" opens a quote case for the customer and
  the items, linked to the order case. The order waits on it and resumes
  when the quotation is approved.

## Acceptance

1. The order cannot be prepared while its linked quote is open.
2. Approving the quote clears the finding at the order's next check.

## Comments

## Done

- **"Mở báo giá"** (`POST /sales/orders/{id}/quote`, `sales.order.prepare` +
  `sales.quote.prepare`, a person's button on the `quotation_missing` finding;
  no model or tool can call it): opens one quote case for the customer and
  every `quotation_missing` line, its request the PO's own lines anchored on
  the PO's file (`domain/order_quotes.request_from_order`), assigned to the
  order's PIC, its YCBG drafted at once as a mailbox request's is. Quote case,
  link and both audit rows in one transaction. Refused while a quote opened
  from the order is open (`quote_open`, names it): opening twice opens one.
- **The link** both ways: `OrderCase.quote_links` (migration `ae1388cdd714`,
  JSONB array, CHECK), `QuoteCase.from_order` (in the quote's body). Whether
  the order waits is the quote's own status, read where it decides, never a
  copy: approved/sent/recorded or declined = settled; priced again after
  approval = open again.
- **The wait**: `OrderCase.prepare(settled_quotes=...)` refuses any link the
  caller did not read as settled (fail closed); `OrderCommands.prepare` reads
  the linked quotes in its transaction. `quotes_open` in the refusal, said in
  Vietnamese on the page.
- **The resume**: an approved quote's document (`quoted_rows`, shared with
  the master list) is the quotation the order's linked lines are checked
  against, applying from the PO's date (`quoted_for_po`; the order's customer
  only, the line's item only). DW1 rechecks those lines right after the
  approval (best effort, its own transaction); "Kiểm tra lại theo báo giá"
  (`POST .../quote-check`) does the same by hand; every later check of the
  lines (a mapping, a correction, a revision) reads it too.
- **Web**: the button on the finding, "Báo giá mở từ đơn này" on the order
  (status, link, "Đơn chờ báo giá"), "Mở từ đơn hàng PO …" on the quote.
- A PO written in the mail opens a quote too (2026-11-17, below). (The
  reminder and the map, left here before, are done below.)

## Done: the reminder and the map (2026-11-16)

Migration `57bbf61ae6b8` (from `1f037954f3d9`).

- **`waiting_quote`** (`domain/followups.py`): an order before its
  self-check (`orders.quote_wait_statuses()`: checked, in review) linked to
  a quote case still open reminds the PIC once per wait, from the oldest
  open link, after `sales_followups.waiting_quote.remind.after_hours`
  (platform 1.6.0: 24 h, PIC, on). Whether the quote is open is read from
  its own status when the lane reads the cases (`order_quotes.SETTLED`, the
  set `prepare`'s caller reads), never copied onto the order: approved,
  sent, recorded or declined, nothing is owed; the order prepared or closed,
  nothing either. `SqlFollowupStore.cases` joins the link to the quote case
  in the order's own tenant and workspace (and under RLS); a link naming
  another tenant's case reads nothing. The CHECKs admit it like 06's.
- **The map**: the order lane's flow `quote` (`SubflowKey.QUOTE`, step
  `waiting_quote`, in `quote_wait_statuses()`); the BA's flow has no code
  for it, so none is drawn on it. Its setting is placed on O6.
- Tests: `test_followup_waits.py` (fires a day after "Mở báo giá", not
  before; nothing once the quote is declined; nothing past review),
  `test_followup_waits_db.py` (open for priced and pending approval, none
  for approved, sent, recorded, declined; another tenant's quote reads
  nothing).

## Done: a PO written in the mail (2026-11-17)

- "Mở báo giá" on a PO the customer wrote in the mail (AI item 4): the quote's
  request holds the mail's text the order holds (`QuoteRequest.body`, no
  attachment), every anchor the order's.
- Each value a model read that Sales did not correct on the order (and no
  confirmed change replaced) comes `model_read` on the request, so Sales
  confirms it before the YCBG is drafted. The unit is the item's own, never
  flagged. The PO's price is only `stated_target_price`, as a request a model
  read holds it: it never reaches price evidence.
- `QuoteRequest.order_reader` stamps the PO's reader
  (`sales.po_body_extraction@…`). The request has no `reading` of its own: the
  model step was the order's, counted there, and neither the activity log nor
  the labelled cases count it twice. `reading` and `order_reader` together are
  refused.
- `quote_po_not_a_file` now means only that the PO's file is no longer on its
  message.
- Mutations: corrections ignored, the price as a target, no flags, both
  stamps allowed: each turns a test red.

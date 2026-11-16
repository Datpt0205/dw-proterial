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
- Left: a PO read from the mail's text (no file) opens no quote
  (`quote_po_not_a_file`); no follow-up reminds while an order waits on its
  quote; the process map does not draw the wait.


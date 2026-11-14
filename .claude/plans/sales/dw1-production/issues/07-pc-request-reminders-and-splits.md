# 07 — The request to PC, its reminders, and lines split by PC's dates

Status: done (2026-11-15)
Blocked by: none (PC's own request form, if any, improves it)
Category: enhancement

## Why

Drawio 2a: Sales asks PC for delivery dates and chases them, and PC's reply
may split a line into several dates. DW1 reads PC's dates from a pasted
mail (item 7) but drafts no request and sends no reminder.

## Shape

- "Hỏi PC" drafts the request (lines, quantities, requested dates). The
  case waits on PC, with a follow-up from `sales_followups`.
- PC's dates that split a line become delivery schedules (ticket 21), each
  one a row of the paste sheet (ticket 02). Bravo keeps both the first and
  the current confirmed date, so a re-confirmation by PC keeps the first.

## Acceptance

1. A line PC splits in two becomes two schedules whose quantities sum to
   the line's.
2. A re-confirmation keeps the first confirmed date.

## Comments

## Done

2026-11-15:

- **"Hỏi PC"**: `GET /orders/{id}/pc-request` drafts the request from the case
  (`application/pc_requests.py`, words in `sales_handoffs@1.1.0`'s new
  `pc_request` template: each line asked with PRV code, customer code,
  quantity, requested date); the person copies it, DW1 sends nothing and
  stores nothing of it. `POST /orders/{id}/pc-request` ("Ghi đã hỏi PC")
  records `OrderCase.pc_request` (lines asked, who, when): the lines PC has
  not answered, or all of them when PC answered every line (asking again).
- **Reminder**: `sales_followups@1.3.0` adds `waiting_pc` (on, 24 h, the PIC;
  tenant config, placed on step O4 of the process page);
  `Followup.WAITING_PC` is owed from `pc_request.at`, and the request is
  cleared once every line asked has PC's answer, or when the case leaves
  `in_review`/`prepared` (`OrderCase._next`), so nothing fires after the
  answer. Migration `91f83937dbf1` adds `order_cases.pc_request`,
  `order_lines.pc_answer` and `waiting_pc` to the deliveries' CHECK.
- **PC's answer, one line at a time**: `POST /orders/{id}/lines/{n}/pc-answer`
  with each delivery's quantity and PC's date (`OrderCase.pc_answered` /
  `take_pc_answer`, through `OrderIntake._recheck` as ticket 27's change
  takes). A split that does not add up is refused (`split_not_summing`); a
  line the PO prints split takes one date per printed schedule
  (`printed_schedules`). The answer also stands as PC's agreement on a short
  lead time. Case version bumps, event `order.pc_answer_recorded` and its
  audit row in the same transaction; the recorder is a maker.
- **Splits are the line's deliveries**: `OrderLine.delivery_quantities` is the
  one owner (PC's, else the printed schedules, else the line); `deliveries`,
  the confirmation (`confirm`, `confirmed_deliveries`), the PC-mail reader
  (`pc_dates.deliveries`) and the paste sheet read it. `upload_rows` makes a
  row per PC delivery.
- **First and current date**: `PcDelivery.first_date`/`date`; a
  re-confirmation keeps each delivery's first date when PC keeps the
  quantities, else every new delivery takes the line's earliest first date.
  `sales_bravo_upload@2.1.0` fills AG "Ngày XN giao hàng lần đầu" and AH
  "Ngày XN giao hàng" (new `UploadField`s `first_confirmed_date`,
  `confirmed_date`); ticket 38's replay leaves those two columns uncompared
  (a worked example has no PC answer).
- **Dropped when stale**: a customer's change (ticket 27) or a correction of
  a line's quantity or requested date drops that line's PC answer.
- **Web**: "Hỏi PC ngày giao" panel on the order (`pc-request.tsx`): the
  draft with "Chép bản hỏi PC", "Ghi đã hỏi PC", the wait and the next
  reminder, per line PC's deliveries "lần đầu → hiện tại" and "Ghi ngày PC"
  (one dialog per line, a row per delivery). The confirmation drawer takes a
  date per PC delivery, pre-filled with PC's current date.

Not done: the cross-check sheet still lists the PO's printed schedules, not
PC's split (needs `sales_documents` words); the PC-mail reader reads dates
only, so a split's quantities are typed. Owed by Proterial: whether PC has a
request form of its own; the reminder interval they want; how Bravo sets
"Ngày XN giao hàng lần đầu" when PC re-splits a row.

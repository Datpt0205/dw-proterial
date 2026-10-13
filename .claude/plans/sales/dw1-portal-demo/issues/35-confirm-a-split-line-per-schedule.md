# 35 — A line split over several delivery dates is confirmed per schedule

Status: needs-triage
Blocked by: —
Category: enhancement

Found on 2026-10-13 in ticket 21's review (agent, Đạt away).

## What

Ticket 21 keeps every delivery schedule of a PO line through reading, the
checks, the upload file and the cross-check sheet. Confirmation does not:
`confirm` takes one `confirmed_date` per line (`OrderLine.confirmed_delivery_date`),
and the confirmation draft (`order_artifacts.confirmation_draft`) prints the
line's whole quantity on that one date. A customer who asked for 3,050 m on
16/11 and 3,050 m on 01/12 is told 6,100 m on one day.

## Question for Đạt / Proterial

Does PC confirm each schedule's date separately (one confirmed date per
schedule), or does Sales confirm the line and list the requested schedules
unchanged? The first is a decision, a column, an API field and a page
change; the second is a copy change in `sales_emails`.

## Sources (as of 2026-10-13)

- `dw_sales/domain/orders.py` (`OrderLine.confirmed_delivery_date`,
  `record_pc_confirmation`), `application/order_artifacts.py`
  (`confirmation_draft`), ticket 21.

## Comments

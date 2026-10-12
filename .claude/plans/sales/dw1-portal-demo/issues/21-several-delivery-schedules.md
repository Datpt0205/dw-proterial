# 21 — A PO line with several delivery schedules keeps all of them (G36)

Status: ready-for-agent
Blocked by: —
Category: enhancement

Split from ticket 12 on 2026-10-12.

## What

Real POs often split one item's quantity over several delivery dates on one
line ("2,000 m on 15/11, 3,000 m on 01/12"). The reader and `PoLine` carry one
requested date and one quantity, so a split line loses all but one schedule.
The Bravo upload needs one row per schedule.

## Acceptance

1. `PoLine` carries a list of schedules `(quantity, requested_date, anchor)`;
   a line with one schedule is a list of one. The line quantity is the sum
   and is checked against the printed line quantity (mismatch raises the
   existing quantity finding).
2. The Excel and PDF readers read the split shapes the fixtures carry: extra
   rows under one line number, and a "date: qty" list in one cell.
3. The short-lead-time check runs per schedule; MOQ and price per line.
4. `sales_bravo_upload` writes one upload row per schedule, under a new
   version of the mock template (the real template waits on Proterial).
5. The cross-check sheet and the order page show the schedules.
6. Fixtures: one fictional PO per shape, with eval cases; existing fixtures
   produce the same upload file as before (a test pins it).

## Out of scope

- The real Bravo template (ticket 12).
- Rescheduling after confirmation (O5, DW2).

## Sources (as of 2026-10-12)

- `dw_sales/domain/orders.py` (`PoLine`), `domain/order_checks.py`,
  `adapters/readers/`, `application/order_artifacts.py`
  (`upload_values`), `configs/policies/sales_bravo_upload@1.0.0.yaml`.

## Comments

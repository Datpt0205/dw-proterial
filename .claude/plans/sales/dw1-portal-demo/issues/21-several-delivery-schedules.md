# 21 — A PO line with several delivery schedules keeps all of them (G36)

Status: done (2026-10-13; built in dd5ef1d, verified, finished and adversarially reviewed by the agent, Đạt away)
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

## As built

Checked item by item against the code on 2026-10-13 (the build in `dd5ef1d`
was committed unreviewed).

1. `PoLine.printed_schedules` (earliest first, empty for a one-date line) and
   `PoLine.schedules` (a one-date line is a list of one); a validator holds
   `requested_date` and its anchor to the first schedule's.
   `order_checks.check_document` raises `line_total_mismatch` naming
   `line N quantity` / `line N schedules` when they do not add up. It runs
   on the PO as entered too, so a quantity Sales types over a split line is
   held against the printed schedules (test added in this review).
2. Excel: schedule rows under a line (only quantity and date filled; the
   line's own date cell blank, else refused) and a `date: quantity` list in
   the date cell. PDF: the list in the date cell. One parser for the list
   (`adapters/readers/schedules.py`); each schedule anchored at its cell; a
   hidden schedule row flags the line's `requested_date`. A PDF printing
   schedule rows ends the table and is reported by `line_total_mismatch`
   (no customer sends that layout yet).
3. `check_line`: short lead time per schedule, one finding naming each date
   too soon; MOQ, pack and price on the line quantity. The Bravo duplicate
   check compares one entry per schedule.
4. `upload_rows`: one row per schedule (its quantity, date, DW1's suggestion
   for that date, amount = quantity x unit price), under
   `sales_bravo_upload@1.1.0` (MOCK, same columns).
5. Cross-check sheet `sales_documents@1.2.0` lists each schedule beside its
   upload row; the order page shows "N đợt giao" with each date, quantity and
   suggestion, and opens each schedule's source (`schedule:<n>`).
6. Fixtures M34 (`.xlsx`, rows) and M35 (PDF, list; line 1 short of its
   quantity, line 2 too soon); eval case `sales-normal-delivery-schedules`
   (`sales.schedules_kept`) in `sales@1.2.0`;
   `test_upload_rows_pinned.py` pins every one-date PO's upload rows to
   `golden/bravo_upload_rows@1.0.0.json`, captured before the change.

A split line's dates are not typed by Sales (`correctable_fields`, 409
`printed_schedules`): one typed date cannot say which schedule it is.

## Comments

- 2026-10-13, review (agent, Đạt away). Mutation-checked against a green
  baseline, each killed: lead time on the first schedule only; one upload row
  per line (unit, and the new PostgreSQL test); Excel schedule rows not read;
  the PDF list not read; a split line's date typable; the Bravo comparison
  per line; the suggestion ignoring the lead time; schedules left unsorted;
  the schedule sum check removed. Added:
  `test_a_typed_quantity_its_schedules_do_not_add_up_to_is_line_total_mismatch`
  (unit) and `test_a_line_split_over_several_dates_keeps_each_through_the_store_and_the_file`
  (API integration, M34 read back from PostgreSQL and its upload file
  downloaded: 6 rows). The unit suite ran on the in-memory store only, which
  cannot see a JSON round trip (failure-modes #0).
- Found in review, outside this ticket's acceptance: confirmation is one
  confirmed date per line (`confirm`'s `delivery_dates`,
  `confirmed_delivery_date`), and the confirmation draft prints the line's
  whole quantity on that one date. A split line is therefore confirmed to the
  customer as one delivery. Decided by the agent (Đạt away): not widened
  here; ticket 35 (needs-triage then, done 2026-10-14) holds it, because a
  confirmed date per schedule touches the decision, a column, the API and
  the page, and PC's side of it is Proterial's process.
- Left as is: an Excel `date: quantity` list reads its quantities as plain
  numbers (`3.050` is 3.05); the PDF list uses the layout's separators. A
  misread there cannot pass silently, the schedules no longer add up to the
  line (`line_total_mismatch`).
- 2026-10-13, `reviewing-feature-security` (agent). Tenant isolation: no new
  table, query, cache key or object path; schedules ride in the line's
  `po_line` JSON in the RLS'd `sales.order_lines`, read back in the new API
  test. Authorization: no new route; `DeliveryScheduleView` carries no
  amount; a split line's date is refused in `OrderCase.corrected`, not only
  on the screen. Autonomy: no agent reach. Provenance: every schedule keeps
  its cell's anchor. Lifecycle: nothing created. **Untrusted content: found
  and fixed.** The `date: quantity` entry pattern (lazy groups between
  optional spaces) backtracked cubically on customer text: 1.2 s at 1,000
  characters, 9.4 s at 2,000, 75.6 s at 4,000 (measured), all inside the
  process reading the mail. It is a split at the colon now, linear;
  `test_a_long_padded_list_entry_is_refused_in_time_linear_in_its_length`
  went red with the pattern put back. The same search found a pre-existing
  quadratic pattern in the PDF reader's total (`_TRAILING_WORDS`, 3.2 s at
  16,000 characters), replaced by a word walk, with tests that go red with the
  pattern back. Ticket 25's wall clock is the containment for whatever such
  shape is left.

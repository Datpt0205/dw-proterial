# 35 — A line split over several delivery dates is confirmed per schedule

Status: done (2026-10-14; built, mutation-checked and reviewed by the agent, Đạt away; not committed; integration tests written and owed while Docker is down, see Owed)
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

## Triage (2026-10-14, agent, Đạt away)

Category: enhancement. State: ready-for-agent. Đạt asked on 2026-10-14 for
35 and 36 to be triaged and done now.

Claims checked against the code (as of 2026-10-14):

- `OrderCase.confirm` takes one date per line (`delivery_dates:
Mapping[int, date]`) into `OrderLine.confirmed_delivery_date`; the route's
  `LineDate` is `{line_no, confirmed_date}`. **True.**
- `confirmation_draft` prints each line once, its whole quantity beside that
  one date. **True.** Found besides: `portal_checklist` (O10 for a customer
  who confirms on its own portal) has the same shape, one row per line, the
  whole quantity, one date. Both follow.
- The upload file and the cross-check sheet: already a row per schedule with
  DW1's suggestion for it (ticket 21), and both are made before confirmation
  (`bravo_upload` from `prepared`, `cross_check_sheet` at
  `uploaded_to_bravo`), so no confirmed date exists when they are drawn.
  Nothing to change; a test pins that they still hold M34's schedules.
- Short lead time: `check_line` raises one `requested_date_short_lt` per
  line naming every schedule too soon (ticket 21), PC's agreement is per line
  (`pc_confirmed_by`), and `confirm` refuses a short line without it. That
  agreement covers each schedule the finding names, so it stays per line;
  with dates per schedule, each schedule's DW1 suggestion is now what the
  confirm drawer pre-fills.

Redundancy: none. O5 (rescheduling after confirmation) is DW2 and out of
scope; no other ticket touches confirmation dates.

- **Decided by the agent (Đạt away), 2026-10-14: one confirmed date per
  schedule** (the question's first option, the recommended default). The
  second, a line confirmed once with its requested schedules listed
  unchanged, would tell the customer a too-soon schedule's requested date
  as if PC had agreed to it, and gives Sales no way to move one schedule
  without the others. The first holds the second: Sales may confirm each
  schedule on its requested date. If Proterial says PC confirms the line
  once, the draft's copy changes and the extra dates go; nothing else.

Brief: `OrderLine` keeps a confirmed date per delivery (a split line's
schedules, one for any other line), stored as one `date[]` column replacing
`confirmed_delivery_date` (a new migration, backfilled); `confirm` refuses a
split line that does not get exactly one date per schedule (422), and the
route's `LineDate` takes `schedule_dates` for such a line beside
`confirmed_date` for any other; the views show each schedule's confirmed
date; the confirmation draft (new copy `sales_emails@1.2.0`, words for a
schedule list in vi/en/ja) and the portal checklist (a row per schedule)
print each schedule's quantity and date; the confirm drawer asks a date per
schedule, pre-filled with DW1's suggestion for each. Tests: M34 confirmed per
schedule through the domain, the draft and the checklist; M35 with its short
lead time agreed by PC; a split line given one date is refused; the API
round trip of the array column (integration, owed while Docker is down).

## As built (2026-10-14, agent, Đạt away; not committed)

- `domain/orders.py`: `OrderLine.confirmed_delivery_dates` (one per delivery,
  in the schedules' order) replaces `confirmed_delivery_date`, which is now a
  property (the one date of a line delivered once, None for a split line);
  `deliveries`, `confirmed_schedules()`; a validator refuses any other count
  of dates whatever builds the line (a stored row included). `confirm` takes
  `Mapping[int, Sequence[date]]` and refuses a miscount with 422
  `date_per_schedule`, naming the lines. A recheck keeps the dates.
- `presentation/routes.py`: `LineDate` is `{line_no, confirmed_date}` for a
  line delivered once or `{line_no, schedule_dates: [...]}` for a split line,
  exactly one of the two (422 otherwise). `orders_service.py` passes them on.
- `application/views.py`: `DeliveryScheduleView.confirmed_delivery_date`;
  the line's `confirmed_delivery_date` is None on a split line.
- `application/order_artifacts.py`: the confirmation draft lists a split
  line's schedules ("theo 2 đợt: 6100 m ngày 18/11/2026; 6100 m ngày
  02/12/2026"), in copy `sales_emails@1.2.0` (words `schedules`/`schedule` in
  vi, en, ja; nothing else changed); the portal checklist has a row per
  schedule. Upload file and cross-check sheet unchanged (Triage).
- Persistence: `sales.order_lines.confirmed_delivery_dates date[]`
  (`tables.py`, `persistence/orders.py`), migration `b2afb906fbf2`: the
  column replaces `confirmed_delivery_date`, backfilled (a line confirmed
  before holds its one date for each delivery, as it was told to the
  customer; the touch trigger held so `updated_at` keeps its time),
  `ck_order_lines_confirmed_delivery_dates` (non-empty, one dimension, no
  NULL); downgrade refuses while a line holds different dates per schedule.
- Web: the confirm drawer asks a date per schedule of a split line,
  pre-filled with DW1's suggestion for each, and sends `schedule_dates`; the
  lines table shows each schedule's confirmed date and "Đã xác nhận theo N
  đợt". `contracts/openapi/openapi.json`, `generated/sales.d.ts`
  regenerated.
- Eval world and `sales_flow.dates` send one date per delivery.
- Tests: `test_orders.py` (3 new: per schedule, a miscount refused both ways,
  the invariant); `test_artifacts.py` (M34 draft, M34 portal checklist, M35
  with PC's agreement, the order view); `delivery-schedules.test.tsx` (the
  drawer's body, the per-schedule display); API integration
  `test_a_split_line_is_confirmed_per_schedule_through_the_store_and_the_draft`
  (M34 through PostgreSQL, one date refused 422, the draft downloaded).

Mutation checks (each against a green baseline, restored): count check in
`confirm` removed; the `OrderLine` invariant removed; `deliveries` always 1;
the draft printing a split line's first date only; one checklist row per
line; schedules' confirmed date dropped from the view; the drawer sending
`confirmed_date` for a split line; the per-schedule display removed. All
red.

`reviewing-feature-security`: tenant isolation (no new table or query; the
column is on RLS'd `sales.order_lines`, read back through the API in the
integration test); authorization (unchanged route and scope,
`sales.order.prepare`; the count is enforced in the domain, not the
drawer); autonomy (no agent reach); untrusted content (dates are typed
`date`, at most 1,000 per line; copy words filled by `string.Template`);
audit (`order.confirmed` as before, in the write's transaction); defaults
(no dates: the draft is refused `confirmed_date_missing`; a miscount is
refused, never padded).

## Owed when Docker is back (WSL hung since 2026-10-13 22:01)

```sh
set -a; . ./.env; set +a
uv run alembic -c db/alembic.ini heads          # one head (0a78ca5e96d3 on 2026-10-14, ticket 25 on top of 26a5276840ba)
uv run pytest -m integration apps/api/tests/integration/test_sales_api_artifacts.py \
  apps/api/tests/integration/test_sales_api_orders.py \
  packages/python/dw_sales/tests/integration/test_sales_schema.py \
  packages/python/dw_sales/tests/integration/test_sales_store.py
uv run pytest -m integration packages/python/dw_sales apps/api/tests/integration -k sales
```

Then on a scratch database: `alembic downgrade 13c687788955` and `upgrade
head` with a confirmed split line stored (the downgrade must refuse while its
dates differ), and the mutation "the persistence writes only the first date"
against the integration test above.

## Comments

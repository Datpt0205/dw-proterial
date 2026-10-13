# 24 — The overview aggregates in SQL

Status: done (2026-10-13; built and adversarially reviewed by the agent, Đạt away; not committed)
Blocked by: —
Category: enhancement

Split from ticket 12 on 2026-10-12 (noted under ticket 05).

## What

`OverviewService.overview` and "my work" load every order, quote, message and
event of the workspace (`list_all()` on each) and count in Python. At real
volume (a year of POs) every page view reads the whole history.

## Acceptance

1. Counts by status, waiting times and the work items are computed by SQL
   aggregates in the Sales repository adapter, behind a port the overview
   service declares; the service no longer calls `list_all()`.
2. "My work" pages with keyset pagination; each ORDER BY it pages on has an
   index leading with `tenant_id` (and `workspace_id`), shipped in a new
   migration.
3. Same answers as today: a test runs the old Python computation and the new
   SQL over the demo seed and asserts equal views (keep the old one in the
   test only).
4. RLS still narrows everything: the cross-tenant and cross-workspace
   negative tests pass unchanged.
5. `EXPLAIN` on a seeded table of 50,000 cases shows index use for the
   paged query (recorded in Comments, not asserted).

## Out of scope

- New overview metrics.

## Sources (as of 2026-10-12)

- `dw_sales/application/overview_service.py` (`overview`, the my-work
  query), the Sales persistence adapter, `CLAUDE.md` "Data model rules".

## Comments

- Decided by the agent (Đạt away), 2026-10-13: **one port, two questions.**
  `OverviewReadPort` (`application/overview_ports.py`), a member of the Sales
  unit of work, answers `figures(basis)` and `work_page(filter, page)`. What
  the figures are computed against (whose time each status is, the
  draft-ready status per kind, the surveyed steps and their states, the zone
  a month is counted in) and which steps a caller may take are handed down by
  `OverviewService`, which owns them; the SQL restates none of it (arrays
  passed as parameters, `figure_basis`).
- Decided by the agent (Đạt away), 2026-10-13: **the store narrows, the
  service decides.** `WorkFilter` is built from `_ORDER_NEXT`/`_QUOTE_NEXT`
  and the caller's scopes; each row of a page is then decided by the same
  rules as before (an order awaiting its cross-check is read whole for
  `awaited` and its makers). A page can therefore hold fewer items than its
  limit; `next_cursor` alone says whether more follow.
- Decided by the agent (Đạt away), 2026-10-13: **`GET /my-work` is a page
  (`limit` up to 200, `cursor`), and the web reads every page.** The work
  list's screens count across it (overdue, due soon, per tab) and ask whether
  one case is the caller's, so `SalesApi.myWork()` walks the cursors; a "load
  more" would make those counts lie. The total is bounded by the caller's
  open work, no longer by the workspace's history. `myWorkPage()` is one page.
- Decided by the agent (Đạt away), 2026-10-13: **the sort key leads with a
  date, so the kernel cursor carries an optional `group`** (a text sort
  component before the timestamp; empty and not written for every other
  listing, whose cursors are unchanged). The work list sorts by (due date or
  9999-12-31, received, row id), as before up to ties, which now break by row
  id instead of list order.
- Decided by the agent (Đạt away), 2026-10-13: **columns for the order the
  indexes carry.** `order_cases.received_at` (the current revision's) and
  `quote_cases.received_at` are written by the repositories on every save and
  backfilled (with `touch_updated_at` disabled for the backfill, so
  `updated_at` keeps its value); `quote_cases.quote_due` is GENERATED from the
  body as ISO text. Partial indexes `ix_order_cases_open_work`,
  `ix_quote_cases_open_work` (not settled: confirmed or closed,
  master_list_recorded or declined) and `ix_messages_routed_work`, each
  leading `(tenant_id, workspace_id)` (migration `6d0252a87a6c`). The settled
  statuses are written into the statements as literals so a generic plan
  matches the predicates; `tests/unit/test_overview_reader.py` fails if a
  work-list step ever lands on one.
- `CaseEventLogPort` and `SqlCaseEventLog` had the overview as their one
  reader and are removed with it.

### Review (2026-10-13)

Found and fixed while measuring, before the ticket closed:

1. **The work list sorted every open row of the tenant.** The RLS policy's
   workspace test is `workspace OR workspace_scope = 'tenant'`, which no index
   can seek on, so each branch read the tenant's open rows and sorted them
   (EXPLAIN on 50,000 cases: an Index Scan of 900 rows, then a top-N Sort).
   The statement now names the scope's workspace, as `SqlAuditRepository`
   does: Index Cond on `(tenant_id, workspace_id, ROW(received_at, id) > ...)`,
   51 rows read, no sort but the merge's.
2. **The figures comparison was flaky.** A sum in SQL is exact and a sum of
   Python floats is not; seconds are compared to the microsecond
   (`math.isclose`), not by rounding, which flips at a boundary.

Acceptance 5, measured on a throwaway database (`dw_scratch_t24`, dropped
after): one tenant, 50,000 order cases (49,000 closed, 1,000 in review over a
year, half assigned to the caller), 2,000 messages routed to Sales, analysed.
Page 3 of the caller's work, `plan_cache_mode = force_generic_plan`:

```
Limit (actual time=0.321..0.327 rows=51)  Buffers: shared hit=9
  -> Sort  Sort Key: ($2), order_cases.received_at, order_cases.id   (the merge)
     -> Append
        -> Limit -> Index Scan using ix_order_cases_open_work on order_cases
             (actual rows=51)  Index Cond: tenant_id = <app.tenant_id>
             AND workspace_id = $3 AND ROW(received_at, id) > ROW($7, $8)
        -> Subquery Scan -> Limit -> Sort -> Seq Scan on quote_cases (0 rows)
        -> Limit -> Index Scan Backward using
             ix_messages_tenant_id_workspace_id_processed_at_id (actual rows=51)
Execution Time: 0.537 ms        (custom plan: 4.1 ms)
```

Pages 1 to 3 answered in 77, 34 and 21 ms through the adapter (connection
warm-up in the first). The overview's figures over the 50,000 cases: 368 ms;
they are aggregates over all time, which no index makes free.

Mutation checks (each against the passing tree, then restored):

- DW1's own statuses counted as a person's time: the figures comparison red;
- the assignee rule dropped from the order branch: the page walk red (Diệu
  listed An's cases);
- the keyset condition ignored for orders: the page walk red (rows twice);
- the settled-status predicate dropped, the due-date expression bound as a
  parameter, the workspace not named: the index test red each time (a second
  `Sort Key`, or the partial index unused).

`reviewing-feature-security`: tenant isolation (another tenant and another
workspace read no figure and no work; the cursor carries tenant, workspace
and principal, and Diệu replaying An's cursor gets 422); authorization
(unchanged scopes; the viewer's 403 test stands); untrusted content and
autonomy (no document text, no agent reach; SQL literals are enum values
only); audit (read-only); defaults (a caller with no scope gets an empty
filter, and every row is decided again). `reviewing-deployment-security`:
two query parameters on an existing route; no header, origin, image or secret.

### As built (2026-10-13)

- `packages/python/dw_kernel/src/dw_kernel/pagination.py`
  (`CursorPosition.group`) and `tests/unit/test_pagination.py`.
- `packages/python/dw_sales/src/dw_sales/application/overview_ports.py` (new),
  `overview_service.py` (figures, the paged work list, `figure_basis`;
  `KpiPort` is ticket 19's), `case_store.py` (`overview` on the unit of work;
  `CaseEventLogPort` gone).
- `packages/python/dw_sales/src/dw_sales/adapters/persistence/overview.py`
  (new, `SqlOverviewReader`), `orders.py` and `quotes.py` (`received_at`
  written; `stored_quote` public), `records.py` (`disposition_of` public,
  `SqlCaseEventLog` gone), `tables.py`, `uow.py`.
- `packages/python/dw_sales/src/dw_sales/evals/overview_memory.py` (new: the
  old Python computation as `PythonOverviewReader`), `evals/world.py`,
  `evals/graders.py`.
- `packages/python/dw_sales/src/dw_sales/presentation/routes.py` (`GET
/my-work` paged).
- `db/migrations/versions/6d0252a87a6c_sales_open_work_indexes_and_received_at.py`.
- `packages/typescript/api-client/src/sales.ts` (`myWorkPage`; `myWork` walks
  the pages), `contracts/openapi/openapi.json`, `generated/sales.d.ts`.
- Tests: `apps/api/tests/integration/test_sales_overview_sql.py` (new, five
  tests), `packages/python/dw_sales/tests/unit/test_overview_reader.py` (new),
  and the page's `items` read in `test_sales_api_overview.py`,
  `test_sales_api_assignment.py`, `test_case_reassignment.py`,
  `test_cross_check_recovery.py`.

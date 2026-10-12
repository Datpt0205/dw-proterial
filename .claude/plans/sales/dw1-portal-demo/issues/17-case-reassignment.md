# 17 — The head reassigns a case (G22)

Status: ready-for-agent
Blocked by: —
Category: enhancement

Moved out of ticket 12 on 2026-10-12: it needs nothing from Proterial and
closes a gap in Q1 ("assign from the customer's Sales PIC") of the demo flow.

## What

A case's `assigned_to` is stamped when the case opens, from the customer's
Sales PIC email matched against workspace members, and never changes. No
route changes it, so a wrong or absent PIC can only be worked around:
unassigned cases show to every PIC. Verified 2026-10-12: no reassign route,
`sales.case.assign` not declared (the sales roles migration defers it to the
route that reads it).

## Acceptance

1. `sales.case.assign` is declared in a new migration (alembic random
   revision id) and granted to `sales_head` only, with the privileges and
   migration tests updated.
2. `PUT /api/v1/sales/{orders|quotes}/{case_id}/assignee` with
   `{assignee: uuid | null, case_version}`:
    - requires `sales.case.assign`;
    - the assignee must hold the scope that works the case
      (`sales.order.prepare` for an order, `sales.quote.prepare` for a quote)
      in the case's workspace, answered by `ScopeHoldersPort.holding`, the
      same function the access context is built from; anyone else → 422;
    - `null` unassigns;
    - a stale `case_version` → 409; idempotency key as on other mutations;
    - a closed case → 409.
3. The case version increments; one audit row with old and new assignee
   ids, in the same transaction.
4. The new assignee is notified through `NotificationSenderPort`
   (idempotent by source key).
5. Web: the case header shows the assignee and, to a holder of
   `sales.case.assign`, a "Phân công lại" action (antd `Select` of the
   eligible members). Hidden for others, and the API refuses them anyway.
6. Negative tests: `sales_pic` → 403; an assignee from another workspace or
   tenant → 422; an assignee without the working scope → 422; a support
   context → 403.
7. The overview and "my work" lists follow the new assignee.

## Out of scope

- Reassigning the maker of a step already done (makers are history, and
  maker/checker reads `makers`, not `assigned_to`).
- Bulk reassignment.

## Sources (as of 2026-10-12)

- `dw_sales/application/case_store.py` (`CaseOrigin`),
  `application/inbox_service.py` (`_assignee`),
  `application/overview_service.py` (assignee visibility),
  `application/ports.py` (`ScopeHoldersPort`, `NotificationSenderPort`).
- Migration `68305ebe4a83` (deferred scopes); spec "Roles", ticket 12 (G22).

## Comments

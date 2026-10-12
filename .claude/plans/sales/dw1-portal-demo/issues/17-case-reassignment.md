# 17 — The head reassigns a case (G22)

Status: done (2026-10-12; not committed)
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

## As built (2026-10-12)

- `sales.case.assign` declared by migration `934101cde272` (random id, after
  ticket 14's `58184771c541`), granted to `sales_head` only;
  `test_sales_roles.py` and `test_sales_personas.py` say so, and the PIC
  lacks it. No column or grant changes: `assigned_to` already existed.
- Routes `GET /orders|quotes/{id}/assignees` (who may be given the case,
  with names) and `PUT /orders|quotes/{id}/assignee`
  `{assignee: uuid | null, case_version}` with `Idempotency-Key`; both on
  `sales.case.assign` at the route and again in `AssignmentService`
  (`dw_sales/application/assignment.py`), which also refuses a support
  context outright, whatever its grant stamped.
- Eligibility is `ScopeHoldersPort.holding(tenant, workspace,
{sales.order.prepare | sales.quote.prepare})`, the function the access
  context is built from; the candidate list and the check are the same call.
  Anyone else (another workspace's or tenant's member, a viewer, an unknown
  id) is one 422 (`field: assignee`, `rule: assignee_not_eligible`) that does
  not say whether they exist.
- The case's next version: `OrderCase.reassigned()` / `QuoteCase.reassigned()`
  bump the version and refuse a closed case (409 `case_closed`: an order
  `closed`, a quote with no move left, `declined` or `master_list_recorded`);
  a stale version is 409. The store gained `assign(case_id, assigned_to)`,
  written in the same transaction as the save, its event
  `order|quote.reassigned` (field `assigned_to`) and one audit row whose
  details add `assigned_from` and `assigned_to` (ids). Giving the case to
  whoever has it already changes nothing (no version, no event).
- The new assignee is told after the commit through `NotificationSenderPort`,
  source key `sales.case.assigned:{case}:{version}`, naming the PO or RFQ
  number and who reassigned it, never an amount. As with the pause, a
  delivery failure after the commit answers 500 while the change stands.
- Web: "Phân công lại" in the order and quote headers
  (`_components/reassign.tsx`), drawn only for `sales.case.assign`; an antd
  `Select` of the API's candidates plus "Không giao ai", sent with the case
  version and a key per press; the "Phụ trách" cell already shows the
  assignee. My work and the lists follow `assigned_to`, so they follow the
  new assignee (tested in the unit and API suites).
- Tests: `dw_sales/tests/unit/test_case_reassignment.py` (12),
  `apps/api/tests/integration/test_sales_api_assignment.py` (7),
  `apps/web/app/sales/_lib/__tests__/reassign.test.tsx` (2), service scope
  entries in `test_service_scopes.py`. Negatives: a PIC 403 (route and
  service), an assignee from another tenant or without the working scope 422,
  a support context 403, another workspace's case 404, stale 409, closed 409.
- Mutation checks, each red after a passing baseline: the support refusal,
  the service's scope check, the eligibility check, the version check, the
  closed refusal, the audit's old/new ids, the notification, the stored
  assignee; on the web, the control drawn for everyone and the case version
  not sent. Not red when removed alone: the route's scope dependency (the
  service refuses the same caller first; both stay).

## Comments

# 14 — An order whose cross-check decision failed to apply can be cross-checked again

Status: done (2026-10-12; committed in 4027c0d)
Blocked by: —
Category: bug

## What

Verified 2026-10-12. The cross-check decision is checked twice: the guard
inside `ApproveAndResumeService.decide` (`CaseDecisions.check`, write=False)
commits the approval as decided, then `runner.resume` applies it
(`_decide(write=True)`), which repeats the version check. Anything that bumps
the case version between the two without changing its status (acknowledging
a finding, recording a PC confirmation) makes the apply raise
`ConflictError`; the runner marks the run FAILED.

The order is then stuck:

- the approval stays APPROVED/REJECTED, the run FAILED, the order
  `uploaded_to_bravo`;
- `bravo-entry` needs `prepared`, `apply_change` needs `change_review`,
  `confirm` is refused while a cross-check is required, `withdraw` skips a
  decided approval;
- the overview still shows cross-checkers a "cross_check" work item with no
  approval to decide;
- the only way out is a customer's revised PO.

Quotes do not have this: `pending_approval → priced` is allowed, and
re-submitting withdraws and raises a fresh approval.

## Acceptance

1. **Reproduce first** (`/diagnosing-bugs`): a test that decides the
   cross-check, bumps the case version before the resume applies it, and
   asserts the order can still reach `cross_checked`. Red before the fix.
2. An order in `uploaded_to_bravo` with no PENDING cross-check approval and
   no running cross-check run offers one step, "Gửi kiểm chéo lại", to the
   person who recorded the Bravo entry (the maker) or a `sales_head`. It
   starts a new `order_cross_check` run at the current case version and
   raises a new approval. Refused (409) while an approval is pending or a run
   is running, so it never makes two.
3. The failed apply leaves a trace a person can read: an audit row naming the
   run, the approval, and the reason code (`stale_case_version`), ids only.
   The order page says the earlier decision was not applied and why.
4. Maker/checker is unchanged: the new approval excludes the same makers;
   the person who decided the failed one may decide again.
5. The overview's "cross_check" work item shows only while an approval is
   pending; the stuck state shows as a work item for the maker instead.
6. Negative tests: re-raise while pending → 409; by a non-maker `sales_pic`
   → 403; for another workspace's order → 404.

## Out of scope

- Making the platform's decide and apply one transaction. The recovery
  step covers any failed apply (a version race, a crashed run), which a
  narrower fix to the race would not.
- Refusing version-bumping actions while a cross-check is pending: possibly
  wanted later, but PC confirmation can legitimately arrive then.

## Sources (as of 2026-10-12)

- `dw_sales/domain/orders.py` (`OrderStatus`, `_NEXT`, `record_bravo_entry`,
  `apply_change`, `confirm`), `application/runs.py`
  (`Dw1Runs.record_bravo_entry`), `application/decisions.py` (`check`,
  `_decide`, `_still_waiting`), `workflows/graph.py` (`decide` node),
  `application/overview_service.py`.
- `dw_agent_runtime/approval_flow.py` (`decide`, `withdraw`),
  `adapters/langgraph_runner.py` (`_fail`).
- `sales.md` Open "From ticket 10"; ticket 10 line 100.

## As built (2026-10-12)

- **Reproduced first.** `dw_sales/tests/unit/test_cross_check_recovery.py`
  wraps the Sales decision guard so An acknowledges NOC/ESF on M03 between
  the guard and the resume: the approval ends APPROVED, the run FAILED, the
  order at `uploaded_to_bravo` with no pending approval. Red before the fix
  (no way out); the API suite repeats it through the routes
  (`apps/api/tests/integration/test_sales_api_cross_check_recovery.py`).
  A second way to strand an order was found on the way: `POST bravo-entry`
  on an order already in Bravo withdrew its pending cross-check before the
  run refused the step. It is now refused (409) before anything is
  withdrawn.
- **The trace.** `CaseDecisions.apply` catches the case's refusal of the
  decision (any `DWError`), and for an order records it before re-raising
  (the run still ends FAILED): `OrderCase.decision_not_applied` stamps an
  `UnappliedDecision` (approval id, run id, decider, outcome, the version
  decided on, reason code, time) with event `order.decision_not_applied`
  (DW1's, initiated by the decider) and one audit row naming the run
  (`run_id`), the approval (`details.approval_id`) and `reason_code`; ids and
  codes only. The reason code is the refusal's `rule` (`same_version` now
  says `stale_case_version`), else its error code. A case that already moved
  on gets the audit row only. The platform's resume payload now names the
  approval (`approval_id`), the one line the graph needed to say which.
- **Stored** in `sales.order_cases.unapplied_decision` (jsonb, migration
  `58184771c541`). Its CHECK holds it to `uploaded_to_bravo` and to exactly
  `UnappliedDecision`'s keys with a code-shaped `reason_code`, so a comment
  or an amount has no field there (`test_sales_schema.py` compares the keys;
  the API suite shows a stranger key, a missing code and an amount-shaped
  code refused). Writing Python `None` as JSON `null` was caught by this
  CHECK on the first run: the column is `JSONB(none_as_null=True)`.
- **"Gửi kiểm chéo lại"**: `POST /orders/{id}/resend-cross-check`
  `{case_version}` with `Idempotency-Key`, route scope `sales.order.prepare`.
  `Dw1Runs.resend_cross_check` reads the case (404 elsewhere), checks the
  version (409), lets the case refuse (`OrderCase.resend_cross_check`: 409
  unless it awaits its cross-check; 403 unless the caller recorded the Bravo
  entry or holds the new `sales.order.resend_cross_check`, granted to
  `sales_head` only by the same migration), then refuses 409 while an
  approval is pending (`cross_check_pending`) or any DW1 run about the order
  is unfinished (`dw1_running`, read from the run store's `active_since`,
  which nothing read before). It starts an `order_cross_check` run; its step
  (`CaseDecisions.record_bravo_entry`, which now picks the step by the
  order's state) asks the case again and bumps the version, so two presses
  at once meet the version and never raise two. Graph and worker versions
  are unchanged: the graph's code is not.
- **Maker/checker unchanged**: the new approval names `OrderCase.makers` as
  before; whoever re-raises is its requester (the platform excludes the
  requester), and the decider of the failed one may decide again.
- **The order page** shows "Quyết định kiểm chéo trước chưa được áp dụng vào
  đơn" with who decided which way, on which version, the reason
  (`NOT_APPLIED_REASON`, glossary "Not-applied reasons") and who acts; the
  button "Gửi kiểm chéo lại" is offered to the recorder and the head, and
  disabled with the reason in words for any other PIC. `OrderCaseView`
  gains `cross_check_stalled` and `unapplied_decision`.
- **My work**: `cross_check` only while an approval is pending; a stalled
  order is `resend_cross_check` for its Bravo recorder (the head acts from
  the page). Left as it was: an order at `uploaded_to_bravo` whose rules need
  no cross-check still shows the `cross_check` item (pre-existing; closed
  2026-10-15, `867d330`: My work offers `confirm` to the PIC for such an
  order). Still open: the web review page (`app/sales/review/page.tsx`)
  lists every `uploaded_to_bravo` order as a cross-check without reading
  `cross_check_required`, so it and My work disagree about one order (read
  path drift); it should filter on the field or read `awaiting()` from the
  API. Carried with it: `OrderCase.confirm()` accepts
  `cross_check_required=None` (legacy) at `uploaded_to_bravo`, while
  `awaiting()` treats None as needing a cross-check. Owed on Docker:
  `test_sales_overview_sql.py`.
- **Mutation checks** (each turned a test red, after a baseline run passed):
  the case's authority check; the pending and the unfinished-run refusals;
  the bravo-entry status pre-check; the trace in `apply`; the stalled branch
  of my-work; clearing the record when the order moves on (needed a test of
  its own, added); the `stale_case_version` rule code; on the web, the
  page's explanation, the offer to everyone, the offer to no one.

## Comments

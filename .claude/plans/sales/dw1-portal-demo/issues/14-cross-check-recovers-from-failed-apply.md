# 14 — An order whose cross-check decision failed to apply can be cross-checked again

Status: ready-for-agent
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

## Comments

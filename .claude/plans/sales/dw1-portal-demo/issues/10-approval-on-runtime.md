# 10 — Move the Sales decision onto the runtime

Status: done (2026-10-06, not committed)
Blocked by: 09

## What

Replace the context-recorded decision (spec decision 5, dw_sales ADR 0001)
with a versioned graph. It pauses on `interrupt` into the platform approvals
inbox and resumes, so approval, autonomy and audit come from the runtime.

## Acceptance (G19)

1. Each approval type declares its decide-scope (`sales.quote` →
   `sales.quote.approve`; `sales.order.cross_check` →
   `sales.order.cross_check`), checked in `ApproveAndResumeService.decide`.
   `GET /approvals` lists only approvals the caller may decide or requested.
2. The interrupt payload names the case's maker (`priced_by` /
   `prepared_by`), and the strict check excludes that person. Wire
   `strict_approval_prefixes |= {"sales."}` at the composition root, with
   `requested_by` set to the maker, not to whoever pressed "DW xử lý".
3. Approval payloads, run results and audit details carry the case id,
   version and hash only, never an amount.
4. `RunAllowancePort` is checked when processing starts, including
   mailbox-triggered runs.
5. `configs/workers/sales.yaml` and the graph are pinned in the release
   manifest.
6. A model turn that reads email or attachment content gets a toolset with
   no outbound tool (ADR 0007).
7. The context-side decide endpoints are deleted in the same change, with a
   test that they are gone.

Negative tests:

- the purchasing manager decides a `sales.quote` → 403;
- the maker decides → 409;
- `dev|dieu.hoang`, holding `approver_boost`, cannot approve a quote she
  priced.

## As built (2026-10-06)

dw_sales ADR 0004 (Proposed) records the decision and supersedes ADR 0001;
spec decision 5 is amended. Per acceptance line:

1. **Decide scope per type.** `dw_sales.application.runs.DECIDE_SCOPES` is the
   one map (`sales.quote` → `sales.quote.approve`, `sales.order.cross_check`
   → `sales.order.cross_check`). The interrupt stamps it on the approval
   (`payload.decide_scope`); `ApprovalRequest.required_scope` reads the stamp
   and `ApproveAndResumeService.decide` requires it instead of
   `approvals.decide`. `GET /approvals` and `GET /approvals/{id}` serve only
   what `ApprovalAudience.may_see` allows (the decider's scope or the
   requester), filtered in SQL, in the caller's workspace; the SQL and the
   Python rule are held together by `test_approval_audience.py`. The Sales
   guard refuses a `sales.` approval stamped with any other scope (fails
   closed).
2. **Makers.** The payload names every maker (`OrderCase.makers`: preparer,
   Bravo recorders this round and earlier, typed values; a quote's pricer and
   submitter); the strict check refuses `requested_by` and each of them (409,
   `rule: maker_checker`, "tách nhiệm"). `strict_approval_prefixes |=
{"sales."}` and the guard are wired by `dw_sales.workflows.graph.register`,
   called from `apps/api` `build_sales`. The run starts as the person who
   submits or records the Bravo entry, so `requested_by` is a maker, never
   whoever pressed "DW xử lý".
3. **Ids only.** `DecisionAsked` (extra forbidden): type, scope, reason
   words, case kind/id/version, document hash, makers. The run's input is
   the task (ids, document numbers), its result the outcome code; comments
   and reasons go to the platform decision and the case, never the run row.
4. **RunAllowancePort.** "DW xử lý" (one message or all), submit and the
   Bravo entry are each a DW1 run, so the runner's check where every run
   begins covers them; the steps (`CaseDecisions`) are not on the routes'
   bundle. There is no mailbox trigger yet; one must start a run the same way.
5. **Pinned.** `configs/workers/sales.yaml` (sales-dw1@1.0.0, graph 1.0.0, A1,
   no toolset) is in the release manifest (`sha256:c0f21a1b…`).
6. **ADR 0007.** No toolset on the worker, and the graph takes only its
   steps; `test_dw1_runtime.py` fails if a toolset with an external tool or a
   model reaches DW1.
7. **Gone.** `POST /quotes/{id}/approval` and `POST /orders/{id}/cross-check`
   are deleted (route inventory test, API 404/405 test, the walk). The pages
   decide on the platform approval (`decision.approval_id` on the case view)
   with the reasons, a now-required comment and the case version shown.

Walk: `make test-web-sales` 11/11 on the third run; two earlier runs timed
out at different steps under machine load (no server error; the slow M29
run took 107 s on its row, 0.2 s measured idle).

Negatives: purchasing manager 403, maker 409, Diệu with `approver_boost` 403
on her own quote, viewer (and another tenant) sees no Sales approval; in
`apps/api/tests/integration/test_sales_api_runtime.py`, the unit
`test_dw1_runtime.py` and the eval `sales.separation_of_duties`.

Platform pieces added (none names Sales): stamped decide scope, named makers,
`ApprovalDecisionGuard` with `ProposedDecision` (reasons, subject version),
`ApprovalAudience`, `withdraw`/`waiting` by subject, `WorkflowRunnerPort.withdraw`,
`dw_agent_runtime.testing.memory_runtime` (the eval world runs the real
runner and approval flow).

Open: the generic Approvals page lists Sales approvals to their deciders but
sends no case version, so a decision there is refused (the page is shadcn;
moving it to antd comes first); an order whose decision passed the guard and
failed in the run (a one-request race) has no step that raises its
cross-check again; DW1 has no service principal (ticket 12); processing's
audit rows do not carry the run id (the decision rows do).

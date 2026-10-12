# 16 — DW1 processes new mail on its own: a worker lane over `InboxPort`

Status: ready-for-agent
Blocked by: —
Category: enhancement

## What

DW1 runs only when a person presses "DW xử lý" (`POST /inbox/{id}/process`
or `/inbox/process-all`), under that person's access context and
`sales.inbox.process`. The worker has no Sales lane; `apps/worker` main
carries only the commented seam. Production needs each new message to
start processing without a click, and the mock inbox should exercise the
same path so the demo and the real adapter share it.

Verified 2026-10-12: no consumer is registered; `InboxProcessing.process`
requires an access context holding `sales.inbox.process` and refuses while
DW1 is paused; `RunAllowancePort` is checked where a run starts (ticket 10,
acceptance 4).

## Acceptance

1. A `sales_inbox` lane registered at the worker's composition root
   (`ConsumerRegistry.register`), `dw-sales` declared in
   `apps/worker/pyproject.toml`, the lane named in the worker test that
   asserts the set of lanes.
2. Each tick, per workspace where DW1 is enabled and not paused: list
   messages from `InboxPort`, process each one not yet processed, oldest
   first, with an idempotency key per `(workspace, message_id)`, so a
   message is processed once whether the lane or a person gets there first.
3. The lane audits as itself: `lane_audit_event` with
   `system_actor("sales_inbox")`, `details.actor = "system:sales_inbox"`.
   It never acts as a person.
4. The lane holds `sales.inbox.process` only; it cannot prepare,
   cross-check, price or approve (spec, actor table, "DW1 (tài khoản dịch
   vụ)").
5. The plan quota is enforced: a tenant over `runs_per_day` gets no run from
   the lane, and the message stays unprocessed for the next day, visibly.
6. Pausing DW1 stops the lane for that workspace on its next tick.
7. Negative tests: the lane never processes a message of workspace A under
   workspace B's context; a paused workspace is skipped; a message already
   processed by a person is not processed again.
8. A `ReapTarget` if the lane owns a job queue.

## Questions for Đạt (why needs-info)

1. **Whose authority does the lane carry?** Two shapes:
    - (a) a worker principal per tenant (the spec's production "DW1 tài
      khoản dịch vụ"), resolved by the platform like any member, holding
      `sales.inbox.process` through a role;
    - (b) a system context minted in the lane, like the ingest lane does
      today, with the processing service exposing a lane entry that skips
      the person-scope check;
    - trade-off: (a) keeps "who may act" in one place (`effective_scopes`);
      (b) is smaller but puts a scope check in two places. Proposed: (a).
2. **"DW1 enabled" per workspace**: is it the existing pause state only
   (every workspace with Sales data is enabled unless paused), or a
   separate on/off the head sets? Proposed: pause state only for now.
3. **Tick interval** for the mock: proposed 60 s locally; the real adapter
   decides its own.

## Out of scope

- The Microsoft 365 adapter (ticket 12, needs Proterial's mailbox access).
- Mail authentication (G39, ticket 12).

## Sources (as of 2026-10-12)

- `apps/worker/src/dw_worker/main.py` (commented Sales seam),
  `apps/worker/src/dw_worker/consumers/ingest.py` (`_context_for`, shape b).
- `dw_sales/application/inbox_service.py` (`InboxProcessing`),
  `application/ports.py` (`InboxPort`), `application/support.py` (service
  principal note).
- `dw_platform/domain/audit.py` (`system_actor`, `lane_audit_event`).
- `CLAUDE.md` "Agent and tool rules" (lane audit, plan quota in the runner).

## Comments

- 2026-10-12, Đạt ("làm theo bạn tự recommend"): the proposed defaults hold.
    1. Shape (a): a worker principal per tenant, the spec's "DW1 (tài khoản
       dịch vụ)", resolved by the platform like any member and holding
       `sales.inbox.process` through a role, so `effective_scopes` stays the
       one answer to who may act. The lane never mints a context of its own.
    2. "Enabled" is the pause state only: every workspace with Sales data
       runs unless paused.
    3. Tick 60 s for the mock inbox locally; the real adapter picks its own.

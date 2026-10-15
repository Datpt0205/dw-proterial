# 16 — DW1 processes new mail on its own: a worker lane over `InboxPort`

Status: done (2026-10-12, reviewed, committed in 8ac3d33)
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

## As built

- Lane: `dw_sales/application/inbox_lane.py` (`InboxLane.tick`), paced by
  `apps/worker/src/dw_worker/consumers/sales_inbox.py`, registered as
  `sales_inbox` in `dw_worker.main.build_registry` (60 s), switch
  `DW_WORKER_SALES_INBOX_LANE` (default on).
- Authority: DW1's service account per tenant (subject `dw1_subject`, role
  `sales_dw1` = `sales.inbox.process`, migration `af154486381e`), resolved by
  `SqlMembershipLookup.find_service_access`, cut to `LANE_CEILING`, no role.
- Once per message: skipped if it had a disposition when the tick began or
  has one just before its run; `SqlMessageLog.record` refuses a second
  disposition on a case (`message_already_processed`) for a run racing a
  person.
- DW1 assembled once for API and worker: `dw_sales.adapters.assembly.build_dw1`.
- Tests: `dw_sales/tests/unit/test_inbox_lane.py`,
  `dw_sales/tests/integration/test_sales_inbox_lane.py`,
  `dw_platform/tests/integration/test_service_access.py`,
  `apps/worker/tests/integration/test_sales_inbox_lane_db.py`,
  `apps/worker/tests/unit/test_sales_inbox_consumer.py`,
  `apps/worker/tests/unit/test_worker_sales_settings.py`, `test_worker.py`.

## Comments

- 2026-10-12, Đạt ("làm theo bạn tự recommend"): the proposed defaults hold.
    1. Shape (a): a worker principal per tenant, the spec's "DW1 (tài khoản
       dịch vụ)", resolved by the platform like any member and holding
       `sales.inbox.process` through a role, so `effective_scopes` stays the
       one answer to who may act. The lane never mints a context of its own.
    2. "Enabled" is the pause state only: every workspace with Sales data
       runs unless paused.
    3. Tick 60 s for the mock inbox locally; the real adapter picks its own.

- 2026-10-12, built (agent). What landed, per acceptance:
    1. `sales_inbox` registered at the worker's seam
       (`apps/worker/src/dw_worker/main.py`, `build_sales_inbox_lane`), under
       `dw_sales.application.inbox_lane.SALES_INBOX_LANE`; `dw-sales` in
       `apps/worker/pyproject.toml`; named in `test_worker.py`
       (`test_dw1s_mailbox_lane_needs_a_database_object_storage_and_a_mailbox`).
       Wired with a database, object storage and a bound mailbox; the
       worker builds DW1 with the API's own call, now
       `dw_sales.adapters.assembly.build_dw1`, over a LangGraph runner of
       its own (`dw_worker.composition.build_workflow_runtime`).
    2. `InboxLane.tick`: per workspace, DW1's context, nothing while paused,
       then each message without a disposition, oldest first, through
       `Dw1Runs.process` (one run per message). The idempotency key is the
       message log's unique (workspace, message_id): `SqlMessageLog.record`
       now replaces only a routed disposition and refuses
       (`message_already_processed`) a second one on a case, so of a person
       and the lane the second transaction rolls back.
    3. `lane_audit_event` from `system_actor("sales_inbox")` per message,
       `action = sales.message.processed_by_lane`, naming the account in
       `details.account_id`; the processing's own rows name the account.
    4. Role `sales_dw1` (migration `af154486381e`): `sales.inbox.process`
       only. The account (subject `service|sales-dw1|<tenant_id>`, no email)
       is seeded in tenant-alpha by `seed_dw1_accounts` (demo seed and
       `make demo-reset`); the lane cuts its context to that one scope and
       carries no role, so a role added by hand (even `platform_admin`)
       widens nothing (`SqlMembershipLookup.find_service_access`).
    5. Quota: the run's own `RunAllowancePort` check; the lane stops the
       workspace for the tick on `QuotaExceededError`, the rest stay "Chưa xử
       lý" in the inbox.
    6. Pause: checked before any run each tick, and the run's step refuses
       a pause that lands mid-tick.
    7. Negative tests: `dw_sales/tests/unit/test_inbox_lane.py` (another
       workspace's context refused, alpha's account is nobody in beta, a
       paused workspace, a message a person processed, a person racing the
       lane), `dw_sales/tests/integration/test_sales_inbox_lane.py` (the key
       across two transactions, the seeded account's scopes),
       `dw_platform/tests/integration/test_service_access.py`, and the whole
       lane on Postgres in `apps/worker/tests/integration/test_sales_inbox_lane_db.py`.
    8. No `ReapTarget`: the lane owns no job queue.
       Also: a message whose run fails waits a doubling delay (5 min to 6 h) so
       one bad file does not spend a run a minute. Demo: the lane is on by
       default (decision 3); `DW_WORKER_SALES_INBOX_LANE=false` keeps the
       walk-through by button deterministic (demo.md section 1, new 3.9).
       Open: a lane run is recorded with `channel="web"` (`RuntimeDw1Runs`
       hard-codes it; trace metadata only); a production tenant's DW1 account
       is not provisioned by anything yet (seed only).

- 2026-10-12, review (agent). Re-ran the guards' mutations through bash,
  each with a green baseline first and the file restored and compared after:
  the pause check, the other-workspace refusal, the quota stop, a widened
  `LANE_CEILING`, the lane's audit actor, the "not in done" filter (unit),
  the `record` `where=` (integration, both the overwrite and the two-transaction
  race) and `find_service_access` passing no ceiling (integration): all red.
  Migration `af154486381e` upgrade, downgrade -1, upgrade on a scratch
  database: the role present, absent, present; one head.
  Fixed: a routed message may be processed again, so the log's key did not
  keep the lane off a message a person routed after the tick began, and a
  pause landing mid-tick still cost one refused run. The lane now re-reads
  the pause and the message's disposition just before each run.
  `test_a_message_a_person_routes_during_the_tick_is_not_processed_again`
  and a run count on the mid-tick pause test go red without it.
  Still open: the worker image (now with dw-sales) is not built or scanned
  here, so CI's trivy run is the first look (since seen: CI's container job
  builds it and trivy finds no HIGH or CRITICAL vulnerability with a fix,
  e.g. run 38545008947 on `99cb905`); the lane's own audit row is a
  transaction after the run's (the run's rows, as the account, are in the
  run's transaction); runs record `channel="web"`; sign-in's
  `users.subject` match would resolve DW1's account if an identity provider
  ever issued that subject (nothing refuses `service|` subjects at sign-in);
  no production tenant's account is provisioned. (All four closed
  2026-10-15, next comment.)

- 2026-10-15, the open items closed (agent, Đạt: "làm luôn"; batch merge):
    - **Channel** (`e4cbb09`): the lane's runs carry `dw.channel=sales_inbox`,
      derived from the job's asker (DW1's account), with no column on the
      job. Recorded, not changed, decided by the agent: `configs/workers/sales.yaml`
      declares `supported_channels: [web]` and nothing reads it
      (failure-modes #1); enforcing it would stop the lane. Open: add
      `sales_inbox` at DW1's next worker version bump (with
      `DW1_WORKER_VERSION`, the harnesses and the manifest), or decide what
      `supported_channels` means for a lane.
    - **Sign-in** (`cf9744c`): a `service|` subject is refused at the
      verifier wrapper and in `find_access`'s SQL; `find_service_access`
      still resolves it.
    - **Provisioning** (`ecce3d7`, `97a5bde`): a context registers a
      `ServiceAccount` at the composition root; every new tenant gets it in
      its main workspace, in the create-tenant transaction. The demo seed
      writes the membership as provisioning does (department left at the
      default). Tenants created before (only the seeded demo tenants) keep
      the seed's account; no backfill path exists for an existing production
      tenant. The `platform.tenant.create` audit row is still written after
      that transaction (pre-existing). Open, for Đạt: offboarding never
      deletes `platform.users`, so a purged tenant leaves DW1's per-tenant
      user row behind (failure-modes #6); should the purge delete users
      whose subject is `service_subject(*, <purged tenant>)`?
    - **Lane audit row** (`5d65589`, `d5d8989`): written in the job's
      transaction; a job a person queued gets no lane row.
    - **Owed on Docker:** `test_service_access.py` (`find_access` by the
      account's subject and by an identity mapped to it resolves nothing),
      `test_provisioning.py::test_a_new_tenant_has_its_service_accounts_and_no_sign_in_finds_them`,
      `apps/worker/tests/integration/test_sales_inbox_lane_db.py` (channel
      and lane rows) and dw_sales `test_sales_inbox_lane.py`.

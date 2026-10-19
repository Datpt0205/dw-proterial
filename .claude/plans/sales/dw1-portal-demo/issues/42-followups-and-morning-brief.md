# 42 — Follow-ups and the morning brief, every timing the customer's

Status: done (2026-10-19, `b92a3bf` and `4235dde`; Đạt's goal of 2026-10-18 "the follow-ups the proposal promised exist, and every timing in them is the customer's to change"; built and mutation-checked by the agent; integration tests written and owed while Docker is down)
Blocked by: —
Category: enhancement

## What

FPT's DW1 proposal promises, for Sales: a PO not confirmed 4 h after it
arrived reminds the Sales PIC, past 1 day the head; a quote request waiting
on Design (BP code, spec) reminds, and a quote deadline under 2 days away
tells Sales; a case waiting on the customer past 1 day reminds the PIC (DW1
never mails the customer: it reminds the person, who decides); and a morning
brief at 07:30 (Asia/Ho_Chi_Minh). None of it existed, and none of its
numbers may be a constant: each customer's process differs.

## Acceptance

1. A tenant-overridable policy key `sales_followups`
   (`configs/policies/sales_followups@1.0.0.yaml`, `SalesFollowups`) holds
   every switch, threshold, audience (`pic`, `head`), the brief's local time
   and switch, and the working days and hours (Mon–Sat by default); the
   proposal's numbers are the platform's values. Validated narrowly: no
   defaults, `HH:MM` text, a loadable time zone, escalation after reminder.
   Every field carries a description (the rules page's schema form).
2. A worker lane `sales_followups` (300 s) reads each tenant's resolved
   policy through `TenantRuleBook`, delivers each owed stage once per (case,
   follow-up, stage, wait) through `NotificationSenderPort`, recorded in
   `sales.followup_deliveries` (RLS, grants) so a restart, a second worker, a
   reassignment or the inbox's 90 days never duplicates it. Quiet hours
   defer, never drop. Audits as the lane.
3. The brief: once per working day per workspace at the local time; the head
   the workspace, each PIC their own cases; counts and `/sales`, never an
   amount.
4. Web: Vietnamese titles, a link to the case, multi-line bodies kept.

## As built

- Domain `dw_sales/domain/followups.py`: `SalesFollowups` and its sections,
  `WaitingCase`, `owed(policy, cases, now)`, `brief_slot`,
  `WorkingHours.is_open`. The deadline is the end of the due day, local.
- `RuleKey.FOLLOWUPS` in `OVERRIDABLE`; `TenantRuleBook.followups`;
  `SalesPolicies.followups`. `STATUS_BUCKETS` (whose turn each status is)
  made public in `overview_service.py`: the brief's "waits on whom" and the
  statuses the lane loads read it, one owner.
- Application `dw_sales/application/followups.py`: `FollowupLane.tick`,
  `FollowupStorePort` (on the unit of work as `followups`), the words
  (`reminder_text`, `brief_of`, `brief_text`). Order: deliver, then record
  (+ lane audit) in one transaction; a crash in between re-delivers under the
  same `source_key`, which the inbox ignores per recipient. `pic` falls back
  to the head while a case is unassigned; nobody to tell records nothing.
  A paused DW1 reminds nobody (owed reminders go on resume if still owed).
- Migration `d2b1394c67b1` (down `445f93c2ea2a`): `ck_rule_versions_key`
  takes the ninth key; `sales.followup_deliveries` (unique key, closed-set
  CHECKs, workspace RLS ENABLE+FORCE, `dw_app` SELECT/INSERT/DELETE, no
  UPDATE); `sales.followup_scopes()` SECURITY DEFINER, ids only. Brief rows
  past 35 days are deleted in the brief's own transaction.
- Adapters: `SqlFollowupStore` (status entry time from `case_events`),
  `SqlFollowupScopes`; `build_followup_lane` in `assembly.py`; the in-memory
  store in `evals/world.py`.
- Worker: `consumers/sales_followups.py`, registered where DW1 is wired;
  `test_worker.py` names it.
- Web: `RULE_KEY.sales_followups`; the bell keeps a body's lines
  (`whitespace-pre-line`).
- Contracts and the release manifest regenerated; demo reset, API fixture
  truncate, `test_privileges.py` and `test_sales_schema.py` know the table.

## Decisions made here (Đạt may overrule; each is a policy value or one line)

- A reminder is owed per wait: a case that comes back to the customer later
  is reminded again; a PO revision restarts its clock (its `received_at`).
- Thresholds are wall-clock hours; quiet hours only defer delivery.
- `order_unconfirmed` leaves out a PO waiting on the customer
  (`waiting_customer`'s); `quote_deadline` stops once the quotation is sent.
- The brief goes before working hours (07:30 < 08:00) on working days only;
  a day with nothing for a person sends them nothing.
- Defaults the proposal does not state: waiting on Design 24 h; working
  hours 08:00–17:30; the brief's "due soon" 2 days.

## Tests

- Unit, run: `test_followups.py` (each threshold a minute before and at it,
  quiet hours, Sunday, a disabled switch, a tenant's own values, validation
  refusals, every field described), `test_followups_lane.py` (once per stage
  over many ticks, lost record re-delivers under one key, reassignment,
  escalation to the head, deferral then delivery, tenant version moves the
  timing, pause, lane audit, another tenant's tick tells nobody, delivery
  bound to the tick's tenant, the brief's content without amounts, once a
  day, its time, old records forgotten), `test_sales_followups_consumer.py`,
  `test_worker.py`, the web bell test.
- Mutations, each red: the dedupe filter removed, the brief's dedupe
  removed, the delivery context's tenant swapped, quiet hours ignored, the
  pause ignored, the policy read for another tenant, `pic` ignored; in the
  domain, a strict threshold, the deadline at the start of its day, the
  switch ignored, working hours' end inclusive, the escalation order
  unchecked; the bell's line keeping.

## Owed on Docker

- `packages/python/dw_sales/tests/integration/test_sales_followups_db.py`
  (record unique, RLS across workspace and tenant, status entry time, the
  scopes function, brief pruning, CHECKs, no UPDATE, the ninth key), and the
  catalog tests that now cover the table (`test_sales_schema.py`,
  `test_privileges.py`, `test_rls_coverage.py`). The migration has not been
  applied anywhere.

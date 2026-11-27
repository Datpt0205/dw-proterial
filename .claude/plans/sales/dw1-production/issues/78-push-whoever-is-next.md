# 78 — Push whoever's turn it is

Status: done 2026-11-27 — the platform push and the checkers (11-26), the export-control PIC and push off at sign-out (11-27), its review's five findings fixed (11-27); one consent gap left as a follow-up (below)
Blocked by: none
Category: enhancement (platform + Sales)

## Why

Only DW1's follow-up lane sends a web push (`followups.py`). A mail routed to
Sales, a cross-check due, a quotation waiting for the Manager, an NOC/ESF
waiting for the export-control PIC reach nobody's phone. `WHOSE_TURN`
(`overview_service.py`) knows two audiences, `pic` and `head`; the
cross-checker and export-control PIC are neither, so they are not told at all.

## What

- Push from the platform's notification `deliver` (batched, quiet hours from
  the tenant), so every context's notice can reach a phone; DW2 inherits it.
- `WHOSE_TURN` gains the audiences the flow has: cross-checker (holders of the
  cross-check scope, not the preparer), quote approver, export-control PIC.
- A mail routed to Sales notifies and pushes the case's PIC.
- Signing out cancels the device's push subscription.

## Acceptance

- Each audience above gets one notice and one push per item (idempotent by
  source key); the preparer is never told to cross-check their own order.

## Comments

**2026-11-26, done.**
- **Every notice can reach a phone.** Migration `19a366484422`: the channel
  outbox (ADR 0006) gains `web_push`; `platform.deliver_notification` queues
  one for each recipient a notice was inserted for who holds a push
  subscription in that workspace (the opt-in), in the same statement. Worker
  lane `web_push_delivery` (`dw_worker.consumers.web_push_delivery`, on where
  the deployment has a VAPID key) sends them through `WebPushService.push`
  under one tag, so pushes replace each other on the lock screen; never the
  notice's body. So a mail routed to Sales, an approval, DW2's notices all
  push now, with no code in the context.
- **No double ring.** `p_push` (default true); Sales' follow-ups keep their
  own batched push (ticket 48) and are wired with
  `SqlNotificationRepository(push=False)`.
- **Who checks is told.** Where a case waits on a checker (`checker_scope`:
  cross-check, quotation approval), the follow-ups tell every holder of that
  scope but the assignee, beside the heads.
- Tests: Postgres 16 (a subscriber queued once, a non-subscriber and another
  workspace's subscription not, `push=False` queues none), migration
  down/up; lane unit 4; follow-ups 135 + 285 related. Mutations red:
  `p_push` ignored, any subscriber in the workspace, the checker not added,
  the assignee not excluded.

Left: the export-control PIC (an NOC/ESF waits as a finding, not a status
`WHOSE_TURN` reads); a device's subscription cancelled at sign-out.

**2026-11-27, done (export-control PIC, push off at sign-out).**
- **The hold is a finding, so it got its own follow-up.**
  `OrderCase.awaits_export_control`: an open `missing_noc_esf` in the
  statuses where `dispose` lets the PIC decide it
  (`export_acknowledgeable_statuses()`). `Followup.EXPORT_CONTROL_HOLD`,
  told at once (`Stage.NOTIFY`) with `since` = the current revision's
  `received_at`: never the finding row's time, since every save rewrites
  the findings (`_replace_findings`). So one notice per PO revision; a
  recheck that reopens an acknowledged hold on the same revision is not
  told again (only a new revision re-raises it today).
- **Who is told.** A new internal audience `export_control` (`Told`, never
  a tenant's `Audience`): holders of both
  `capability_scope(ACKNOWLEDGE_EXPORT_CONTROL)` (read from
  `access._CAPABILITIES`, not restated) and `sales.order.prepare`, the two
  `_decide` needs. **Decided by recommendation (Đạt 11-26, unattended):**
  while nobody holds both, the heads alone (`sales.case.assign`, never the
  cross-check holders) are told, in their own words
  (`export_control_unheld`: nobody may acknowledge, grant "PIC kiểm soát
  xuất khẩu"), so a tenant that never granted the set has no silent holds.
  `pic` and `head` behave as before (unassigned `pic` still goes to the
  heads). The assignee who is also the export PIC is told once.
- **Seeing it.** In a restricted tenant the export PIC is rarely the
  assignee: `sees_case` lets a holder of the acknowledging scope read an
  order while it awaits them (list, detail, the decision), and not after.
- Config: `sales_followups@1.8.0` (`export_control_hold.enabled: true`;
  `implied_acceptance.record: true` stated and its stale "DW1 never records
  it" comment fixed), `sales_reminders@1.3.0` (the two reminders, the push
  word, and "po" → "PO" in `your_turn_order`); pins bumped; the rule sits
  at step O10; labels in `rule-labels.ts`; contract regenerated. Migration
  `fa17832cd08d`: both follow-up CHECKs admit the value (rebuilt from what
  they hold); `test_today.py` unions it.
- **Push off at sign-out.** `endPushOnSignOut`: unsubscribes in the browser
  first (existing registration only, no worker fetched), then asks the
  server to forget the endpoint, waited for at most 2 s, then clears the
  badge; never throws. `logout` runs it before the workspace and token are
  cleared (the call needs them), keeps its `() => void` type, and a second
  press during the wait does nothing. `turnOff` now also unsubscribes
  first and always asks the server.
- Measured: unit 7 lane + 4 policy + 3 domain + 3 visibility (+ push stage
  table); Postgres 16 13 (`test_export_control_hold_db.py`: held/clean
  parity with the domain, acknowledged, superseded, statuses, another
  tenant, CHECKs, migration down/up on its own database); web 6 + 2. 27
  related dw_sales unit files green, web vitest 902/903 (the one red,
  `quote-preview.test.tsx`, a 24 s timeout under load, green alone), tsc
  clean. Mutations red: export_control falling to the heads; the
  `sales.order.prepare` intersection dropped; the stand-in words ignored;
  checkers added to the stand-in; `enabled` ignored; `since` from
  `status_since`; the visibility clause removed or the hold ignored;
  `is_open` or the status dropped from `awaits_export_control`; SQL without
  `superseded_at IS NULL`, `disposition = 'open'` or the status; the marks'
  CHECK left out; the value missing from the migration; unsubscribe after
  the server call; `turnOff`'s `finally`; workspace cleared before the push
  ends; the double-press guard.
- Note for the rollout: the first tick after deploy (or after a tenant
  turns the rule on) tells of every order on hold at once, one notice
  each, then never again for that revision.

Security review (reviewing-feature-security): tenant isolation, the new
SQL reads inside the store's RLS session and joins on tenant and
workspace, and another tenant's tick reads none of the hold (tested);
authorization, the acknowledgement is still refused at the mutation
without both scopes, and a PIC without the acknowledging scope reads the
held order as not found (tested); no agent reach, no new untrusted input
(the push table covers the new kind), the record audits as the lane in its
own transaction as before. **Owed decision, Đạt:** while an order is held,
seeing it lets the export PIC take any `sales.order.prepare` step on it,
not only the acknowledgement, the same breadth the cross-checker's
visibility already has (`checker_scope`). Narrowing it to "read and
acknowledge" means telling the case loader which action asks; not done.

Left (follow-up, not built): a session that expires with no sign-out keeps
the device subscribed, and `PushRenewal` hands it to whoever signs in next
on that browser (consent on a shared device, not a leak: the server already
moves an endpoint to its newest owner). Fix when wanted: store the
principal id with the subscription on turn-on, and have `renewPush`
unsubscribe instead of renewing for another principal (key on the person,
not the workspace, or switching workspace would turn push off).

**2026-11-27, review (5 findings, all held after checking, all fixed).**
- **The hold opened every step, not only the acknowledgement (security).**
  Reproduced first: as the export PIC in a restricted tenant, `close` on
  Diệu's held `in_review` order succeeded. `stored_order`/`seen_by` take
  `export_control` (default False): the hold clause applies only where the
  caller reads (order get, list, line trail, activity, history, pipeline
  board, read-back, Bravo writes list, change requests, finding
  explanation, thread summary, source and mail text, artifact list and
  download) and in `dispose` of the `missing_noc_esf` key; every other
  step (close, prepare, resume, value and mapping edits, Bravo line
  proposals, PC, Design, quotes, mail) reads it as not found as before.
  This settles the owed decision above by narrowing, the fail-closed
  reading. The order view carries `export_hold_only`; the order page then
  narrows the viewer to read scopes (`onHeldOrder`) so no control the
  server refuses is drawn enabled, and says in one line why.
- **One answer to who the export-control PIC is.**
  `access.EXPORT_CONTROL_SCOPES` (the capability's scope and
  `sales.order.prepare`), read by `sees_case`, the lane's audience and the
  work list. A holder of the set alone no longer reads held orders (they
  could not decide them). The web's NOC control asks both
  (`mayAcknowledgeExport`), and says "Cần thêm vai Sales phụ trách (PIC)"
  to the set alone.
- **The stand-in words now fix the problem.** `sales_reminders@1.4.0`:
  grant the set to someone with the role "Sales phụ trách (PIC)" (both
  are needed); the rule's help in `rule-labels.ts` says the same.
- **The PIC granted after the heads stood in is told.** The heads' notice
  is recorded under its own stage `stand_in` (`STAND_IN_STAGE`, migration
  `d217eda10ac8` adds it to `ck_followup_deliveries_stage`, rebuilt from
  what it holds), so the revision stays owed to the export PIC; the heads
  are not told twice (the stand-in key is looked up with the rest).
- **The hold is in "Việc của tôi".** `WorkFilter.export_holds` and
  `OpenOrder.export_held` (SQL: the follow-ups' `export_held()` reused, so
  one expression); a held order is the export PIC's item
  (`acknowledge_export`, "Xác nhận NOC/ESF") whoever is assigned, until
  acknowledged. `WHOSE_TURN` stays `pic`/`head`: the hold is a finding, so
  the work list reads it from the case, not from a status.
- Measured: unit `test_case_visibility.py` 18 cases (+4 tests, +1 case),
  `test_export_control_hold_followup.py` 8 (+1), 18 related dw_sales unit
  files green; Postgres 16 `test_export_control_hold_db.py` 10 (+3: the
  stand-in recorded apart, the work list's SQL admitting the held order
  to the export PIC alone and not after acknowledgement nor to another
  tenant, the migration down/up on its own database),
  `test_sales_schema.py`, `test_sales_overview_sql.py` (SQL = in-memory
  work list, now with an export-holds-only filter); OpenAPI snapshot
  current; web `sales-ui.test.tsx` +2, full vitest 904/905 (the one red,
  `quote-preview.test.tsx`'s known timeout under load, green alone), tsc
  clean. Mutations red: the read-only flag ignored in
  `seen_by`; `dispose` not passing it; visibility on the ack scope alone;
  `export_hold_only` forced false; the artifact list loaded narrow; the
  stand-in recorded under the hold's key; the stand-in `done` check
  dropped; the stand-in keys not asked; the migration without `stand_in`;
  `export_holds` false, `any` for `all`, the hold item without the scope
  check, the SQL branch reading every order; web: the NOC control on the ack scope alone, the held-order
  viewer keeping every scope, or losing `exportControl`.

Left: the pipeline board's "Việc của bạn" (`my_action`) does not name the
hold for the export PIC (the board lists the order; its card says nothing
of the hold for them).

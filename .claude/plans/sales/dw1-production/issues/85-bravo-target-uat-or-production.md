# 85 — The gateway on Bravo UAT, switched to production from the portal

Status: built 2026-11-27 and its review fixed, offline (throwaway SQL Server); running it live waits on the UAT logins and script 10 (needs-info); two review points owed to Đạt (below)
Blocked by: none for the code; the UAT logins and script 10 (ticket 75) to run it live
Category: Bravo gateway

## What (Đạt, 2026-11-27)

"làm cho nó UAT vào database UAT … có nút switch nhanh qua production khi
dùng thật được không" — answered: a switch on the portal (Đạt chose it over a
config command and over two gateways).

Evidence for the names: UAT is `B8_Hitachi_Cable_UAT` (its log
`B8_Hitachi_Cable_UAT_Log`, trace 3), production `B8_Hitachi_Cable`
(11-19 survey). Same server or not is not known: each target names its own
host.

## Design

1. **Two targets in the gateway's settings, one credential set each.**
   `DW_BRAVO_GATEWAY_UAT_{HOST,PORT,DATABASE,READ_USER,READ_PASSWORD,WRITE_USER,WRITE_PASSWORD}`
   and `DW_BRAVO_GATEWAY_PRODUCTION_*`. The current single set stays readable
   as the UAT one for one release (no `.env` breaks). A target with no
   credentials is absent; `.env.example` fills UAT's database name only.
2. **The active target is the tenant's rule, not the gateway's env.**
   `sales_bravo_writes@1.1.0` gains `target: uat | production`, default
   `uat`. Changing it is a rule version, so it is proposed by one person and
   decided by a second (the rules page's existing maker≠checker); a version
   naming `production` must name its `uat_proof`, the same as switching a
   kind on.
3. **Stamped on every write.** A proposal (`sales.bravo_line_writes`,
   migration) records the target it read the line from; the approval token
   carries it. The gateway resolves the tenant's current target and refuses
   (`target_changed`) a write whose stamp differs: a proposal made reading
   UAT never writes production, and the reverse. Reads (`so.by_number`, the
   fingerprint) go to the current target. A target with no credentials
   refuses every read and write (`target_unconfigured`), it never falls back
   to the other.
4. **Seen on every screen that writes.** The order page's "Ghi vào Bravo"
   panel and the approval host show a tag: "Bravo UAT" (blue) or
   "Bravo thật" (red); the rules page shows the switch with what changes,
   and the gateway's own answer (configured or not) for each target.
5. **Audit.** The switch is a rule decision (already audited); each write's
   ledger row carries its target.

## Acceptance

- Unit: stamp mismatch refused at the gateway, asserted at the pipeline
  (not only the client); absent target refused; reads go to the current
  target; the rule defaults to `uat`; a `production` version without
  `uat_proof` refused. Each guard's mutation turns a test red.
- Integration (throwaway SQL Server): two databases standing in for UAT and
  production; a write lands in the stamped one only.
- Web: the tag on the panel and the approval host; the switch on the rules
  page disabled without the scope, with the reason.

## Owed

- Proterial IT: the UAT logins (read and write) and script 10 run on UAT.
- Đạt: the production logins only at go-live (ticket 83/84).

## Comments

### 2026-11-27 — built (feat/dw1-uat-gateway)

Commits a8fd81f4 (settings, routing), 5ee027c5 (`sales_bravo_writes@1.1.0`),
75b050f2 (stamp, token, migration, targets route), 2de7cb9d (web), and the
commit with this comment (env, compose, the second-person rule).

- **Settings.** `DW_BRAVO_GATEWAY_UAT_*` and `DW_BRAVO_GATEWAY_PRODUCTION_*`;
  the old `DW_BRAVO_GATEWAY_BRAVO_*` read as UAT's, and both together refuse
  to start. A target is present only with a credential (a database name
  alone is not); half a set, or one login for read and write, refuses to
  start; no target at all refuses to start. `environment` is gone: each
  configured target answers `/v1/fingerprint/<its name>`.
- **The rule.** `target: uat | production` (default `uat`) and
  `target_uat_proof`, required for production (domain validator). The
  gateway reads them from the same approved version as the switches
  (`SqlSwitches.target`, `target_of`): no version or a 1.0.0 one is UAT;
  production without a proof, or any other value, is no target and refuses
  everything (`target_unreadable`). Pin 1.1.0; release manifest regenerated.
  Not placed on the process page (`process_settings.NOT_ON_PAGE`).
- **Routing.** `dw_bravo_gateway.targets.Targets`: every read and write
  goes to the tenant's target now; a target without logins answers
  `target_unconfigured` (503 on a read, `refused/target` on a write), never
  the other. A read names its target in the `Bravo-Target` header.
- **Stamp.** The SO read's header stamps the proposal
  (`BravoSo.target` → `sales.bravo_line_writes.target`, the approval payload,
  the audit details); an answer without the header is could-not-ask. The
  approval token is format 2 with `tgt` (a format-1 token is refused, so an
  approval decided before the deploy is decided again). The pipeline refuses
  `target_changed` when the stamp, the tenant's target now and the target
  the pipeline reaches are not all one, before the kind, the ledger or
  Bravo. `bravo.write_ledger.target` from the verified token. Migration
  `f04b1390d99f`: both columns `NOT NULL`, CHECK `uat|production`, rows
  already stored backfilled `uat` (the one Bravo the gateway held), default
  dropped. An approval opened before the deploy has no `target` in its
  payload and is refused at the stamp: proposed again.
- **Web.** "Bravo UAT" (blue) / "Bravo thật" (red) on the Ghi vào Bravo
  panel (the target now, from `GET /sales/bravo/targets`, case readers) and
  on the `bravo_write` approval (the stamped one). The rules page has a
  "Bravo DW1 đọc và ghi" card: the target now, the gateway's answer for
  each, "Đổi Bravo…" opening the proposal of `sales_bravo_writes`, disabled
  with its reason without `sales.rules.propose`. Labels: `BRAVO_TARGET`,
  check `target`, rule fields and values `uat`/`production`.
- **Env.** `.env.example` names `B8_Hitachi_Cable_UAT` and
  `B8_Hitachi_Cable`, every credential empty; compose passes both sets as
  `${VAR:-}` (port `1433`) and the old set for one release.

Tests: gateway units (routing, header, absent and unreadable target, the
stamp both ways at the pipeline, settings), `test_gateway_switches.py`
(target as the schema writes it), token (format 2, unknown/missing target),
Sales (stamp into payload, row and token; an old approval not signed;
client header; targets route refused without case read), web (tags, card).
Integration: `test_gateway_ledger_db.py` (target stored, CHECK refuses
another); `test_gateway_sqlserver.py::test_a_write_lands_only_in_the_bravo_it_was_stamped_with`
on SQL Server 2017 with two databases (a copy restored as production): a
UAT-stamped write refused while production is current, a production-stamped
one lands in production only, and after switching back it writes nowhere.
Mutation, each red: the pipeline's stamp comparison (unit and on SQL
Server), the pipeline's own-target check, the router's fallback, the
unreadable-as-UAT fallback, the header, production without proof (gateway
and domain), the token's target check, the stamp signing a fixed target,
the client's header check, the targets route's scope, the settings' both-
sets and no-target refusals, the card's scope reason, the panel tag.

Seen, not mine: `test_gateway_sqlserver.py::test_an_so_is_read_by_its_number_in_the_clients_line_order`
fails on the current tree (its fixture has no `IsCancel`, read since
ticket 71); the two My Work tests in `test_cross_check_recovery.py` (81's
comment).

**Left.** The change watch (ticket 65) still baselines `production` only:
a gateway holding UAT only cannot fingerprint production, so the watch
pauses every kind once its age limit passes (fail closed), and a person
cannot accept a baseline. Until the watch guards the target in use, a UAT
run needs production configured or the watch's pauses lifted by hand; a
ticket for the watch to follow the target is owed. The SO header (`so_id`)
of a write is not checked against the target beyond the stamp: a stamp
equal to the target is what proves the line was read there.

**Second person.** The head's own rule version applied at once
(2026-10-28), so a head could switch to production, or switch a write kind
on, alone, against ticket 63 g's "proposed and approved by two people" and
this ticket's design. `rules.DECIDED_BY_A_SECOND` now holds
`sales_bravo_writes`: the head's version waits on another approver like
anyone's (`test_the_heads_switch_to_bravo_production_waits_on_a_second_person`,
red when the exception is removed); the editor and the rules list word it
"Gửi duyệt" (`appliesAtOnceFor`).

**Owed.** Proterial IT: the UAT read and write logins, script 10 on UAT.
Đạt: the production logins at go-live (83/84); confirm the second-person
exception to the head's direct path for `sales_bravo_writes` (with one head,
the admin holding `sales_rules_editor` proposes and the head decides).

### 2026-11-27 — review fixed

Ten findings, each checked against the code first; eight fixed, one fixed
fail-closed pending Đạt's word, one left to Đạt.

- **The old credential set (security).** `DW_BRAVO_GATEWAY_BRAVO_*` was read
  as UAT's, but before this ticket that set's Bravo was named by
  `DW_BRAVO_GATEWAY_ENVIRONMENT`, `production` unless set, so a gateway
  upgraded in place could label the real Bravo "uat". Confirmed with
  `GatewaySettings().targets()`. Now the old set refuses to start, naming
  the two prefixes to move it to; compose no longer passes it and
  `.env.example` says so. `f04b1390d99f`'s note now says the `uat` backfill
  is a label, not a fact (nothing reads a ledger row's target; an open
  proposal from before has no target in its approval and is proposed again).
  Test: `test_the_single_set_before_ticket_85_does_not_start` (alone, with
  the UAT set, with the production set), red with the refusal removed.
- **A self-applied version at the gateway.** `SqlSwitches` read any approved
  `sales_bravo_writes` version. A version its proposer applied alone
  (`applied_directly`) now reads as no version, the platform's file: every
  kind off, target UAT. Tests in `test_gateway_switches.py`, both red with
  the check removed.
- **The sync after a switch.** `bravo.mirror_cursors.target` (migration
  `2a03c3efa356`, CHECK `uat|production`, NULL before); a sync page's answer
  carries the `Bravo-Target` header (`SyncAnswer`; an answer naming none is
  could-not-read). When another Bravo answers than the cursor's, the lane
  marks that table's copy gone, forgets the cursor and reads the table whole
  from the Bravo that answered; a Bravo that changes between pages moves no
  cursor. Unit (`test_bravo_sync.py`, three tests, each red under its
  mutation; the client's header check red too) and integration
  (`test_mirror_db.py`: restart of one tenant only, CHECK on the target).
- **The rules editor's card.** `GET /sales/bravo/targets` now answers
  `sales.case.read` or `sales.rules.propose` (the service checks; the route
  no longer requires case read), so the tenant's IT admin who proposes the
  switch sees which Bravo is in use. The card draws loading and the
  region's error state, and "Đổi Bravo…" waits, with its reason, until the
  target is read. Tests: service (case reader, rules editor, neither), page
  (rules-only persona sees the tag; a refused read disables the switch),
  each red under its mutation. The disabled-without-scope state stays only
  in the card's own test: the page is gated on the same scope.
- **One owner for "decided by a second person".** The web copy of
  `DECIDED_BY_A_SECOND` is gone; `RulesInForceView.decided_by_a_second`
  carries the server's set, and the rules page and editor read it. The
  page's column, subtitle and help now say which keys wait on another
  approver; the editor tells the head "bạn không tự duyệt được" for such a
  key. Tests: server (`test_rules.py`, red with an empty list), page (a list
  naming KPI makes the head's KPI version "Gửi duyệt"), red with a hard-coded
  key.
- **Target refusals in words, and each proposal's Bravo.** The `target`
  check reads "Bravo đang dùng"; `target_changed`, `target_unconfigured` and
  `target_unreadable` each have their own sentence (`BRAVO_WRITE_REASON`). A
  row read from a Bravo other than the one in use carries that Bravo's tag,
  and a waiting proposal stamped with the old Bravo says it will be refused
  and how to clear it (`STALE_PROPOSAL`). Tests red under each mutation.
- `rule-drafts.test.tsx` and `rules-process.test.tsx` failed on this branch
  since 2de7cb9d (their API mock had no `bravoTargets`); mocked now.

**Not built, owed to Đạt.**
- The write-kind switches are shared by both Bravos: a kind needs `enabled`
  and a `uat_proof` to write even on UAT, and every kind switched on for the
  UAT run is live on production as soon as a version names production. My
  recommendation: a kind writes on UAT when `enabled`; on production only
  with its `uat_proof` too (a schema version 1.2.0, the gateway and the
  domain validator). It loosens what UAT accepts, so it is Đạt's call.
- One head: only `sales_head` holds `sales.rules.approve`, so in a tenant
  with one head the head's own `sales_bravo_writes` version can never be
  decided (the admin holding `sales_rules_editor` proposes and the head
  decides). The editor now says another approver decides; who that is
  stays Đạt's decision.
- Confirm the old credential set refusing to start (rather than being read
  by its old `environment`).

### 2026-11-27 — full review (functions): four more mocks without `bravoTargets`

`case-audit`, `cross-check-on-match`, `export-control-hold` and
`order-stalled` render the order page, whose "Ghi vào Bravo" panel calls
`salesApi().bravoTargets()` since 2de7cb9d; their mocks never had it, so 16
tests threw `bravoTargets is not a function` and asserted nothing after it
(16 failed / 12 passed, run alone). Each mock now answers UAT; 28/28 pass.
The review's "CI does not run the web suite" is not so: `ci.yml` runs
`pnpm --filter @dw/web test`; PR 21 was merged without waiting for it.

# 85 — The gateway on Bravo UAT, switched to production from the portal

Status: built 2026-11-27, offline (throwaway SQL Server); running it live waits on the UAT logins and script 10 (needs-info)
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


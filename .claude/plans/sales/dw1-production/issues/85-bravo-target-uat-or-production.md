# 85 — The gateway on Bravo UAT, switched to production from the portal

Status: ready-for-agent
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

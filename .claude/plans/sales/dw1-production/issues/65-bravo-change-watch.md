# 65 — Watch Bravo for change, and say so before a PIC meets it

Status: in-progress — the table, the lane, the store, the acceptance and the gateway's measurement built (2026-11-21); left: the nightly replay of recorded saves (until it exists every changed layout pauses its screen), the UAT database read for the early warning (a second read login), the client version (VIEW SERVER STATE), the Import templates (ticket 51), a page for the watch; live after IT's read login
Blocked by: 63 (the gateway computes the fingerprint; only it holds the credential)
Category: enhancement (ADR 0027, decision 4)

## Why

Đạt (11-21): Bravo's vendor and Proterial's admins will change Bravo without
telling DW, and asking them to commit to telling us is the wrong lever. DW
checks on a schedule, notices what changed, and says so. A change DW can
follow does not stop anything. A change it cannot follow stops only the
writes that depend on it, before a PIC's write meets it.

## Shape

- **What is fingerprinted.** The gateway computes it with its read login,
  plus `VIEW DEFINITION` on the listed objects only.
  - **Layouts and templates.** The layouts and Import templates DW runs:
    `B00Layout` / `B00LayoutData` per form, `B00ImportSetting` per template.
    Each is recorded with its `ModifiedAt` and `ModifiedBy`.
  - **Engine wiring.** The `B00Command` rows of those screens (module and
    `CtorArgs`).
  - **Columns** of every table DW reads or writes: name, type, length,
    nullability, default.
  - **Triggers** on the written tables: their definition hash and whether
    each is enabled.
  - **Bravo routines DW relies on.** The definition hash of every procedure
    and function the rule runner calls, plus the context parser
    (`ufn_sys_GetUserIdFromContext_Info`) and the permission functions.
  - **The client version** seen in the connected sessions' application name.
- **When.** A worker lane, `bravo_watch`, runs every 30 minutes during
  7–19h (Vietnam time) and once at night. Before each write, the gateway
  compares its cached fingerprint, which costs nothing. The lane is in the
  worker and asks the gateway for the fingerprint, so the decisions stay in
  the platform and the gateway only measures.
- **History.** Every fingerprint that differs from the last one is stored, as
  a tenant-scoped, append-only row. That history is also the answer to "how
  often does Bravo change".
- **What a change does.** Each write kind declares what it depends on, so a
  change stops only the kinds that touch it.

  | Change | Action |
  |---|---|
  | A layout changed. Every rule still parses, and the nightly replay of recorded saves gives the same or an explained result | **Writes go on.** A notice says DW follows Bravo's new rule X, with the diff of the rule. |
  | A layout holds a rule the runner cannot evaluate (new function or component) | That screen's writes **pause**. The notice names the rule. |
  | A column, a trigger, a routine DW calls, or the context parser changed | The dependent write kinds **pause**. Reads go on while their columns still exist. |
  | The client version changed | Notice. The nightly replay must pass before writes resume. |
  | UAT differs from production | **Early warning**: "Bravo UAT has X, production does not yet". An upgrade is usually tried on UAT first; nobody has to promise it. |

- **Nightly replay.** For each screen DW writes, the recorded saves (the
  trace, ticket 59) are run through the runner on today's layout, and the
  result is compared with yesterday's. Every rule of every layout DW uses is
  parsed, so an unknown function is found at night, not on a PIC's write.
- **Notice.** It goes through the platform's notifications (in-app and push)
  to the people holding `bravo.watch.read`, and to FPT support.
  - **Plain words:** what changed, when, by which Bravo user (Bravo's own
    `ModifiedBy`), which DW functions it affects, and whether they run or
    are paused.
  - **Audit:** as the lane itself (`lane_audit_event`, `system:bravo_watch`).
- **Resume.** A person accepts the new fingerprint as the baseline, after the
  replay passes on UAT. The acceptance is a permission
  (`bravo.watch.accept`), checked where the baseline is written, and it is
  recorded with who accepted it and why. Nothing resumes by itself after a
  pause (fail closed).
- **Bravo unreachable.** The status reads "could not check since HH:MM",
  never "unchanged". Writes pause after the cached fingerprint passes its
  age limit.

## Acceptance

1. Each row of the table is a test on recorded definitions:
   - a layout edit that parses goes on, with a notice;
   - a layout with an unknown function pauses only that screen;
   - a column change pauses only the kinds that use it;
   - a trigger change pauses only the kinds that write that table;
   - a UAT-only difference gives the early warning;
   - unreachable Bravo reads "could not check".
2. A pause holds until a person with the permission accepts the baseline. A
   person without it is refused where the baseline is written.
3. Mutation: an unchanged-on-error default, or a resume without acceptance,
   turns a test red.

## Done (2026-11-21)

- **The table** (`dw_bravo.watch`, `1bf3f52e`): `diff` of two fingerprints
  and `react`, row by row; a test per row (acceptance 1); 11 mutations red.
- **The lane's tick** (`dw_bravo.watch_lane.BravoWatch`): measure production,
  keep it if it differs, compare with the accepted baseline, pause, tell;
  no baseline pauses every kind; Bravo unread is "could not check since",
  past two hours every kind pauses; UAT ahead is an early warning; a tick
  never lifts a pause. 8 tests, 4 mutations red.
- **Store** (migration `6b0f375184fb`, `bravo.watch_fingerprints`
  append-only history, `watch_pauses`, `watch_baselines` append-only,
  `watch_reads`; tenant only, RLS forced; FKs to the evidence RESTRICT):
  `dw_sales.adapters.persistence.bravo_watch`, the one place that writes them.
- **The way back** (acceptance 2): `BravoWatchService.accept` checks
  `sales.bravo.watch.accept` where the baseline is written, takes only the
  latest production fingerprint, lifts every pause and writes the audit row
  in one transaction. Scopes `sales.bravo.watch.read`/`.accept` join
  `sales_head`. Routes `GET /api/v1/sales/bravo/watch`,
  `POST /api/v1/sales/bravo/watch/baseline` (scope before idempotency key,
  members only). PostgreSQL: a person without the right refused and nothing
  lifted, a stale fingerprint refused, another tenant sees and accepts
  nothing, history and baselines append-only; 3 mutations red.
- **The gateway** measures (`SqlServerBravo.fingerprint`, `GET
  /v1/fingerprint/<env>`): layouts (with a parse check), `B00Command`, the
  written tables' columns and triggers (enabled flag in the digest), the
  context parser and the rights and lock routines. A definition the read
  login cannot see is "could not check", never a constant. On a throwaway
  SQL Server 2017: a column added and a trigger disabled are the only two
  changes found, and the dependent kinds pause; 2 mutations red. It reads
  pauses before each write (a paused kind reads `paused` even switched on).
- **Worker**: lane `bravo_watch`, every 30 min 07-19h Vietnam time and once
  at 02:00, registered only with `DW_WORKER_BRAVO_GATEWAY_URL`, tenant and
  workspace; notices to holders of `sales.bravo.watch.read`, once per
  fingerprint, audited as `system:bravo_watch`. Found on the way: compose
  passes an unset value as "", which a UUID setting refused at start; read
  as unset now, in the worker and the gateway, each with a test.

Decided alone, for Đạt to review: with no nightly replay yet, every layout
change pauses its screen until a person accepts (fail closed); the history
is not partitioned (bounded by Bravo's change rate); FPT support is not
notified (no FPT principal in the tenant; holders of the read scope only).

## Comments

Script 06 section 11 measures how often Bravo changed in the past three years
(the last-modified dates of layouts, templates, routines, triggers and tables).
Those are only the last change of each object, so the counts are a lower bound.

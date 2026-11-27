# 26 — Nightly replay of recorded saves against today's Bravo layouts

Status: ready-for-agent
Blocked by: 02
Category: Bravo gateway

## What

§6: "Replay hằng đêm các lần lưu đã ghi lại" (Sales ticket 65's design,
"Nightly replay"). Checked 2026-11-27: not built. Until it exists every
changed layout pauses its screen until a person accepts (65, "decided alone,
for Đạt to review"). The recorded saves exist as the gateway's test fixtures
(the traced cancel and splits, `2c0d8fb3`; the runner from ticket 59).

L, sliced: this ticket runs the replay and reports it; letting an agreeing
replay keep writes going is a switch, off, for Đạt.

## Design

- **The recorded saves become versioned artifacts** the gateway image
  carries (one file per traced save: screen, the typed input, the statements
  the client wrote), taken from the existing fixtures, never retyped.
- **Gateway:** `POST /v1/replay/<target>` runs each recorded save of each
  screen DW writes through `dw_bravo`'s runner on that target's layouts read
  now, and answers per write kind: same, differs (which column, which rule),
  or cannot run (a rule the runner cannot evaluate, named).
- **Lane:** the existing `bravo_watch` lane calls it once a night (02:00) for
  the target in use (ticket 02), stores the outcome
  (`bravo.watch_replays`, append-only, RLS forced; migration) and tells the
  watch's readers when an outcome changes. The watch page shows the last
  replay per kind.
- **A switch, off by default:** `sales_bravo_writes` gains
  `replay_keeps_writes` (schema version bump, decided by a second person
  like the rest of that rule). Off: a changed layout pauses as today. On: a
  changed layout whose replay is "same" for a kind does not pause it.

## Acceptance

- Gateway on the throwaway SQL Server: a layout unchanged replays "same"; a
  rule edited in a copy replays "differs" naming the column; an unknown
  function "cannot run".
- Lane: outcome stored once per night; a change told once.
- With the switch off, a changed layout still pauses (test); on, only kinds
  replaying "same" go on (test). Mutation on each: red.

## Owed

- Đạt: whether an agreeing replay may keep writes going (the switch; Sales
  ticket 65's table, row 1).
- Live run: the UAT read login (Proterial IT).

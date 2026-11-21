# 49 — ADR 0026 superseded: Bravo reached through one gateway over its database

Status: done (2026-11-21: `docs/adr/0027-bravo-is-reached-through-one-gateway-over-its-database.md`, accepted by Đạt; IT reviews the grants before production)
Blocked by: none
Category: architecture decision

## Why

ADR 0026 said "no database access, ever". The 11-19/20 survey showed the 48
needs can be met from Bravo's SQL Server with no vendor API, and IT agreed.

## Decision (ADR 0027, 2026-11-21)

Every option is written out with its verdict in the ADR. Briefly:

- **One gateway** (`apps/bravo-gateway`) is the only holder of a Bravo
  credential or a SQL Server driver. It runs `dw_bravo` (ticket 59) on the
  live layouts, and contexts reach it through their ports with typed
  commands. Ticket 63.
- **Nothing of DW's inside Bravo's database.** No `dw` views, procedures,
  staging table or Agent job: those were the 11-20 design, now rejected. Two
  logins have table- and column-level grants.
- **Creation:** DW's rule runner computes the INSERT by default; the vendor's
  automatic Import (ticket 60) is used when it exists; UI automation is the
  last resort.
- **The PIC's own Bravo user on every write.** It is proven by:
  - a signed approval token;
  - a live identity check;
  - Bravo's own rights, read live;
  - the screen's rules, the lock check and the `timestamp` condition, with a
    read-back after the write.
- **Identity anchored on the employee code.** Keycloak is federated with
  Proterial's AD; links are made automatically when unambiguous, and the
  admin queue takes the rest. Ticket 64.
- **Fail closed** when a layout, template or column changes, until UAT proves
  the new version again.

## Moved

The architecture test is narrowed, not deleted. A driver is allowed only in
`apps/bravo-gateway`. Shown red with a probe import elsewhere, it is ticket
63's first slice, so the allowance arrives together with the code it allows.

## Comments

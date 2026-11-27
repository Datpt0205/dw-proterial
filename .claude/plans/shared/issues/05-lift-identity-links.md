# 05 — Identity links (person ↔ employee code) owned by the platform

Status: ready-for-agent
Blocked by: 04 (the shared gateway client answers the Bravo people port)
Category: identity / platform lift

## What

§7 Định danh: "Nâng lên nền tảng (DW2 cũng cần mã nhân viên → user Bravo)".
Checked 2026-11-27: the rules, the store and the admin act live in
`dw_sales/application/identity_links.py` and
`dw_sales/adapters/persistence/identity_links.py`, scope
`sales.identity.link`; the table is in the `bravo` schema (migration
`adad4d524377`) and the gateway reads it
(`apps/bravo-gateway/tests/integration/test_identity_links_db.py`). DW2 needs
the same answer for its own Bravo writes (ticket 33).

## Design

- **The code moves, the table stays.** `dw_platform.application.identity_links`
  (decide, link by hand, the queue) and its SQL adapter in
  `dw_platform.adapters.persistence`; the table keeps its schema and its one
  owner, `db/migrations`, since the gateway reads it.
- **Bravo's people behind a port the platform declares** (`ExternalPeoplePort`:
  people by employee code in the company system), satisfied at the
  composition root by the shared client from ticket 04, so the platform never
  names Bravo.
- **One scope:** `platform.identity.link`, granted by migration to every role
  that holds `sales.identity.link` today, the old scope removed in the same
  migration (role seeds and `test_privileges.py` updated). Sales'
  `EmployeeCodesPort` is satisfied by the platform service.
- Audit and announce unchanged (`AnnouncePort`).

## Acceptance

- The existing identity-link unit and integration tests pass where they moved.
- Negative: a person without `platform.identity.link` cannot link; tenant B's
  admin can neither link nor read tenant A's people (PostgreSQL).
- import-linter: no import of the moved modules from `dw_sales` remains.
- Mutation: "a code held by a live account is never taken over" removed → red.

## Owed

- none for the code. The AD federation stays Proterial IT's (Sales ticket 64).

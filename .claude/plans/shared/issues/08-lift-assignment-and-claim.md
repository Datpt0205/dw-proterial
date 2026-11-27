# 08 — Assignment on the platform, and "Nhận việc" for an unassigned case

Status: ready-for-agent
Blocked by: none
Category: assignment / platform lift

## What

§3: "Nâng phần giao việc lên nền tảng (port, danh sách ứng viên, audit, thông
báo)" and "PIC tự 'nhận việc' hồ sơ chưa ai nhận".

Checked 2026-11-27: assignment is Sales' own
(`dw_sales/application/assignment.py`: `candidates` at :82 from
`ScopeHoldersPort.holding` ∩ the directory, `reassign` at :101 with version
check, audit details `assigned_from`/`assigned_to`, notice at :187). Its
docstring says "an unassigned case is every PIC's to pick up", but nothing
lets a PIC pick it up: no claim route (`dw_sales/presentation/routes.py`).
DW2 has no assignee at all (ticket 29).

## Design

- **What the platform owns** (`dw_platform.application.assignment`): the
  question "who may be given work of scope S here" (`AssignmentCandidates`,
  holders of S in the workspace ∩ members, by name, the same function the
  access context is built from, so the list offered and the check made are
  one answer), the notice to the new assignee (through `deliver`, a source
  key naming the subject and its version, ids and the case's number only,
  never an amount), and the audit details shape. A support context never
  assigns (refused before anything is read), as today.
- **What stays in each context:** the case's `assigned_to` column, its
  version check, which scope works which kind of case (`_WORKS`), and the
  transaction. Sales' `AssignmentService` keeps its routes and uses the
  platform pieces; behaviour unchanged.
- **Claim:** `POST /api/v1/sales/{orders|quotes}/{id}/claim` with the case
  version: allowed to a holder of the scope that works the case
  (`sales.order.prepare` / `sales.quote.prepare`) when the case has no
  assignee; 409 when someone holds it (the race: two PICs press at once, one
  wins by version); audited as `<kind>.claimed`; nobody is notified but the
  heads' list moves. Web: "Nhận việc" on an unassigned row in "Việc cần làm"
  and on the case page, disabled with its reason otherwise.

## Acceptance

- Sales' assignment tests pass unchanged in outcome.
- Claim: a holder claims an unassigned case; a second claim at the same
  version is 409; a non-holder is refused; a support context is refused; a
  closed case is 409; another tenant's case is 404 (negative, PostgreSQL).
- Mutation: claim without the version check, claim of an assigned case, the
  scope check removed: each red.

## Owed

- none.

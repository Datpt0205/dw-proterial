# 12 — Hand a pending approval to a colleague with the same right

Status: ready-for-agent
Blocked by: none
Category: approvals / platform

## What

§2: "Chuyển một phê duyệt đang chờ sang người khác cùng quyền". Checked
2026-11-27: not built. Approvals are decided by any holder of the stamped
`required_scope` (`platform.approval_requests.required_scope`), so
"handing over" does not change who may decide: it names whose turn it is,
which today nobody can say.

## Design

- `platform.approval_requests.nominee_id` (nullable, FK users `ON DELETE SET
  NULL`, indexed; migration). `POST /api/v1/approvals/{id}/nominate` by a
  holder of the required scope or the current nominee: the nominee must hold
  the required scope in that workspace (`ScopeHoldersPort.holding`, the same
  answer the decision is checked against) and must not be the requester
  (separation of duties); audited; the nominee is told through `deliver`.
- **The decision rule does not change:** any holder may still decide (the
  nominee is whose turn it is, not a new permission). Reminders (ticket 11)
  go to the nominee first, the holders after escalation.
- **A type with a decision guard** (`decision_guards`, e.g. a
  `bravo_write.*` approval that only the person with the Bravo user may
  decide) is not handed over in this slice: the route refuses it with its
  reason, until a guard can answer "eligible?" without deciding.
- Web: "Chuyển cho…" on `/approvals` and the approval page: a `Select` of the
  candidates (holders minus the requester), with the reason in words where it
  is disabled.

## Acceptance

- API: a nominee without the scope refused; the requester refused; a guarded
  type refused; a decided approval refused (409); another tenant's approval
  404 (PostgreSQL).
- Any holder can still decide after a nomination (test, so the nominee never
  becomes a lock).
- Mutation: the scope check on the nominee, the requester exclusion: red.

## Owed

- none.

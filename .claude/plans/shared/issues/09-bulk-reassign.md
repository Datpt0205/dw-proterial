# 09 — Hand over every open case of a person who is away

Status: ready-for-agent
Blocked by: 10 (its drawer opens from the workload view)
Category: assignment

## What

§3: "Giao lại hàng loạt (người vắng, chuyển hết hồ sơ)". Checked 2026-11-27:
not built; the head reassigns one case at a time (`reassign.tsx`,
`AssignmentService.reassign`).

## Design

- `POST /api/v1/sales/assignments/hand-over` (`sales.case.assign`):
  `from_user`, `to_user` (or nobody), and the list of case ids with their
  versions the head saw (never "all of X's cases" resolved server-side at
  press time: the head approves the list they were shown).
- Each case goes through the same `reassign` (version, eligibility, closed
  case refused), one audit row per case carrying a shared `hand_over_id`; one
  notice to the new assignee naming the count, not one per case.
- The answer lists what moved and what did not, with each refusal's reason
  (stale version, closed, not eligible). Nothing is retried silently.
- Web: on the head's workload view (ticket 10), "Giao lại tất cả…" opens a
  drawer: the person's open cases (checkbox per case, all checked by default:
  reassignment is not verification, so selecting many is allowed), the new
  assignee from the candidates, the result per case after the server answers.

## Acceptance

- Unit/API: two of three cases move, one stale is reported; a non-eligible
  assignee refuses the whole request before any write; without
  `sales.case.assign` refused; a support context refused.
- Negative: a case id from another workspace or tenant is reported not
  found, and nothing reveals it exists.
- Mutation: the per-case version check removed → red.

## Owed

- none.

# 38 — A tenant's rule version is decided on a platform approval

Status: done (2026-10-14; Đạt chose "move it" on 2026-10-14; built, mutation-checked and security-reviewed by the agent; integration tests rewritten and owed while Docker is down)
Blocked by: —
Category: enhancement

## What

Ticket 19 decided a tenant's rule version on a Sales route,
`POST /sales/rules/versions/{id}/decision`, with `sales.rules.approve`, the
proposer refused at the service and by `ck_rule_versions_checker_not_maker`.
That kept the maker/checker rule but left it the one checker's decision in DW1
that is not a platform approval: it is missing from the shared `/approvals`
inbox, is not refused by the platform's strict `sales.` rule or a decision
guard, and is the exception to dw_sales ADR 0004 ("no Sales route decides").
Ticket 30 moved the PO layout to a run-less `sales.layout` approval; this
moves the eight rule keys onto the same path.

## Acceptance

1. Proposing a version opens a run-less `sales.rules` approval in the same
   transaction, stamped `sales.rules.approve`, naming the proposer as its
   maker, its payload ids, the key and the version only (never the document:
   it can hold price rules). The version row names its approval.
2. The decision is the platform's (`POST /approvals/{id}/decisions`):
   `sales.` is strict (a second person, a comment); the `sales.rules` guard
   refuses a version no longer proposed, an approval not opened by a proposal,
   a stamp other than `sales.rules.approve`, and approving a number the
   platform has released since.
3. The worker carries out `sales.rules.decided` once, reading the outcome from
   the approval row as the decider (the CHECK refuses the maker again):
   approved supersedes the version in force; rejected is recorded. A
   redelivery writes nothing.
4. The Sales decision route is gone; `/approvals` decides `sales.rules` in
   place (no rules page yet), and links every other `sales.` type as before.
5. The demo seed decides through the same approval.
6. Tests: unit (propose opens the approval; guard refusals; settlement both
   ways and idempotent; the route is gone), worker consumer, web host;
   integration (migration, API) written and owed while Docker is down.

## As built

- `application/rules.py`: `RULES_APPROVAL`, `RULES_DECIDED`,
  `RuleApprovalAsked` (payload: ids, key, version, makers), `propose` opens
  the approval in its transaction, `RuleDecisions` (the guard),
  `RuleSettlement` (idempotent; reads the approval as the decider holding
  the stamp); `SalesRulesService.decide` and `RuleDecision` are gone.
  `RuleVersion.approval_id`; `RuleVersionView.approval_id`.
- Migration `218118b8f0e5`: `approval_id`,
  `fk_rule_versions_approval_requests` (composite, CASCADE, as
  `po_layouts`), `uq_rule_versions_approval_id`,
  `ck_rule_versions_proposed_has_approval` (NOT VALID: a proposal from
  before has no approval and is proposed again; no deployment holds one).
- Wiring: `register(..., rules=)` puts the guard on `sales.rules`;
  `build_rule_settlement`; the worker's run-less handler is one
  (`consumers/sales_decisions.py`, renamed from `sales_layouts.py`) wired
  under both decided events.
- Web: an `ApprovalHost` may return null from `inbox.href` for a type it
  leaves on `/approvals`; Sales does for `sales.rules`.
- Seed: proposes, decides through `ApproveAndResumeService` with the guard
  (a runner that refuses every call: nothing run-less resumes a run), and
  settles as the worker would.
- `test_no_sales_route_decides_what_a_checker_decides` looked for
  `/approval`, `/approve` and `/cross-check` only, so the rules route ending
  in `/decision` passed it (failure-modes #0); it now looks for `/decision`
  and `/decisions` too, and went red with such a route added back.
- Mutations, each red: the guard ignoring a number released since, a
  version no longer waiting, the stamp, the maker (asked directly, behind
  the platform's strict rule); the settlement not idempotent, settling a
  pending approval; the guard not registered; the worker not wired.

## Owed (Docker down)

- `apps/api/tests/integration/test_sales_api_rules.py` (rewritten: the
  approval path, 404 for a decider without the stamp and for another
  tenant, the three new constraints), the migration round trip, and a
  `make demo-reset` (the reset deletes `sales.` approvals, which now
  cascades to the demo tenant's rule versions; the seed proposes 1.5.1
  again).

## Left open

- A decider's reason is on the approval's decision, not on the version: the
  rules list shows `comment` only for versions decided before this ticket.
- No rules page in the web app yet: the head sees the key and the version on
  `/approvals`, the document through `GET /sales/rules` only.

---
status: Proposed
date: 2026-10-03
---

# Sales decisions are case transitions until the runtime carries them

## Context

CLAUDE.md requires that "approval pauses and resumes a durable, checkpointed
run". The DW1 demo (spec decision 5) records each Sales decision differently.
Prepare, cross-check, confirm, price, approve and decline are each a
transition on a case in the `sales` schema, with an audit event, and no run
or interrupt is involved. The reason is that the demo runs on mock data and
nothing it does writes outside the platform: a person uploads every file and
sends every email.

The runtime gives more than approval, and this shortcut bypasses all of it.
This ADR lists each bypassed guarantee with what stands in for it, so that
none is lost silently.

## Decision

Until ticket 10, dw_sales records decisions as case transitions, with these
substitutes:

| Runtime guarantee bypassed                                    | Interim substitute in dw_sales                                                                                                                                                                        |
| ------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Approval interrupt and requester ≠ approver (`approval_flow`) | Per-case maker/checker in the handler (cross-checker ≠ preparer, Bravo recorder or author of a hand-entered value; approver ≠ pricer), backed by CHECK constraints on `order_cases` and `quote_cases` |
| Durable checkpoint and resume                                 | The case row and its `case_version` in PostgreSQL. Every decision names the version it was made on                                                                                                    |
| Run provenance (version columns on `worker_runs`)             | Stamps on the case: rules `id@version`, parser version, attachment sha256, master-data `as_of`, release manifest ref                                                                                  |
| Plan quota (`RunAllowancePort`)                               | None. Processing starts only from a button, on mocks bound to the demo tenant and not wired when `settings.is_deployed`                                                                               |
| Autonomy table and stop control                               | A per-workspace pause flag: `sales.worker.pause` (every PIC) and `sales.worker.resume` (the head), audited and notified                                                                               |
| Approvals inbox                                               | `GET /api/v1/sales/my-work`, filtered by the caller's scopes                                                                                                                                          |
| Effect gate: no side effect without approval                  | Download gates: each artifact is served only in its state and for the decided `case_version` (ticket 06)                                                                                              |
| Worker identity                                               | `actor_kind = 'worker'` and `initiated_by` on DW1's events. A production service principal holding `sales.inbox.process` only is ticket 10's                                                          |

## Exit

Ticket 10 moves the decisions onto a versioned graph with `interrupt`, and
deletes the context-side decide endpoints in the same change. Its acceptance
is fixed in the ticket. In short:

- each approval type declares its decide-scope;
- the maker is excluded by the strict check;
- payloads carry no amount;
- `RunAllowancePort` is checked;
- the graph is pinned;
- a document-reading model turn has no outbound tool;
- the old endpoints are gone.

Ticket 10 must land before DW1 reads a real document, and before any adapter
writes outside the platform.

## Consequences

- Each substitute above is code that ticket 10 deletes or keeps. The CHECK
  constraints stay either way, because they hold for any writer.
- Until then the generic approvals inbox shows no Sales decision. That is
  intended: through `approvals.decide` it would let a purchasing manager
  decide a Sales quote.

---
status: Proposed
date: 2026-10-06
supersedes: 0001-case-decision-before-runtime.md
---

# A checker's decision is an approval DW1's run pauses on

## Context

ADR 0001 let DW1's demo record every Sales decision as a case transition and
listed the runtime guarantees that bypassed. Its exit was ticket 10, with the
acceptance fixed there (decide scope per approval type, every maker excluded,
amount-free payloads, the run quota, a pinned graph, no outbound tool on a
document-reading turn, the old endpoints gone).

Two kinds of decision are on a Sales case, and they are not the same thing.
A **maker's step** (prepare, record the Bravo entry, price, submit, confirm,
decline) is a person doing their own work, audited as theirs. A **checker's
decision** (approve or return a quotation, WIV-03-023 step 9; cross-check or
return an order, WIV-03-012 step 9) is a second person deciding on someone
else's work. Only the second is what CLAUDE.md means by "approval pauses and
resumes a durable, checkpointed run".

## Decision

DW1 is a worker on the runtime (`configs/workers/sales.yaml`, graph
`dw_sales.workflows.graph` 1.0.0, both pinned in the release manifest).

- **Every DW1 action a person starts is a run**: "DW xử lý" (one message or
  all), submitting a quotation, recording a Bravo entry. The runner checks
  the plan's daily run allowance where every run begins, so a later door (a
  mailbox consumer) meets the same check. The steps a run takes
  (`CaseDecisions`) are given only to the graph, never to a route.
- **A checker's decision is a platform approval.** Submitting pauses the run
  on `sales.quote`; recording the Bravo entry (or applying a revision there)
  pauses it on `sales.order.cross_check`, unless the case's rules need no
  cross-check. The decision is `POST /api/v1/approvals/{id}/decisions`; the
  run resumes and applies it to the case as the decider, linked to the run.
  `POST /quotes/{id}/approval` and `POST /orders/{id}/cross-check` are gone.
- **The approval names who may decide it.** The interrupt stamps
  `decide_scope` (`sales.quote.approve`, `sales.order.cross_check`, from the
  one map `DECIDE_SCOPES`) on the request, and the platform requires that
  scope instead of `approvals.decide`. The inbox and a single request are
  served only to holders of it and to the requester.
- **The approval names every maker.** `makers`: the pricer and the
  submitter of a quotation; the preparer, the Bravo recorders of this round
  and earlier ones, and whoever typed a value still on an order. `sales.` is
  a strict prefix, so the platform refuses each of them (409, tách nhiệm) and
  wants a written comment.
- **Sales checks a decision before it is recorded** (`CaseDecisions.check`,
  the platform's `ApprovalDecisionGuard` for `sales.`): the case still waits
  on this approval, at the version the decider saw (`subject_version`), the
  checker opened the source, every blocking price finding has its reason,
  and the approval carries the scope DW1 stamps. The run applies the same
  transition with the same code.
- **A case that moves on withdraws what it waited on**: priced again or
  declined while pending, revised while awaiting its cross-check.
- **Ids, a version and a hash only**: the approval payload, the run's input
  and result, and the audit rows carry no amount and no free text a person
  typed (the comment stays on the platform's decision record).
- **No model turn, no tool**: the worker declares no toolset, so ADR 0007's
  rule (a document-reading turn gets no outbound tool) holds by construction;
  `test_dw1_runtime.py` turns red when a toolset or a model reaches DW1.

## What stays from ADR 0001

| ADR 0001 substitute                                      | Now                                                                                                                                 |
| -------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Per-case maker/checker in the handler, CHECK constraints | The platform's strict rule over the named makers, then the case, then the CHECKs: all three stay                                    |
| Case row and `case_version` as the checkpoint            | The run's checkpoint holds the pause; the case version still names what each decision was made on                                   |
| Stamps on the case for provenance                        | Kept; the run row adds worker, graph and artifact versions, and the decision's audit row names the run                              |
| No plan quota                                            | `RunAllowancePort`, in the runner                                                                                                   |
| Pause flag for the stop control                          | Kept: it stops processing inside the run. The autonomy level is stamped on each run (A1); the checker's pause does not depend on it |
| `GET /sales/my-work` as the inbox                        | Kept for the Sales pages; the platform's inbox lists the same approvals to whoever may decide them                                  |
| Download gates as the effect gate                        | Kept: nothing DW1 does writes outside the platform yet                                                                              |
| `actor_kind = worker` events                             | Kept; the run is the person's who started it. A service principal holding `sales.inbox.process` only is still owed (ticket 12)      |

## Consequences

- The platform gained what a context needs to own its approvals: a stamped
  decide scope, named makers, a decision guard, reasons and a subject version
  on a decision, and withdrawal by subject. None of it names Sales.
- The platform's generic Approvals page lists Sales approvals to their
  deciders, but sends no `subject_version`, so a decision there is refused;
  the Sales pages are where they are decided. Changing that page means
  moving it to antd first (CLAUDE.md "Web UI").
- A decision that passes the guard can still fail when the run applies it, if
  the case changed in the instant between (the window is one request long);
  the run then ends failed and the approval stays decided. A quotation
  recovers by being priced and submitted again; an order at
  `uploaded_to_bravo` has no step that raises its cross-check again yet
  (open, ticket 12).
- Ticket 10 had to land before DW1 reads a real document or an adapter
  writes outside the platform; both remain ticket 12's.

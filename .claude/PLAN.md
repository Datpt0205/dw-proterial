# Plan

The first 40 lines are injected into context at session start by
`.claude/hooks/session-start.sh`. Keep what matters inside them, and keep them
true — a stale plan is worse than none, because it is believed.

Here rather than `docs/`: this repository deliberately ships no documentation
directory, and this is tooling state, not a product document.

## Now — Mốc 3: nhớ được giữa các lượt (đường ĐỌC xong, đường GHI còn lại)

**Done in this slice.** `MemoryService.recall` + `RecalledMemoryMiddleware`, in
`platform_middleware` behind `AgentSpec.recall`. A run carrying a `subject_ref`
now gets what this worker already learned about that record, framed as data by
`runtime@1.5.0`. Four conditions narrow it and each has a negative test that a
mutation proved: tenant, workspace, worker, clearance.

Two honest limits to keep in view:

- `build_agent` still has **no production caller** — this is a skeleton, and a
  bounded context is what builds an agent. "Wired" here means wired into
  `platform_middleware`, the same sense in which the other middlewares are.
- Recall matches on `subject_refs` overlap, not relevance. Good enough while a
  run is about one record; it is not retrieval, and a run about no record
  recalls nothing by design.

**Also done: supersession (migration `62a9aaba6b16`).** Memory was append-only —
nothing ever wrote `valid_until`, so two facts that disagreed both stayed live
and recall returned both by confidence. A `fact_key` names WHAT a memory asserts,
so two live memories sharing a key and a subject are two answers to one question
and the later one closes the earlier. Closed, never deleted: the row, its
provenance and its audit entry stay, and the audit says which memories were
closed and under what key. A memory with no key still accumulates, which is
correct for episodes.

This is the one SOTA idea taken so far that changes correctness rather than
quality. Not taken, deliberately: vector/graph recall (needs embedding
infrastructure; subject-keyed matching is explainable and enough while a run is
about one record), and LLM-decided merging (the model proposes, code decides).

**Also done: the async write path.** `propose` has a production caller — the
worker's outbox handler for `memory.candidate_proposed`, wired in
`dw_worker.main`. Remembering runs after the answer, not during it. The outbox
delivers at least once, so `propose` took an `idempotency_key`: the event's own
id becomes the candidate row's primary key, and a redelivery returns the first
decision instead of writing a second memory. Tenancy comes off the event
envelope, never the payload — what produces the payload is a model's output one
layer up. The context supplies a plan the catalog does not contain, so anything
that starts reading the plan on this path refuses rather than grants.

What a bounded context still owns: EMITTING the event. The platform ships the
schema, the handler, the idempotency and the audit; deciding what is worth
remembering is a workflow's judgement, not the platform's.

**Still open, and the heavy half:**

- ~~Route the builtin file tools through `ToolExecutor`~~ — **checked, and not a
  task.** It was inherited from the blueprint, which assumed memory would be a
  `MEMORY.md` the model edits with `edit_file`. `build_agent` is built on
  `create_agent`, which installs no tools at all; `create_deep_agent` is what
  ships the eight file/shell tools and it is deliberately not used. The only
  always-allowed name is `write_todos`, which writes to graph state and reaches
  nothing outside the run. `OfferedToolsOnlyMiddleware` remains as the guard for
  a context that reaches for the deep variant anyway.
- So the `AGENTS.md` route is not needed either: structured items in Postgres
  carry provenance, supersession, audit and RLS, and a file in tmpfs carries
  none of those. Reopen this only if a context has a real need for a
  model-editable file, and then it is new capability, not a hole to close.
- Left for the write side: vector-ranked recall (Qdrant and `EmbeddingPort` are
  already wired for knowledge), and a context that actually emits
  `memory.candidate_proposed`.

## Next after that

- ~~**Mốc 5 sub-agents**~~ — **done**, `adapters/sub_agents.py`. Two things were
  measured on the pinned deepagents rather than assumed. Inheriting tenancy is
  already safe: the context is graph level, so a child sees the caller's tenant,
  workspace, scopes and autonomy, and a `SubAgent` spec has no field that could
  replace them. What is NOT safe by default is spend — with a probe middleware on
  both, the order is parent, child, parent, so the parent's ceiling never sees a
  token the child burns. `sub_agent_spec` rebuilds the gates inside the child and
  hands it the SAME ledger object. Its tools are built from DEFINITIONS through
  `platform_tools`, never passed in ready-made, and a child may not offer a tool
  its caller lacks. The `task` tool exists only when a context names something to
  delegate to.
- **Mốc 6 running many customers** — model fallback/retry on the agent path (it
  has none), a per-tenant spend cap that reads the ledger (today's quota counts
  runs, not money), `cancel_thread` wired to an endpoint, provider fixtures.

## Decisions still open (asked, not yet answered)

None. The three that stood here were answered and closed — see the last row of
Done. What they turned into:

- `never` was not collapsed into `conditional`; it was given the only meaning a
  tool's author may safely carry — a claim, checked where a tool is declared,
  that the tool does nothing needing a person. A `never` on anything reaching
  outside is now refused instead of silently read as `conditional`.
- The `record_visibility` cache no longer invents a value. An entry written by an
  older release is a miss and is re-read. That also retired the fail-closed guess
  for `max_autonomy_level`, which was safe but still wrong for seconds per deploy.
- `approval_policy_version` is in the release manifest, read from the constant a
  run is actually stamped with rather than copied.

## Done

| Mốc | Commit    | What it changed                                                            |
| --- | --------- | -------------------------------------------------------------------------- |
| 0   | `4d45cf5` | `build_agent()` — one place a platform agent is assembled                  |
| 1a  | `1cda019` | Spend ceiling on the agent loop; ledger no longer leaks                    |
| 1b  | `b3b556f` | Context compaction that is recorded, bounded and fails open                |
| 2   | `eb25931` | Autonomy A0–A4 decides approval; tenant ceiling; policy stamped on the run |
| 4   | `80d849f` | Provenance as a chain the database enforces                                |
| —   | `643236f` | Invariant checker + commit gate + the security-review skill                |
| —   | (below)   | The three open decisions, answered: `never`, the cache, the manifest       |

Mốc 3 is deliberately out of order: Mốc 4 was cheaper and is what an audited
buyer asks for first.

## How a feature is checked here

Three layers, in decreasing order of how much they can be skipped:

1. `scripts/verify_invariants.py` — mechanical, runs in CI and in the commit
   hook. Exemptions live in `RLS_EXEMPT` / `UNREAD_EXEMPT` and each needs a
   written reason.
2. `.claude/hooks/pre-commit-gate.sh` — blocks `git commit`, runs layer 1, then
   asks only the questions this diff's file paths earn. Once per diff, not once
   per attempt. Disable with `touch .claude/no-commit-gate`.
3. `.claude/skills/reviewing-feature-security/` — six trust boundaries, a
   negative test at each, and a mutation check. Run before calling a feature
   done, without being asked.

`.claude/rules/failure-modes.md` holds the counts these are derived from. The
honest limit: layer 2 guarantees the questions are raised, not that they were
answered truthfully, and no layer replaces running the thing.

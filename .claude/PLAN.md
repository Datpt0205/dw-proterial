# Plan

The first 40 lines are injected into context at session start by
`.claude/hooks/session-start.sh`. Keep what matters inside them, and keep them
true — a stale plan is worse than none, because it is believed.

Here rather than `docs/`: this repository deliberately ships no documentation
directory, and this is tooling state, not a product document.

## Now — the platform is waiting for a bounded context

Every platform milestone that can be finished without one is finished. What is
left is not a gap in the platform: `build_agent` and `MemoryService.propose` have
no production caller because a bounded context is what calls them, and this repo
deliberately ships none. Adding one here to make the wiring look complete would
break the boundary the whole repo is built on.

So the next real step is a decision, not a task: **pick one business context**
(sales chat, research, lead scoring) and plug it in at the seams — a package
under `packages/python/`, its graphs registered on the runtime seam, its worker
YAML, its tool specs, its eval dataset. `CLAUDE.md` lists the seven plug-in
points.

Only then do the numbers this plan leaves blank become measurable: how many live
memories one account really accumulates, whether the GIN index gets chosen with
real data, what a day of runs actually costs.

**Done and pinned by tests:** Mốc 0, 1a, 1b, 2, 3, 4, 5, 6. Details below.

**Open decisions:** none. A second language (Go) for the application tier was
asked about and answered in `CLAUDE.md` — allowed, provided it never
re-implements tenant isolation, and the four conditions there are tested by
`test_rls_coverage.py` rather than trusted.

**Next, in the order they would be asked for in an enterprise review:**

1. ~~Data lifecycle~~ — **done for memory and knowledge.**
   `configs/policies/retention@1.1.0.yaml` is the versioned answer to "how long
   do you keep our data", it is in the release manifest with a checksum so the
   question can be asked about the past, and ONE file feeds both sweeps on the
   worker's hourly lanes. Deletes, never closes a window: `valid_until` says a
   fact stopped being true, retention says we may no longer hold it.
   `legal_hold` has no term and is never swept; a class this build does not know
   is kept, not guessed.

   What closing knowledge actually took, beyond the obvious sweep:
   - **Evidence had no lifecycle at all.** `evidence -> documents` is RESTRICT,
     and deleting a memory only cascades `memory.item_evidence` — the evidence
     row survived for ever, pinning its document for ever. So a document cited
     once could never be hard deleted and the grace period was a promise the
     schema could not keep. `SqlMemoryRetention` now removes evidence nothing
     cites, which is what makes the chain drain. It lives in memory, not
     knowledge, because `item_evidence` is a memory table.
   - **A cited document is held back, not crashed on.** The citation test is in
     the SELECT, and again inside the deleting transaction — the vector deletes
     sit between the two, so a memory proposed in that gap would otherwise fail
     the whole batch and stall every document behind it.
   - **Both stores, points first.** Rows without points is a pass the next hour
     finishes; points without rows is the text of a deleted document in the only
     store that can still return it.
   - `KnowledgeGateway.purge_soft_deleted` was deleted. It was this feature,
     written earlier, never called from anywhere, crash-prone on any cited
     document — the duplicate is what would have drifted.

   **And done for audit and usage too.** The baseline said in a comment that "an
   operational job creates real monthly partitions ahead of time"; it never
   existed, every row was in the `_default` partition, and a default partition
   cannot be dropped — so "audit retention is DROP PARTITION" could not execute
   at all. The job exists now as a worker lane, and building it turned up two
   holes of the family migration 0009 found:

   - **The audit log was not append-only.** `0001_platform_grants.sql` revoked
     UPDATE and DELETE on `platform.audit_events` and says in prose that this is
     "enforced by the grant rather than by convention". It never revoked them on
     `audit_events_default`, which had taken them from the blanket grant one
     statement earlier. As `dw_app`, both `DELETE FROM audit_events_default` and
     `UPDATE ... SET action = 'rewritten'` succeeded. `ALTER DEFAULT PRIVILEGES`
     means every future partition would have arrived the same way, so the revoke
     is now part of creating one.
   - **A partition created later inherits no RLS**, which is 0009 again — a
     monthly job would have re-opened that leak every month. Creating, policing
     and revoking are one function, and `test_partition_maintenance.py` asks the
     catalog rather than reading the DDL.

   Two more things the work itself taught:
   - Creation is **self-healing**. A row for a month with no partition lands in
     the default, and Postgres then refuses to create that month's partition.
     Without relocation that state is terminal — one missed window and the month
     can never be partitioned, so never dropped. Found by running the whole
     integration suite, not this one file.
   - **Nothing is dropped by default.** Both tables ship `days: null`. The pass
     creates partitions ahead, which is pure gain, and drops only what somebody
     wrote a number for — DROP PARTITION destroys a month instantly with no soft
     delete in between, and the term is a legal obligation per deployment, not a
     technical default. **Đạt still has to choose those two numbers.**

   Still open, and named rather than silently included: **superseded documents**
   — how many versions back to keep is a different question from how long a
   deletion takes to become final.

2. Backup and restore: no procedure, never rehearsed.
3. Tenant offboarding and data export.
4. SLO, alerting, on-call.

## Mốc 3 — nhớ được giữa các lượt (chi tiết)

**Done in this slice.** `MemoryService.recall` + `RecalledMemoryMiddleware`, in
`platform_middleware` behind `AgentSpec.recall`. A run carrying a `subject_ref`
now gets what this worker already learned about that record, framed as data by
`runtime@1.5.0`. Four conditions narrow it and each has a negative test that a
mutation proved: tenant, workspace, worker, clearance.

Two honest limits to keep in view:

- `build_agent` still has **no production caller** — this is a skeleton, and a
  bounded context is what builds an agent. "Wired" here means wired into
  `platform_middleware`, the same sense in which the other middlewares are.
- The ranker has a real implementation now: `dw_memory/adapters/qdrant_ranker.py`,
  its own Qdrant collection, tested against a running Qdrant (tenant and worker
  filters discriminate; a width mismatch refuses rather than dropping everyone's
  vectors). Indexing runs on the worker after the memory is committed and never
  raises; both composition roots build it only when `QDRANT_URL` is set, measured.
- Measured, and NOT tuned on: the GIN index on `subject_refs` does serve `?|`
  (Bitmap Index Scan), but in the full recall query the planner prefers
  `ix_items_page` and applies `?|` as a filter. That is a reasonable choice on an
  empty table and says nothing about production. Left alone deliberately — index
  tuning against no data is guessing.
- Recall matches on `subject_refs` overlap. Similarity now decides the ORDER of
  that set when a ranker is wired (`dw_memory/ranking.py`) — it never decides the
  SET. An index that is empty, stale or poisoned can only produce a worse order,
  never a wrong answer, and a memory written before the index existed still
  surfaces. A ranker that is down degrades to confidence order, which is what
  every run did before. Still true: a run about no record recalls nothing.

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
- **Mốc 6 running many customers** — half done.
    - Retry on the agent path: **done** (`adapters/model_retry.py`). Provider
      FALLBACK is deliberately not built: the chat factory points at a LiteLLM
      proxy where failover is configuration the application never sees.
    - Per-tenant daily spend cap: **done**. `RunAllowancePort.spend_usd_per_day`
      plus `run_store.spend_since`, checked in the runner beside the run count and
      before it. Summed from `model_usage_ledger` — `worker_runs` has no cost
      column, which the first version got wrong and only a real database said so.
    - `cancel_thread` over HTTP: **done**. The runner's method takes a thread id
      and nothing else — it reads an in-process dict, safe while the only caller
      is a run that started it, a cross-tenant cancel the moment it is a route.
      Ownership is established in the endpoint via `run_store.thread_belongs_to`,
      under the caller's own tenant and therefore under RLS; a thread that is not
      yours is a 404, the same answer as one that never existed.
    - Provider fixtures: **done**. The mechanism existed and was wired at
      `bootstrap/models.py`, the directory was empty, and nothing had ever read a
      fixture back — configured and unexercised. Now tested: found by prompt id
      AND version, a missing recording is refused loudly rather than invented, a
      non-object file is refused, and a registered builder still wins.

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

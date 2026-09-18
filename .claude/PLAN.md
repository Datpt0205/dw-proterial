# Plan

The first 40 lines are injected into context at session start by
`.claude/hooks/session-start.sh`. Keep what matters inside them, and keep them
true — a stale plan is worse than none, because it is believed.

Here rather than `docs/`: this repository deliberately ships no documentation
directory, and this is tooling state, not a product document.

## Now — Mốc 3: nhớ được giữa các lượt

`MemoryService.propose` still has **no production caller**. Mốc 4 made the
provenance chain enforceable; nothing walks it yet. Mốc 3 is what wires memory
into the agent loop, and it is the largest remaining piece:

- Nothing injects memory into a run. `MemoryService` has `propose` and
  `list_items` — no `recall`, no retrieval by relevance, no call site.
- `deepagents.MemoryMiddleware` reads `AGENTS.md` from a backend and teaches the
  model to `edit_file` to update it. `DocgenSandbox` already implements that
  backend — but `/work` is tmpfs, so a `MEMORY.md` there is amnesia on restart.
- The builtin file tools bypass `ToolExecutor` (authorization, idempotency,
  audit), which is why `OfferedToolsOnlyMiddleware` strips them. Routing them
  through the executor is the heavy part of this milestone.
- `AGENTS.md` is customer data: per tenant, versioned, and not writable by a
  prompt-injected instruction inside a document the agent read.

## Next after that

- **Mốc 5 sub-agents** — `SubAgentMiddleware` exists; the platform part is that a
  sub-agent inherits the caller's tenant and scopes and never more, its tools
  still pass `ToolExecutor`, and its cost counts against the parent's ceiling.
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

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

- `approval_policy: never` and `conditional` now behave identically. Collapsing
  them is a breaking change to every tool spec.
- `record_visibility` has two known faults left alone as out of scope: its cache
  default fails open for up to 30s after a deploy, and changing it is not audited.
- `AUTONOMY_POLICY_VERSION` is a code constant and is not in the release manifest.

## Done

| Mốc | Commit    | What it changed                                                            |
| --- | --------- | -------------------------------------------------------------------------- |
| 0   | `4d45cf5` | `build_agent()` — one place a platform agent is assembled                  |
| 1a  | `1cda019` | Spend ceiling on the agent loop; ledger no longer leaks                    |
| 1b  | `b3b556f` | Context compaction that is recorded, bounded and fails open                |
| 2   | `eb25931` | Autonomy A0–A4 decides approval; tenant ceiling; policy stamped on the run |
| 4   | `80d849f` | Provenance as a chain the database enforces                                |

Mốc 3 is deliberately out of order: Mốc 4 was cheaper and is what an audited
buyer asks for first.

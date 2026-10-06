# Agent runtime and memory milestones (Mốc 0–6)

The platform's own agent runtime, built before any bounded context existed.
The full narrative is at `git show 84e3f6a:.claude/PLAN.md`, sections "Mốc 3",
"Next after that", "Decisions still open" and "Done".

| Mốc | Commit    | What it changed                                                            |
| --- | --------- | -------------------------------------------------------------------------- |
| 0   | `4d45cf5` | `build_agent()`: one place a platform agent is assembled                   |
| 1a  | `1cda019` | Spend ceiling on the agent loop; the ledger no longer leaks                |
| 1b  | `b3b556f` | Context compaction that is recorded, bounded and fails open                |
| 2   | `eb25931` | Autonomy A0–A4 decides approval; tenant ceiling; policy stamped on the run |
| 3   | `d0883fe` | Recall: a run remembers what it learned about the record it is on          |
| 4   | `80d849f` | Provenance as a chain the database enforces                                |
| 5   | `ed441d8` | Sub-agents narrower than their parent, sharing one spend ceiling           |
| —   | `643236f` | Invariant checker + commit gate + the security-review skill                |

Mốc 6 (running many customers) is half done:

- **Done:**
    - retry on the agent path;
    - `cancel_thread` over HTTP, ownership checked under RLS;
    - provider fixtures, now tested.
- **Provider fallback:** deliberately not built, because it is LiteLLM proxy
  configuration.
- **Daily spend:** the per-tenant cap that read `platform.model_usage_ledger`
  was removed along with that table. Its successor is Ops hardening phase 3's
  spend guard, whose quotas are still unset.

## Memory, as it stands

- **Recall** matches on `subject_refs` overlap. Similarity only orders that
  set, never decides it, so a stale or poisoned index can give a worse order
  but never a wrong answer.
- **Supersession:** two live memories with one `fact_key` and one subject are
  two answers to one question, and the later one closes the earlier. Rows are
  closed, never deleted.
- **Writes are asynchronous:** the outbox handler for
  `memory.candidate_proposed` calls `propose` with the event id as the
  idempotency key, and tenancy comes from the envelope, not the payload.

## Open

- **CI is green** on run 37427518778 (2026-10-06, commit 46b7e2c), all seven
  jobs, for the first time since 2026-10-02. What it took (detail in the
  commits): gitleaks quoting its own ignored phrase (7daa617); pip-audit,
  scaffold-smoke and the run-state announcement timeouts (2284d3c: tests
  marked `anyio` ran under two async runners, so on Linux the LISTEN
  fixture sat on a loop nobody ran; `-p no:anyio` now); pnpm audit and
  trivy (46b7e2c). Still owed:
    - `braces` <=3.0.3 is audit-ignored for GHSA-vfj7-8cjw-p6xm only (no
      fixed release; dev-only lint dependency). Remove the ignore and add a
      capped override when 3.0.4 ships.
    - `KeycloakTokenVerifier` (RS256/JWKS) has no test; pyjwt 2.15.1 was
      checked by hand only.
    - CI does not run the web vitest suite or the Sales browser walk.

- **CI: the three run-state announcement timeouts were a plugin race**
  (fixed 2026-10-02). pytest-asyncio (auto mode) and anyio's pytest plugin both
  wrap async fixtures; the one registered last wins, and registration follows
  the order of site-packages. On the runner image of 2026-09-20 anyio won for
  modules marked `pytest.mark.anyio`, so the LISTEN fixture ran on a loop that
  was not running and never heard the NOTIFY. Reproduced locally by forcing
  the order (3 failed), green after the fix in both orders (4 passed); the
  product code was never at fault. The anyio plugin is now off in `addopts`
  (`-p no:anyio`) and the marker is gone from four modules, so a new
  `pytest.mark.anyio` is a collection error under `--strict-markers`.
- **Tenant-schema guards read the catalog** (2026-10-02).
  `test_rls_coverage.py` and the USAGE test in `test_privileges.py` find every
  non-system schema with a `tenant_id` column instead of naming three, so a
  context's new schema is checked the day it exists (failure-modes #0). Still
  named by hand: `0001_platform_grants.sql` grants USAGE and default table
  privileges on `platform, knowledge, memory` only, so a new schema's migration
  ships both itself. The USAGE test catches a missing USAGE; missing table
  grants are caught only by the context's own tests running as `dw_app`.
- **Offboarding reads every workspace of a tenant** (2026-10-03,
  `platform-runtime/workspace-scope-offboarding/`, ticket 01 done). The lane sets
  `app.workspace_scope = 'tenant'` per transaction; `test_rls_coverage.py` fails a
  policy that reads it outside `tenant AND (workspace OR scope)` and a
  workspace-narrowed table that does not read it. Needed before the first
  context narrows its tables by workspace. Found on the way: offboarding loses
  in-app notifications unexported (`ops-hardening.md` Open).
- **Approval decisions audited; approvals, runs and audit read by workspace**
  (`platform-runtime/approval-audit-and-workspace/`): HITL-11 and the rest of
  TEN-04. Ticket 01 open, and comes before the first product gate. Ticket 02
  **resolved 2026-10-06**, upstreamed from the first product's repo: the
  repository narrows approval, run and audit reads to the caller's workspace
  (RLS unchanged, still tenant-only), `decide` resumes in the run's own
  workspace, `GET /runs/{id}` checks `runs.read`, the audit route checks
  `audit.events`, cursors carry the workspace, keyset indexes carry
  `workspace_id` (`6d4aed20ccf2`). Open: whether the UoW should own the
  workspace instead of a required read argument.
- **Tickets written for the first product, platform side** (2026-10-03, all
  `ready-for-agent`, product-neutral), each under `platform-runtime/<folder>/`:
  `scope-holder-check` (ask whether a user holds a scope without an
  `AccessContext`, for apply-time checks and worker lanes), `eval-grader-registry`
  (a context registers its own graders), `approval-inbox-link` (`/approvals`
  links a context's approval to that context's own inbox), `nav-any-scope` (a
  menu item shown for any of several scopes), `support-access` (support access
  the customer grants, ADR 0008), `tenant-members-and-invitations` (tenant-wide
  users, per-workspace roles, invitations).
- **Harness hardening, from the 2026-10-06 harness audit** (all
  `ready-for-agent`, product-neutral, in this order), each under
  `platform-runtime/<folder>/`: `memory-vectors` (Qdrant memory points deleted
  by retention, supersession and offboarding; the ranker reorders only the ids
  SQL recalled; **resolved 2026-10-06** in `55bd789`),
  `memory-write-trust` (classification from the cited documents,
  workspace-checked evidence, confidence computed by code, CHECKs, retention
  classes nothing can assign removed; **resolved 2026-10-06**), `memory-review-queue` (REVIEW becomes a
  `memory.review` approval; **resolved 2026-10-06**; the decision audit and
  the workspace narrowing of `decide` stay with `approval-audit-and-workspace`
  01 (open) and 02 (resolved 2026-10-06)),
  `compaction` (long tool loops and multi-turn threads really compact, budget
  from the profile, checkpoint retention; **resolved 2026-10-06**),
  `retrieval-correctness`
  (`document_ids` inside the Qdrant filter, one embedding builder, a pinned
  agent-loop prompt; **resolved 2026-10-06**), `dev-harness` (commit gate for PowerShell and
  `git -C`/`-c`, per-session Stop hook, plugin wording, `ui-quality.md`;
  **resolved 2026-10-06**: `scripts/test_claude_hooks.sh` in `make ci` and the
  CI python job, green on Git Bash without jq and on Alpine with jq; a real
  PowerShell-tool commit was blocked in a nested session. Not done: no
  `permissions.deny` on the gate switches, because a shell `touch` gets past it,
  so it is gitignore plus a human-only note; the new CI step has not been
  watched on GitHub; the Stop hook cannot tell which session made a commit).
  Dropped as already true here: the rerank outage fallback (`4cb45dc`), and
  offboarding purging run checkpoints (catalog discovery already does; the
  `compaction` ticket only pins it with a test).
- **Upstreamed from the first product's repo** (2026-10-06, branch
  `feat/upstream-elmich-platform`): who may decide an approval is stamped on
  it as `required_scope` and enforced in `decide`; `platform_admin` does not
  pass a stamp (platform ADR 0004, `docs/adr/0011` here, migration `36dabf47619c`); the inbox reads
  `can_decide` from the same checks. The resume payload carries `decided_by`
  from the decider's verified context. A multipart route claims its
  idempotency key from parsed fields (`get_form_idempotent_operation`,
  `claim_fields`); `PAYLOAD_TOO_LARGE`→413, `UNSUPPORTED_MEDIA_TYPE`→415.
  Not taken: the product's contexts, migrations, channel code and web look.
- **Who sees a stamped approval** (2026-10-07, branch
  `feat/approval-visibility`, platform ADR 0004 amendment, `docs/adr/0011` here): a stamped request is listed
  and served only to who may decide it and to its requester; everyone else,
  `platform_admin` without the stamp included, gets 404 / absence, the
  decision included. `ApprovalAudience` owns the rule, the repository filters
  by it in SQL (`visible_to`, required on `get` and `list_pending`) and
  `SqlPendingApprovalQuery` now takes the composition root's
  `ScopeAuthorizationService`. Unstamped requests are unchanged.
- **`build_agent` has no production caller** (checked 2026-09-29): this
  checkout ships no bounded context.
- **Platform pieces waiting for their first context** (failure-modes #1).
  They were built with the Supply Chain context as their first caller, and
  that context was removed on 2026-09-29. Each keeps its own tests, and each
  is kept because the next product needs the same thing:
    - `SingleCallModelGateway`: a one-call model run that frees its
      spend-ledger entry;
    - `SqlPolicyOverrideRepository` / `platform.policy_overrides`: a
      tenant's own copy of a policy document;
    - `SqlPendingApprovalQuery`: a context counting its own pending
      approvals by type prefix;
    - `scope_holders.py` and `platform.deliver_notification()`: **taken by
      Sales (ticket 05, 2026-10-05)**: pausing DW1 tells every holder of
      `sales.worker.resume`, wired in `bootstrap/wiring.py`.
    - `required_scope` on an approval and `decided_by` in the resume
      payload: **taken by Sales** (ticket 10; the stamp moved from the
      payload's `decide_scope` to the column in the platform merge of
      2026-10-07).
    - `get_form_idempotent_operation` / `claim_fields`, and
      `PayloadTooLargeError` / `UnsupportedMediaTypeError`: no platform
      route takes a form or raises them (a unit test mounts a probe route).
      A context that adopts one of these wires it there and names it
      here as taken.
- **Nothing emits `memory.candidate_proposed`.** A bounded context has to
  decide what is worth remembering; the platform ships only the consumer.
- **The GIN index on `subject_refs` is untuned.** The planner prefers
  `ix_items_page` on an empty table, and tuning it before real data exists
  would be a guess.
- **Vector-ranked recall is not wired**, although Qdrant and `EmbeddingPort`
  already serve knowledge.
- **The chat path reads the platform profile, not the tenant's.**
  `OpenAICompatibleChatModelFactory.resolve` calls `chat_route` with no
  tenant while the agent budget prices the tenant's route: the shape the
  structured gateway had until 2026-09-28. No agent loop runs in production
  yet, which is why it waits.
- **The release manifest does not pin model profiles.** They carry
  `routing_policy_version` but no run records which profile it used, except
  the usage recorders (now the effective id).
- **`make check-deepgram` and `make check-search` run scripts that do not
  exist**, left over from the product this was extracted from.
  `make check-model` was the third, and works since 2026-09-28.

## Deliberately not taken

- **Vector or graph recall deciding the recalled set.**
- **LLM-decided memory merging:** the model proposes, code decides.
- **An `AGENTS.md`-style memory file** the model edits. Structured rows carry
  provenance, supersession, audit and RLS, and a file carries none of them.
- **`create_deep_agent`'s builtin file and shell tools.** `build_agent` uses
  `create_agent`, which installs none; `OfferedToolsOnlyMiddleware` guards a
  context that reaches for them anyway.

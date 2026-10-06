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

- **CI gitleaks**: confirmed green in CI on run 37398677606 (2026-10-06,
  "no leaks found", 88 commits). Close this entry once that run's other
  failures (below) are confirmed fixed by a push.

- **CI: three run-state announcement tests time out** (2026-09-29, still red
  on run 37398677606, 2026-10-06). Cause found 2026-10-06, fixed locally; not
  yet confirmed in CI (nothing pushed).
    - **Cause:** two async test runners claimed the same tests. The tests
      were marked `pytest.mark.anyio` while `asyncio_mode = "auto"` makes
      pytest-asyncio run every async test too. Which plugin ran an async
      FIXTURE depended on plugin registration order, and that order is
      reversed between the two venvs (`--trace-config`: Windows registers
      anyio first, Linux registers pytest-asyncio first). On Linux, anyio ran
      the `heard` fixture on its own loop and pytest-asyncio ran the test on
      another. The asyncpg LISTEN connection belonged to a loop that was not
      running during the test, so its socket was never read. A probe test
      printed `same_loop=False fixture_loop_running=False` on Linux and
      `same_loop=True` on Windows. Test order had nothing to do with it: on
      Linux the file fails alone too (3 failed, 1 passed). The silence test
      passed because hearing nothing was the expected result.
    - **Why only these tests:** the other anyio-marked fixtures open
      connections lazily, through a NullPool engine, on whichever loop is
      running when they are used. `heard` is the only one that opens its
      connection while the fixture is being set up.
    - **Reproduced** in a `python:3.12-slim` container on the compose
      network, running `uv run pytest -m integration` over the
      `dw_agent_runtime` suite, which is CI's first 48 tests in CI's order:
      3 failed and 45 passed, the same three tests as CI. After the fix:
      48 passed.
    - **Fix:** one runner. The `anyio` marks and `anyio_backend` fixtures
      are removed from the five files that had them, and `-p no:anyio` is in
      `addopts`. If someone adds the marker back, `--strict-markers` refuses
      it at collection (checked).
- **CI pip-audit** (run 37398677606) flagged pyjwt 2.14.0
  (PYSEC-2026-4141 / GHSA-x33g-cr3x-6449) and virtualenv 21.7.10
  (PYSEC-2026-4011..4014). The lock now has pyjwt 2.15.1 and virtualenv
  21.14.5, and dw_platform's floor is raised to `pyjwt>=2.15`. The same
  pip-audit command CI runs finds no known vulnerabilities. Not yet
  confirmed in CI.
    - **Gap:** `KeycloakTokenVerifier`, the production RS256/JWKS path, has
      no test at all. The unit suite covers only the dev HS256 verifier. A
      scratch run against a local JWKS server on pyjwt 2.15.1 accepted a
      valid token and refused each of: wrong audience, wrong issuer,
      expired, missing `sub`, missing `exp`, a foreign key, HS256 and
      `alg: none`. That run was not committed as a test, so the next pyjwt
      bump has nothing that checks this path.
- **CI scaffold-smoke** (run 37398677606): `lint-imports` failed with
  "Module 'dw_smoke_ctx' does not exist". The generator found its place in
  `root_packages` by the lines `"dw_observability", "dw_evals", ]`. Once
  `dw_sales` was appended to `root_packages`, those lines matched only the
  "Kernel is pure" list, so the new package was written there. A second
  failure was hidden behind it: the template's `tests/unit/__init__.py`
  makes a top-level package named `unit`, so a second context's slice test
  failed to import (`No module named 'unit.test_smoke_ctx_slice'`).
    - **Fix:** `scripts/new_context.py` now finds each list inside its own
      table. It adds the context to "Platform does not import contexts" and
      to the domain-purity contract, and gives it a layers contract. From the
      second context on, it adds an independence contract between contexts.
      It reads the file back and refuses to write if any of these entries
      did not land where intended. The template no longer ships
      `tests/unit/__init__.py`.
    - **Verified** by walking the job's exact steps in a scratch worktree:
      red at HEAD, green with the fix. With two contexts generated,
      `dw_sales`'s contracts are unchanged. Not yet confirmed in CI.
- **CI pnpm audit + trivy** (run 37422042077, commit 2284d3c): both red, and
  they share a cause. The audit found 8 high advisories: brace-expansion in
  all three of its lines, braces, and source-map-js. Trivy found one row:
  `source-map-js@1.2.1` in `dw-web:local` (CVE-2026-93749). api, worker and
  docgen scanned 0. Fixed locally in `pnpm-workspace.yaml`, not yet
  confirmed in CI:
    - **Overrides:** the three brace-expansion lines now have floors of
      1.1.20, 2.1.6 and 5.0.11, each capped below its next major (5.x was an
      exact `5.0.9` pin). A new `source-map-js` override has a floor of
      1.2.2. The lockfile changes 4 packages. pnpm 11 rewrites the lockfile
      in single quotes, so it was run back through prettier to keep the
      committed double-quote style and a small diff.
    - **braces has no fix to take.** GitHub lists no first patched version,
      npm's latest is 3.0.3, and micromatch/braces#70 is open. Every
      `@next/eslint-plugin-next` release through 16.3.8 pins
      `fast-glob 3.3.1`, which pulls in micromatch and braces, so no override
      or upgrade removes it. `auditConfig.ignoreGhsas` lists only
      GHSA-vfj7-8cjw-p6xm, so a new advisory on braces still fails the
      audit. Why that is safe: the path is dev-only, it is absent from every
      image, and its only input is `settings.next.rootDir` from our own
      ESLint config. **Owed:** remove the ignore and add a capped override
      once braces 3.0.4 ships.
    - **Measured:** `pnpm audit --audit-level high` was 11 vulns (8 high)
      with exit 1. It is now exit 0, reporting "1 high (1 ignored)", and the
      moderates are gone too. Trivy 0.74.0 with CI's flags (`fs`, HIGH and
      CRITICAL, `--ignore-unfixed`) is red on HEAD's lockfile with the same
      CVE row as CI, and exit 0 on the fixed lockfile. The image itself was
      not rescanned locally: Docker Desktop's BuildKit was failing
      (`context deadline exceeded`) under other sessions' stacks.
      These are green: frozen install, generate:api-types (no diff),
      format:check, lint, typecheck, and web vitest (215/215). `next build`
      compiles, typechecks and generates 26/26 pages; its only failure is
      the known Windows standalone-symlink EPERM.
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
      A context that adopts one of the others wires it there and names it
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

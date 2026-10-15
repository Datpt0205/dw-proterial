# 18 — CI runs the web tests

Status: built and reviewed (2026-10-12; committed in 395dbf3); acceptance 1
waits on a real CI run ("Still to prove" item 1) and acceptance 3 on the
investigation of the walk's red runs (see "Switching the walk to blocking");
"Still to prove" items 2 and 3 were seen on CI from 2026-10-13
Blocked by: —
Category: enhancement

## What

CI's `frontend-quality` job runs format check, lint, typecheck and build.
It runs neither the vitest suite (which holds the antd-only guard, the layer
order test and the approvals registry tests) nor the DW1 Playwright walk
(`make test-web-sales`). A change that breaks the demo, or brings back a
banned UI library, passes CI. Verified 2026-10-12 in `.github/workflows/ci.yml`.

The walk is not yet stable: it passed 11/11 once; two runs timed out under
machine load (`sales.md`, ticket 09).

## Acceptance

1. `pnpm --filter @dw/web test` (vitest) runs in `frontend-quality` and
   fails the job on a red test. Demonstrated by pushing a deliberately
   failing test on a branch and watching CI go red (failure-modes #1, the
   trivy step: a step is wired only once seen running).
2. The DW1 walk runs in its own job with Postgres, the dev-auth API and the
   web app, on the schedule Đạt picks (below), and uploads the Playwright
   trace on failure.
3. Before the walk is required, it passes three consecutive CI runs; a
   timeout is investigated, not retried away.

## Questions for Đạt (why needs-info)

This is "whether CI runs the web vitest suite" from `PLAN.md`'s decisions
owed.

1. Vitest on every push? Proposed: yes (seconds, no services).
2. The Playwright walk: every push, every push to `main`, or nightly?
   Proposed: on `main` and nightly, non-blocking until 3 green runs in a row,
   then blocking on `main`.

## Sources (as of 2026-10-12)

- `.github/workflows/ci.yml` (`frontend-quality`), `Makefile`
  (`test-web-sales`), `apps/web/e2e/sales-demo.spec.ts`,
  `apps/web/lib/__tests__/antd-only.test.ts`.

## Comments

- 2026-10-12, Đạt ("làm theo bạn tự recommend"): the proposed defaults hold.
    1. Vitest runs on every push in `frontend-quality`.
    2. The Playwright walk runs on pushes to `main` and nightly, non-blocking
       until three consecutive green runs, then blocking on `main`.

## Built (2026-10-12)

- **Vitest on every push:** step `Unit tests (vitest)` in `frontend-quality`
  (`.github/workflows/ci.yml`), `pnpm --filter @dw/web test`, between
  Typecheck and Build; the job is renamed "Frontend lint · typecheck · test ·
  build" (safe: `main` has no branch protection and no rulesets, checked
  with `gh api` on 2026-10-12, so no required check names the old title).
  Locally the exact command passes (32 files, 303 tests, 61 s); a throwaway
  `expect(1).toBe(2)` test run through it exits 1, and the file was removed.
- **The DW1 walk:** its own workflow, `.github/workflows/web-e2e.yml`, job
  `sales-walk`, on pushes to `main`, nightly at 19:00 UTC (02:00 in Vietnam)
  and on demand (`workflow_dispatch`). A workflow of its own because a
  `schedule` in `ci.yml` would run every CI job nightly. It starts Postgres,
  Qdrant, Valkey and SeaweedFS the way the integration job does (no Keycloak:
  dev auth; no document sandbox: Sales prints its own files), creates the
  buckets with `compose run --rm s3-setup`, runs `make db-migrate`, then
  `make test-web-sales`, which starts the dev-auth API and the web through
  `playwright.config.ts` and resets the demo tenants itself. On failure or
  cancellation it uploads `apps/web/test-results/` (traces, screenshots) and
  `apps/web/playwright-report/` as the artifact `playwright-sales-walk`,
  kept 14 days. No retries (acceptance 3). The run is not cancelled by the
  next push, so each counted run finished.
- **pip-audit sees the optional extras:** the `security-scan` export is now
  `uv export --all-packages --all-extras --no-emit-workspace`, 209 pinned
  packages against 142 before (docling, docling-core/-parse/-slim, torch,
  transformers and their tree). Run locally with pip-audit 2.9.0: "No known
  vulnerabilities found". Mutation: the same file with `docling==2.128.0`
  reports eight advisories (PYSEC-2026-4189..4195, GHSA-p944-4xh2-x776) and
  exits 1; the old export holds no docling line at all. Still blind:
  `torch==2.14.0+cpu` and `torchvision==0.29.0+cpu` are skipped ("Dependency
  not found on PyPI") because PyPI does not know a `+cpu` local version.
  Audited by hand under their public versions (`torch==2.14.0`,
  `torchvision==0.29.0`, `--no-deps`): no known vulnerabilities on
  2026-10-12. Only trivy's image scan covers them on every push.

## Review (2026-10-12, adversarial reviewer)

- **Fixed:** the trace upload relied on GitHub still running a
  `failure() || cancelled()` step after the job-level 45-minute timeout,
  which nobody had measured. The walk step now has `timeout-minutes: 30`:
  a walk that hangs past it fails its own step, and the upload runs on
  `failure()` with time left. Playwright's own per-test limits (600 s, one
  of 480 s) still fire first on a single hung stage and write its trace.
- **Re-measured, baseline first:** `pnpm --filter @dw/web test` passes
  (303/303, rc 0); with a throwaway source file exporting from
  `lucide-react` (the banned-library case this ticket exists for) the same
  command fails `antd-only.test.ts` and exits 1, file removed. pip-audit on
  the `--all-extras` export: rc 0; with `docling==2.128.0` eight advisories,
  rc 1; the old export has no docling line. actionlint 1.7.7 on both
  workflows: rc 0; a copy with `timeout-minutes: thirty` and `failur()`
  fails, rc 1.
- **Checked without a runner:** Make's `include .env` exports
  `.env.example` as CI copies it (`DW_API_PROFILE=local`, the migrator URL,
  `DW_MODEL_PROVIDER=mock`); DW1 calls no model (`workflows/graph.py`), so
  the mock provider is enough; Sales registers no worker lane, so the walk
  needs no worker; `/api/v1/health` is liveness only, so Playwright's
  readiness wait does not depend on Keycloak or docgen; Playwright 1.62.1
  merges `webServer.env` over `process.env`, so dev auth overrides the
  copied `.env`'s `oidc`; the vitest files read only tracked files, and the
  workspace packages export source, not a build.
- **Not part of acceptance:** the pip-audit `--all-extras` change is
  outside this ticket's three acceptance items (it closes a gap recorded in
  `platform-runtime.md`); kept because it is measured and red when it
  should be.

## Switching the walk to blocking

- **How:** delete the one line `continue-on-error: true` from the
  `sales-walk` job in `.github/workflows/web-e2e.yml`, in a commit whose
  message names the three consecutive green run ids. Nothing else changes.
- **What counts:** three finished runs in a row, of any trigger, whose
  `sales-walk` job succeeded. While `continue-on-error` is on, the workflow
  run reads as succeeded even when the walk failed, so count by the job,
  not by the run list: `gh run view <id> --json jobs --jq '.jobs[] |
{name, conclusion}'`. A red or timed-out run restarts the count and is
  investigated (acceptance 3), never re-run until green.
- **Who:** whoever sees the third consecutive green run, an agent included,
  makes the change and records the run ids here; the condition is objective
  and Đạt decided it on 2026-10-12, so it needs no new decision. A red run
  in the count goes to Đạt with what the trace shows.
- **What blocking means here:** `main` is not protected, so a red walk on
  `main` turns the commit and the run red; it does not refuse the push. A
  merge gate would be branch protection, which nobody has asked for.
- **Count (2026-10-15):** by "What counts" the condition is met. Six
  consecutive green `sales-walk` jobs since the red 38545009082 (`99cb905`:
  the seed and the worker raced to settle the seed's `sales.rules` decision,
  fixed in `9704778`): 38548179383, 38554501750, 38644832623, 38664301595,
  38667353972, 38669232021. Only the last two ran on commits after the race
  fix `9704778`. Flipped 2026-10-15 by the agent (the rule is met; waiting for a third post-fix green would be stricter than it):
  `continue-on-error` is gone from `web-e2e.yml`, the commit naming
  38664301595, 38667353972 and 38669232021.

## Still to prove (needs real CI runs)

1. Acceptance 1: push a branch with a deliberately failing vitest test
   (e.g. `apps/web/lib/__tests__/ci-red.test.ts` with `expect(1).toBe(2)`),
   open a PR or push it, and see `frontend-quality` go red at
   "Unit tests (vitest)"; then delete the branch. Not done: agents here do
   not push.
2. The walk's first run on a runner: `next dev` compiling each route on a
   2-core runner may approach the walk's 60 s expectation timeout (the two
   timeouts of ticket 09 were under local load); `playwright install
--with-deps chromium` and the 45-minute job limit are unmeasured there.
   Seen since: the walk passes on a runner, first on `e97042b` (2026-10-13),
   its green jobs taking 8-14 minutes.
3. What `gh run view --json jobs` reports as the `sales-walk` conclusion
   when the walk fails under `continue-on-error` (the count above depends
   on it), and that the trace artifact is uploaded on that failure. Seen
   since: the job reads `failure`, and run 38545009082 (`99cb905`, a test
   failed) uploaded `playwright-sales-walk`.
4. The `security-scan` job with `--all-extras` on Linux (the local run was
   on Windows; the export is universal, the marker evaluation is not).
5. Scheduled workflows in a public repository stop after 60 days without a
   commit; the nightly run is only as alive as the repository.

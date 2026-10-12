# 18 — CI runs the web tests

Status: needs-info
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

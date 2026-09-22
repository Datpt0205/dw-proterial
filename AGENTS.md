# AGENTS.md

Shared engineering policy for any tool that reads this file (Codex and
similar) working in the Digital Worker Platform repo. This is not a second
copy of the architecture — read `CLAUDE.md` (architecture of record) and
`.claude/rules/failure-modes.md` (documented failure shapes, with counts)
before reviewing or writing anything here. This file only adds what's
specific to running outside Claude Code: how to validate a change, and what
to report.

## Stack

Python 3.12 / uv workspace (FastAPI, SQLAlchemy 2 async, Alembic, LangGraph)
plus a pnpm workspace (Next.js, TypeScript strict). `CLAUDE.md` has the full
required stack and the non-negotiable architecture — modular monolith, an
async worker process, hexagonal boundaries, PostgreSQL RLS as the tenancy
mechanism, versioned artifacts, human-in-command.

## Validation

Before treating a change as done, run the same gate CI runs:

    make lint
    make typecheck
    make test-unit
    make test-architecture

`make ci` runs the full local gate (adds contract tests, eval smoke, the
release-manifest check). `make test-integration` and `make test-e2e` need
`make infra-up` first; skip them for a change with no adapter/DB impact. Full
target list: `make help`.

## Code review rules

Report only what changes behaviour someone relies on:

- correctness bugs, regressions
- a new or widened trust-boundary gap — cross-tenant reads/writes, an
  authorization check made client-side or only in a UI layer, an agent
  autonomy/approval path that got easier to skip, model output used directly
  as an identifier, route, permission or threshold
- a fact duplicated from a table, config file or schema that already owns it
  (`CLAUDE.md`'s "One Owner Per Fact" — in this repo that's `TenantOverlay`,
  `platform.plans`, `NAMING_CONVENTION`, and similar)
- a resource created with no destroy path, a default that fails open, or a
  test that cannot go red — see `.claude/rules/failure-modes.md` for the
  shapes this repo has actually shipped, with counts
- a migration touching a tenant table with no RLS/FORCE/policy, a new FK with
  no explicit `ON DELETE`, or a list endpoint's `ORDER BY` with no index that
  carries it

Do not report: formatting, naming preference, optional refactors, or style
opinions the linter doesn't already enforce. Ruff/mypy/ESLint own style; a
review here is for correctness and the trust boundaries above.

## Boundaries a generic review would miss

- Domain code (`domain/`, most of `application/`) must not import FastAPI,
  SQLAlchemy, LangGraph, Qdrant or a provider SDK — flag it if it does.
- A non-Python service may touch Postgres only under the four conditions
  `CLAUDE.md` states (a role that doesn't bypass RLS, `app.tenant_id` set per
  transaction, no migrations of its own, no re-derived authorization). No
  service in this repo is exempt from `test_rls_coverage.py`.
- `tenant_id=None` in an overlay or registry call means the platform layer,
  not "no tenant" — flag a call that could receive a client-supplied tenant
  id instead of one resolved from the verified access context.

For anything not covered above, this file defers to `CLAUDE.md` and to
`.claude/skills/reviewing-feature-security/` (Claude Code's own pre-ship
checklist for the six trust boundaries) rather than repeating them here.

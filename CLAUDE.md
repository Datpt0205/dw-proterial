# Architecture of record — Digital Worker Platform

This repository is a **platform backbone**, not a product. It carries everything
that is not a business domain: the agent runtime, tenancy and authorization,
knowledge, memory, connectors, observability, evaluations, and the api/worker/
sandbox/web shells. A product adds one or more bounded contexts as packages
under `packages/python/dw_<name>` and inherits the rest.

This file is the architecture of record. Do not silently deviate from it —
record a decision instead.

## Adding a bounded context (the plug-in points)

1. Package `packages/python/dw_<name>` with layers
   `domain/ application/ workflows/ adapters/ presentation/`.
2. Register in the root `pyproject.toml`: `tool.uv.sources`, ruff
   `known-first-party`, mypy `files`/`mypy_path`, coverage `source`, and
   import-linter `root_packages` — plus an `independence` contract the moment a
   second context exists.
3. Wire it at the marked seams: `apps/api/src/dw_api/bootstrap/wiring.py`
   (build from `container.runtime`, the published `RuntimeSeam`),
   `apps/api/src/dw_api/main.py` (mount the router), and
   `apps/worker/src/dw_worker/main.py` (register consumers and reap targets).
4. Ship `configs/workers/<name>.yaml`, prompts under
   `configs/prompts/<name>/<id>@<semver>.yaml`, tool specs under `configs/tools`,
   a toolset under `configs/toolsets`, and policies under `configs/policies`.
5. Add an eval dataset under `evals/datasets/` with FULL security coverage
   (prompt injection, cross-tenant attack, missing evidence) and graders keyed
   `<name>.<gate>` in `dw_evals`.
6. Add Alembic migrations continuing from the baseline (`0001`).
7. Update `scripts/verify_architecture.py` (`IMPORT_TO_DIST`) and the Dockerfile
   COPY lists.

## Non-negotiable architecture

- One monorepo and one shared UI shell.
- Modular monolith plus a separate async worker process.
- Independent bounded contexts; never a super-agent. Where one context needs
  another's data, the dependency goes through a Protocol the **consumer**
  declares and the composition root satisfies — never a direct import.
- Clean/Hexagonal dependency direction.
- Domain code must not import FastAPI, SQLAlchemy, LangGraph, Qdrant or a
  provider SDK.
- All external systems sit behind ports and adapters.
- PostgreSQL is the system of record.
- Qdrant retrieval always receives trusted tenant/workspace/ACL filters from
  backend context; filter injection happens only inside the knowledge gateway.
- Redis/Valkey is never a source of truth.
- Side effects require policy evaluation, idempotency and audit; critical
  effects require approval.
- Every worker, graph, prompt, tool, policy, event schema and evaluation dataset
  is versioned, and a release manifest pins the set a run used.
- Human-in-command.

## Required stack

Python 3.12 with a uv workspace. FastAPI, Pydantic v2, SQLAlchemy 2 async,
Alembic. LangGraph for orchestration/checkpoint/HITL. PostgreSQL, Qdrant,
Redis/Valkey, MinIO/S3. Next.js, TypeScript strict, Tailwind, shadcn/ui.
OpenTelemetry, optional Langfuse. Ruff, mypy, pytest, import-linter, pre-commit.
pnpm workspace and lockfile. Pin versions; commit lockfiles; never `latest`.

## Layer rules

Per context: `domain` (entities, value objects, domain events, rules),
`application` (commands, queries, handlers, ports, DTO mapping), `workflows`
(versioned graph state/nodes/routing), `adapters` (persistence, external
systems), `presentation` (API routes, event handlers).

Direction: `application → domain`, `presentation → application`,
`adapters → application ports`. Only a composition root imports a concrete
adapter. Constructor injection — no service locator, no mutable global client.

## Tenancy and authorization

- Every tenant-scoped table has `tenant_id` and `workspace_id`.
- PostgreSQL RLS is enabled, FORCEd, and tested. The application role must not
  hold `BYPASSRLS`; only the migrator does.
- Tenant context is set per transaction from a verified server-side access
  context — never from anything the client sent.
- Cache keys and object paths include tenant/workspace.
- Entitlement checks and authorization checks are separate concerns.
- Negative tests for cross-tenant reads and writes are mandatory.
- Hiding a control is not authorization. Enforce where the mutation happens.

## Agent and tool rules

- Graph state is typed and versioned; LLM output is always validated into a
  Pydantic schema.
- Workflow nodes contain no provider SDK and no SQL, and never import a concrete
  adapter — they take what they need by injection.
- A tool definition carries version, schemas, scopes, side-effect level,
  approval policy, timeout and idempotency. The executor authorizes, validates,
  executes, validates the output and audits.
- All side effects use idempotency keys.
- Approval pauses and resumes a durable, checkpointed run.

## Data model rules

- Timestamps are `timestamptz`.
- Every foreign key declares `ON DELETE` explicitly and is indexed on its own
  side.
- `updated_at` is maintained by a database trigger.
- Append-only, unbounded tables are range-partitioned, with a DEFAULT partition.
- Constraint names come from `dw_kernel.naming.NAMING_CONVENTION`; a new
  `MetaData` passes it.
- Migration `0001` is the immutable baseline. Corrections are new revisions.
- **A revision id is alembic's random hex, never a hand-picked number.** Two
  people working at once both guess the same "next number", git reports no
  conflict because the filenames differ, and alembic then refuses the merged
  tree with "revision is present more than once" — measured three times in one
  day on the product this was extracted from. Generate migrations with
  `alembic revision -m "..."` and keep the sequence in the _filename_ only,
  where it is a reading aid and carries no meaning.
- Privileges are part of the schema. A role that cannot read a table is an
  application that fails on its first real query while every health check still
  passes, so grants ship with the migration and are asserted by
  `dw_platform/tests/integration/test_privileges.py`.
- Partitioned tables need next month's partition before rows need it.
  `scripts/roll_partitions.py` is idempotent and belongs on a schedule; the
  DEFAULT partition is a safety net, not the plan.

## Environments

`local | test | uat | production`. `uat` and `production` are both deployed and
obey identical rules — the difference is blast radius, not strictness. Gate
anything that must not reach a deployed environment on `settings.is_deployed`,
never on `profile == "production"`, so a fifth environment cannot silently
reopen a hole. The compose overlay pins the profile.

## Observability and evaluation

Emit trace metadata for tenant/workspace (safe identifiers only), worker and
artifact versions, run/node/model/retrieval/tool/approval, latency, token use
and cost, and an error taxonomy. Ship a golden dataset and smoke evals per
context, including prompt injection, missing evidence and tenant leakage.

## Testing and CI

Unit, architecture/import-boundary, PostgreSQL repository/RLS integration,
Qdrant tenant-filter integration, LangGraph checkpoint/resume, outbox/idempotency,
API contract, generated frontend client compile, end-to-end vertical slice, and
eval smoke. CI runs config/contract validation, Python lint/typecheck, frontend
lint/typecheck/build, unit tests, architecture tests, integration tests,
security/dependency scan, eval smoke, container build and a compose smoke test.

## Work style

1. Inspect before changing.
2. Plan, and state assumptions.
3. Work in small phases; run tests after each.
4. Prefer a thin end-to-end slice over empty abstractions.
5. Never leave a placeholder-only module. A deferred component ships a working
   mock adapter and a documented port.
6. Keep diffs focused; update this file when the architecture changes.
7. Record a decision rather than deviating silently.

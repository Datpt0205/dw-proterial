# Digital Worker Platform

A multi-tenant backbone for products whose work is done by agents: a versioned
agent runtime with human-in-command approvals, retrieval, memory, connectors,
tenancy with row-level security, an audit trail, and the evaluation harness that
keeps the safety gates honest.

It ships **no business domain**. A product plugs its own bounded context in at
three declared seams and inherits everything above.

---

## What is here

| Package            | Owns                                                                                                                                                                                                                      |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `dw_kernel`        | Pure primitives: errors, ids, clock/id ports, outbound-URL guard, circuit breaker, the database naming convention. Standard library only — enforced.                                                                      |
| `dw_platform`      | Tenants, workspaces, users, memberships, roles, permission sets, the manager hierarchy, plans/entitlements, approvals, audit, the transactional outbox, provisioning.                                                     |
| `dw_agent_runtime` | Worker/graph/tool registries, the tool executor (authorization → validation → execution → audit), model gateway and profiles, prompt bundles, checkpoints, run store, approval pause/resume, the document sandbox client. |
| `dw_knowledge`     | Documents, chunking, ingest jobs, embeddings, reranking, the retrieval gateway that injects the tenant filter.                                                                                                            |
| `dw_memory`        | Memory items and the write policy that decides what may be remembered.                                                                                                                                                    |
| `dw_connectors`    | Outbound channel ports and their adapters.                                                                                                                                                                                |
| `dw_observability` | OpenTelemetry wiring; Langfuse as an OTLP endpoint.                                                                                                                                                                       |
| `dw_evals`         | Dataset format, runner, and the four platform safety graders.                                                                                                                                                             |

| App           | Is                                                                                       |
| ------------- | ---------------------------------------------------------------------------------------- |
| `apps/api`    | FastAPI. Platform routes under `/api/v1`; a context mounts its router beside them.       |
| `apps/worker` | The async loop: transactional outbox, knowledge ingestion, stale-job reaping, retention. |
| `apps/docgen` | A network-isolated sandbox that runs model-written shell to produce documents.           |
| `apps/web`    | Next.js shell: Home, Approvals, Knowledge, Memory, Integrations, Audit, Admin.           |

---

## Getting started

```bash
make bootstrap        # Python (uv) + Node (pnpm) dependencies
cp .env.example .env  # then fill in the secrets it names
make infra-up         # Postgres, Qdrant, Valkey, MinIO, Keycloak, docgen
make migrate          # create the schema
make dev              # api + worker + web, with reload
```

Everything is also runnable as containers: `make docker-up`.

---

## Adding a bounded context

A context is a package under `packages/python/dw_<name>` with the layers
`domain/ application/ workflows/ adapters/ presentation/`, and it joins the
platform in exactly three places. They are marked in the code.

1. **`apps/api/src/dw_api/bootstrap/wiring.py`** — build the context's handlers
   from `container.runtime`, the published `RuntimeSeam`: session factory,
   clock, ids, telemetry, model gateway, chat-model factory, tool registry and
   executor, tool specs, toolsets, graph and worker registries, knowledge
   gateway, memory service.
2. **`apps/api/src/dw_api/main.py`** — mount its presentation router, guarded on
   the dependency it needs.
3. **`apps/worker/src/dw_worker/main.py`** — register its consumers, and a
   `ReapTarget` for each job queue it owns.

Then register it in `pyproject.toml` (uv sources, ruff first-party, mypy paths,
import-linter `root_packages` plus an independence contract), ship its
`configs/` artifacts, add an eval dataset with full security coverage, and add
its migrations after the baseline.

Nothing above those seams may import a business package, and import-linter
fails the build if it does.

---

## Environments

Four profiles, and two of them are deployed.

| Profile      | Meaning                                                                               |
| ------------ | ------------------------------------------------------------------------------------- |
| `local`      | A developer's machine. Mocks allowed, docs exposed, private outbound targets allowed. |
| `test`       | CI. Same permissiveness; no external services assumed.                                |
| `uat`        | A real deployment with real people and real data.                                     |
| `production` | The live deployment.                                                                  |

`uat` and `production` are held to **identical** rules, because the difference
between them is who a mistake reaches, not how strict the configuration should
be. In both, startup fails on: a mock model provider, dev-mode auth, the
meaningless hash embeddings, a missing vector store, or CORS origins left
unlisted — and the OpenAPI schema and its UIs are not served.

The profile is pinned by the compose overlay, not by an environment variable
somebody has to remember:

```bash
docker compose -f infra/compose/docker-compose.yml \
               -f infra/compose/docker-compose.uat.yml  --profile full up -d
docker compose -f infra/compose/docker-compose.yml \
               -f infra/compose/docker-compose.prod.yml --profile full up -d
```

One deploy path for all three environments, run by CI or by hand:

```bash
scripts/deploy.sh <branch> <dev|uat|production>
```

---

## The data model

One baseline migration (`db/migrations/versions/0001_platform_baseline.py`)
creates three schemas — `platform`, `knowledge`, `memory` — and every later
change is an ordinary revision on top of it.

What the baseline guarantees:

- **Tenant isolation is enforced by the database.** Row-level security is
  enabled and FORCEd on every tenant-scoped table; the tenant comes from
  `app.tenant_id`, set per transaction from a verified access context. The
  runtime role does not hold `BYPASSRLS` — only the migrator does.
- **Every foreign key states what happens when its parent goes** — `CASCADE`,
  `RESTRICT` or `SET NULL`, never the implicit default.
- **Every foreign key is indexed on its own side**, so deleting a parent does
  not sequentially scan the child table while holding a lock on it.
- **`updated_at` is maintained by a trigger**, not by whichever code path
  remembered.
- **The two append-only tables are range-partitioned** — `audit_events` by
  `occurred_at`, `model_usage_ledger` by `created_at` — so retention is
  `DROP PARTITION` rather than a `DELETE` that has to be vacuumed. Both have a
  DEFAULT partition, so a row is never rejected for arriving outside every
  declared range.
- **Timestamps are `timestamptz`**, without exception.
- **Constraint names follow one convention** (`dw_kernel.naming`), so a later
  migration can name what it drops without querying the database first.

---

## Checks

```bash
make lint typecheck test-unit test-architecture test-contract eval-smoke
make ci               # all of the above, as CI runs them
```

CI (GitHub Actions and GitLab CI both ship, running the same commands) covers
config/contract validation, Python lint + type check, frontend lint/type/build,
unit tests, import-boundary and dependency rules, integration tests against real
Postgres/Qdrant/Redis/MinIO, a dependency and secret scan, the eval smoke suite,
a container build and a compose smoke test.

Safety is tested, not asserted: the eval suite grades prompt containment, the
tool-approval gate, the cross-tenant retrieval filter and the memory write
policy against the real components.

---

## Conventions

- Clean/Hexagonal: `application → domain`, `presentation → application`,
  `adapters → application ports`; only a composition root imports a concrete
  adapter. Domain code imports no framework, ORM or provider SDK.
- Every worker, graph, prompt, tool, toolset, policy and eval dataset is
  versioned, and a release manifest pins the exact set a run used.
- Side effects go through the tool executor: policy evaluation, idempotency key,
  audit record, and approval when the tool's spec says so.
- Human-in-command. An approval pauses a checkpointed run and resumes it.

`CLAUDE.md` is the architecture of record and the file to read before changing
any of the above.

# 04 — Persistence: `sales` schema, RLS, repositories

Status: ready-for-agent
Blocked by: 02, 03

## What

- Alembic revision (generated id) creating `sales` tables: messages state,
  order_cases, order_lines, findings, quote_cases, artifacts, case_events.
  tenant_id + workspace_id, RLS ENABLE + FORCE, policies, grants, FK ON
  DELETE explicit and indexed, timestamptz, CHECK on fixed value sets,
  keyset indexes leading with tenant_id.
- SQL repositories implementing the application ports.

## Acceptance

- `test_rls_coverage` and `test_privileges` pass with the new tables.
- Cross-tenant read and write negative tests.

# 05 — API routes and scopes

Status: ready-for-agent
Blocked by: 04

## What

`/api/v1/sales/...`: inbox list + process, orders list/detail/decide,
quotes list/detail/actions, master data (read-only, mock), process overview
counts. Tenant from the verified access context only. Scopes `sales.read`,
`sales.review`, `sales.approve_quote` granted to seeded roles. Mutations
honour `Idempotency-Key`. Audit event per decision.

## Acceptance

- API tests: authorized path, missing scope refused, other tenant's id
  answers 404.

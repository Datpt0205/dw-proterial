# 24 — The overview aggregates in SQL

Status: ready-for-agent
Blocked by: —
Category: enhancement

Split from ticket 12 on 2026-10-12 (noted under ticket 05).

## What

`OverviewService.overview` and "my work" load every order, quote, message and
event of the workspace (`list_all()` on each) and count in Python. At real
volume (a year of POs) every page view reads the whole history.

## Acceptance

1. Counts by status, waiting times and the work items are computed by SQL
   aggregates in the Sales repository adapter, behind a port the overview
   service declares; the service no longer calls `list_all()`.
2. "My work" pages with keyset pagination; each ORDER BY it pages on has an
   index leading with `tenant_id` (and `workspace_id`), shipped in a new
   migration.
3. Same answers as today: a test runs the old Python computation and the new
   SQL over the demo seed and asserts equal views (keep the old one in the
   test only).
4. RLS still narrows everything: the cross-tenant and cross-workspace
   negative tests pass unchanged.
5. `EXPLAIN` on a seeded table of 50,000 cases shows index use for the
   paged query (recorded in Comments, not asserted).

## Out of scope

- New overview metrics.

## Sources (as of 2026-10-12)

- `dw_sales/application/overview_service.py` (`overview`, the my-work
  query), the Sales persistence adapter, `CLAUDE.md` "Data model rules".

## Comments

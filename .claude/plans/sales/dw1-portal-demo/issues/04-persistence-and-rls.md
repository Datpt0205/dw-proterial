# 04 — Persistence: `sales` schema, RLS, repositories

Status: done (2026-10-05)
Blocked by: 02, 03 (amendments)

## What

- An Alembic revision (generated id) creating the `sales` tables:
    - messages, with their disposition, reason and owner;
    - order_cases;
    - order_revisions (revision no., attachment sha256, `superseded_at`);
    - order_lines (per revision);
    - findings, with the disposition columns;
    - quote_cases;
    - artifacts;
    - source_served;
    - worker_state (the per-workspace pause flag);
    - case_events.

    Every table has tenant_id and workspace_id, RLS ENABLE + FORCE, policies,
    grants, explicit FK ON DELETE indexed on its own side, timestamptz columns,
    a CHECK on every fixed value set, and keyset indexes leading with
    tenant_id.

- SQL repositories implementing the application ports.

## Amendments (2026-10-03)

- **Maker/checker columns (G1, G6).**
    - `order_cases`: `prepared_by/at`, `bravo_so_no`,
      `bravo_recorded_by/at`, `bravo_entry_compared`,
      `cross_checked_by/at`, `confirmed_by/at`, `case_version`, and
      `CONSTRAINT ck_order_cases_checker_not_maker CHECK (cross_checked_by
IS NULL OR (cross_checked_by IS DISTINCT FROM prepared_by AND
cross_checked_by IS DISTINCT FROM bravo_recorded_by))`. The third
      maker kind (a hand-entered value's author) is per line, so the
      handler checks it (spec decision 7).
    - `quote_cases`: `priced_by`, `approved_by`, `approved_version`,
      `document_sha256`, `ycbg_no`, and `CHECK (approved_by IS NULL OR
approved_by <> priced_by)`.
    - Each FK column is indexed.
- **Check basis (G11).** `order_lines.check_basis jsonb NOT NULL` with a
  CHECK on its keys, clean lines included. `order_cases` and `quote_cases`
  carry `rules_version`, `parser_version`, `catalog_as_of` and
  `release_manifest_ref`.
- **Assignee (G22).** `order_cases.assigned_to` and `quote_cases.assigned_to`
  are stamped from `Customer.sales_pic` at creation, never looked up again.
  They are indexed and NULL when no user matches.
- **Events (G14, G26).** Every transition and human action is recorded with:
    - `occurred_at`;
    - `actor_kind CHECK IN ('worker','user')`;
    - `actor_id`, `worker_id`, `worker_version` and `initiated_by`.

    A correction to an extracted value is its own event (field, by,
    `case_version`). Each extracted value carries its value state
    (`CONTEXT.md`, with a CHECK on the set), starting at `dw` until a person
    confirms or types it.

- **No amounts outside the sales tables (G27, decision 8).** Audit and event
  details carry ids, finding codes, transitions, `case_version` and actor
  only. Never a price, a target price or a finding's expected/actual. A test
  scans the details of every event the 02/03 golden runs produce for the
  known price strings.
- **Schema rules (G28).**
    - Decisions and transitions go to `platform.audit_events` through
      `AuditRepositoryPort`, in the same transaction. If `case_events` is
      kept, it is range-partitioned with a DEFAULT partition through
      `platform.ensure_time_partitions`.
    - Policies are named `tenant_isolation_<table>`. They narrow by
      `app.tenant_id` AND `app.workspace_id`, with a two-workspace negative
      test.
    - Unique keys lead with `(tenant_id, workspace_id)`:
        - messages: `(…, message_id)`;
        - PO identity: `(…, customer_code, po_no, revision)`.
    - `updated_at` uses the yielding trigger. Constraint names come from
      `NAMING_CONVENTION`.
    - RESTRICT edges are added to offboarding's `_ORDERED_FIRST`, or
      declared CASCADE. An offboarding integration test exports and purges a
      sales case.
- **Roles (G2, dw_sales ADR 0003).** Insert:
    - the roles `sales_pic`, `sales_head` and `sales_viewer`;
    - the permission sets `sales_price_evidence`, `sales_quote_approver` and
      `sales_export_control`;
    - their scopes, per the spec's actor table, with Vietnamese names in
      `name`;
    - one `platform.sod_rules` row keeping `platform.members.write` and
      `sales.price.read` apart.

    A migration test asserts that no `sales.*` scope sits on `member`,
    `approver`, `manager`, `director`, `executive` or `org_admin`.

## Acceptance

- `test_rls_coverage` and `test_privileges` pass with the new tables.
- Cross-tenant and cross-workspace read and write negative tests.
- An UPDATE setting `cross_checked_by` to `prepared_by`, or to
  `bravo_recorded_by` (and `approved_by = priced_by`), fails on the
  constraint, run as `dw_app`.
- The `platform.sod_rules` row refuses a membership holding both
  `platform.members.write` and `sales.price.read` (`dev|tam.ngo` given
  `sales_pic` is refused).
- The offboarding export/purge test for a sales case passes.

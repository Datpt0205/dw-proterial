"""sales rule drafts swept without a request

Revision ID: e8a1c3e8ed78
Revises: 42868d8c21c5
Create Date: 2026-10-21 04:57:13.252459+00:00

A draft's file was dropped when the worker read it, and old drafts when the
same workspace next asked for one (42868d8c21c5). A draft whose event spent
its outbox retries stayed queued with its bytes for good, and a workspace
that never asked again kept every draft (failure-modes #6). The worker's
`sales_rule_drafts` lane now sweeps each workspace that has something due
(`dw_sales.application.rule_drafts.RuleDraftSweep`), in that workspace's own
row security.

- **`sales.rule_draft_scopes_due(queued_before, requested_before)`**,
  SECURITY DEFINER: the one read that crosses tenants, so the lane knows
  which workspaces to visit: a draft still queued since before
  ``queued_before``, or any draft requested before ``requested_before``.
  Tenant and workspace ids only (`sales.processing_scopes_due` is the same
  shape). The table is bounded by the sweep itself (30 days of uploads), so
  no index is added for this read.

Grants: EXECUTE to `dw_app`, revoked from PUBLIC. Downgrade drops it.
"""

from __future__ import annotations

from alembic import op

revision = "e8a1c3e8ed78"
down_revision = "42868d8c21c5"
branch_labels = None
depends_on = None

_FUNCTION = "sales.rule_draft_scopes_due(timestamp with time zone, timestamp with time zone)"

_SCOPES_DUE = """
    CREATE OR REPLACE FUNCTION sales.rule_draft_scopes_due(
        p_queued_before timestamp with time zone,
        p_requested_before timestamp with time zone
    )
    RETURNS TABLE (tenant_id uuid, workspace_id uuid)
    LANGUAGE sql
    STABLE
    SECURITY DEFINER
    SET search_path = pg_catalog, sales
    AS $$
        SELECT DISTINCT d.tenant_id, d.workspace_id
        FROM sales.rule_drafts d
        WHERE (d.status = 'queued' AND d.requested_at < p_queued_before)
           OR d.requested_at < p_requested_before
        ORDER BY d.tenant_id, d.workspace_id
    $$
"""

_GRANT = f"""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
            GRANT EXECUTE ON FUNCTION {_FUNCTION} TO dw_app;
        END IF;
    END
    $$
"""


def upgrade() -> None:
    op.execute(_SCOPES_DUE)
    op.execute(f"REVOKE ALL ON FUNCTION {_FUNCTION} FROM PUBLIC")
    op.execute(_GRANT)


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {_FUNCTION}")

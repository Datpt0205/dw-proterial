"""purchasing automation lane and its account

Revision ID: 6971b41fcdf6
Revises: 6cbb8581e01e
Create Date: 2026-11-01 10:00:00.000000+00:00

DW2 takes each step on its own as far as the tenant's switches let it (the
worker's `purchasing_automation` lane), under its own service account:

- **Role `purchasing_dw2`** ("DW2 (tài khoản dịch vụ)"): what the lane does
  and nothing else, read and receive requests, send them to their approver,
  draft RFQs and orders. No approve scope, no `approvals.decide`.
- **`purchasing.automation_scopes_due()`**, SECURITY DEFINER: the one read
  that crosses tenants, so the lane knows which workspaces have a case
  waiting on a step it may take (received, approved, suppliers chosen).
  Tenant and workspace ids only; EXECUTE to `dw_app`, revoked from PUBLIC.
- **`ix_cases_tenant_id_workspace_id_status_received_at`** carries the lane's
  read of one workspace's waiting cases, oldest first.
"""

from __future__ import annotations

import json

from alembic import op

revision = "6971b41fcdf6"
down_revision = "6cbb8581e01e"
branch_labels = None
depends_on = None

_SCOPES = (
    "purchasing.request.read",
    "purchasing.request.intake",
    "purchasing.request.submit",
    "purchasing.rfq.prepare",
    "purchasing.po.prepare",
)
_FUNCTION = "purchasing.automation_scopes_due()"


def upgrade() -> None:
    scopes = json.dumps(list(_SCOPES))
    op.execute(
        "INSERT INTO platform.roles (key, name, scopes)"
        f" VALUES ('purchasing_dw2', 'DW2 (tài khoản dịch vụ)', '{scopes}'::jsonb)"
    )
    op.execute(
        "CREATE INDEX ix_cases_tenant_id_workspace_id_status_received_at"
        " ON purchasing.cases (tenant_id, workspace_id, status, received_at, id)"
    )
    op.execute(
        f"""
        CREATE FUNCTION {_FUNCTION}
        RETURNS TABLE (tenant_id uuid, workspace_id uuid)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, purchasing
        AS $$
            SELECT DISTINCT c.tenant_id, c.workspace_id
            FROM purchasing.cases c
            WHERE c.status IN ('received', 'approved', 'supplier_selected')
            ORDER BY c.tenant_id, c.workspace_id
        $$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {_FUNCTION} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_FUNCTION} TO dw_app")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {_FUNCTION}")
    op.execute("DROP INDEX purchasing.ix_cases_tenant_id_workspace_id_status_received_at")
    op.execute("DELETE FROM platform.roles WHERE key = 'purchasing_dw2'")

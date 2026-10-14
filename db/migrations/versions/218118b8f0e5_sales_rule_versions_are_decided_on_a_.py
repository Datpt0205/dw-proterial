"""sales rule versions are decided on a platform approval

Revision ID: 218118b8f0e5
Revises: 0a78ca5e96d3
Create Date: 2026-10-14 08:15:22.558694+00:00

Sales ticket 38 (Đạt, 2026-10-14: a tenant's rule version is decided on the
platform's approval, as a PO layout is since ticket 30, dw_sales ADR 0004).
Proposing a version opens a run-less `sales.rules` approval in the same
transaction; the platform decides it and the worker carries it out.

- **`approval_id`** names that approval, of the same tenant and workspace
  (`fk_rule_versions_approval_requests`, composite, so a version never waits
  on another workspace's approval; CASCADE because an approval leaves only
  with its tenant's purge, which removes both), one version per approval
  (`uq_rule_versions_approval_id`, which also indexes the key).
- **A proposal has its approval** (`ck_rule_versions_proposed_has_approval`).
  Added NOT VALID: a version proposed before this revision has none, is
  decided by nobody, and is proposed again; no deployment holds one. Rows
  decided before keep a null `approval_id`, which the check allows.
"""

from __future__ import annotations

from alembic import op

revision = "218118b8f0e5"
down_revision = "0a78ca5e96d3"
branch_labels = None
depends_on = None

_FK = "fk_rule_versions_approval_requests"
_UNIQUE = "uq_rule_versions_approval_id"
_CHECK = "ck_rule_versions_proposed_has_approval"


def upgrade() -> None:
    op.execute("ALTER TABLE sales.rule_versions ADD COLUMN approval_id uuid")
    op.execute(
        f"""
        ALTER TABLE sales.rule_versions
            ADD CONSTRAINT {_FK}
                FOREIGN KEY (tenant_id, workspace_id, approval_id)
                REFERENCES platform.approval_requests (tenant_id, workspace_id, id)
                ON DELETE CASCADE,
            ADD CONSTRAINT {_UNIQUE} UNIQUE (tenant_id, workspace_id, approval_id)
        """
    )
    op.execute(
        f"ALTER TABLE sales.rule_versions ADD CONSTRAINT {_CHECK}"
        " CHECK (status <> 'proposed' OR approval_id IS NOT NULL) NOT VALID"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE sales.rule_versions"
        f" DROP CONSTRAINT {_CHECK}, DROP CONSTRAINT {_UNIQUE}, DROP CONSTRAINT {_FK},"
        " DROP COLUMN approval_id"
    )

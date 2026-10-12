"""sales head reassigns a case

Revision ID: 934101cde272
Revises: 58184771c541
Create Date: 2026-10-12

Sales ticket 17 (G22). `sales.case.assign` was deferred by `68305ebe4a83`
until a route read it; that route is now
`PUT /api/v1/sales/{orders|quotes}/{case_id}/assignee` (and the list of who
may be given the case, `GET .../assignees`). It is granted to `sales_head`
only: a PIC works the cases given to them, the head decides who that is.

Nothing else changes in the schema: `assigned_to` already exists on both
case tables, the change is the case's next version with its event, and
the audit row names the old and the new assignee by id.
"""

from __future__ import annotations

from alembic import op

revision = "934101cde272"
down_revision = "58184771c541"
branch_labels = None
depends_on = None

_SCOPE = "sales.case.assign"
_ROLE = "sales_head"


def upgrade() -> None:
    op.execute(
        f"UPDATE platform.roles SET scopes = scopes || '[\"{_SCOPE}\"]'::jsonb"
        f" WHERE key = '{_ROLE}' AND NOT scopes ? '{_SCOPE}'"
    )


def downgrade() -> None:
    op.execute(f"UPDATE platform.roles SET scopes = scopes - '{_SCOPE}' WHERE key = '{_ROLE}'")

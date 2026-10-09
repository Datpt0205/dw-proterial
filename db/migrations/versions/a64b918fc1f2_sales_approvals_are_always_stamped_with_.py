"""sales approvals are always stamped with a sales scope

Revision ID: a64b918fc1f2
Revises: a4953eae47c2
Create Date: 2026-10-08 00:00:00.000000+00:00

Every Sales approval type (`sales.quote`, `sales.order.cross_check`) is raised
by `DecisionAsked`, which stamps the scope that decides it (`DECIDE_SCOPES`).
Nothing but that code held the stamp in place: an unstamped `sales.` request
would be shown to every member of the workspace (the platform's
`ApprovalAudience` shows an unstamped request to whoever reads the inbox) and
offered to every holder of `approvals.decide`, which `sales_pic`, `sales_head`
and `sales_quote_approver` hold since `ac31ff0f2087`. The Sales guard refuses
such a decision, but by then the request has been listed.

This makes the stamp the database's rule: a `sales.` approval carries a
`sales.` scope, or the INSERT fails and the run ends `failed` with no approval
row (platform ADR 0004, `docs/adr/0011` here: a malformed stamp does the same).
Which Sales scope decides which type stays `DECIDE_SCOPES`' to say; the guard
refuses a request stamped with any other.

Rows already written are checked by the ADD (not NOT VALID): an existing
unstamped Sales request stops the upgrade instead of staying visible.
"""

from __future__ import annotations

from alembic import op

revision = "a64b918fc1f2"
down_revision = "a4953eae47c2"
branch_labels = None
depends_on = None

_NAME = "ck_approval_requests_sales_stamped"


def upgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE platform.approval_requests
            ADD CONSTRAINT {_NAME} CHECK (
                approval_type NOT LIKE 'sales.%'
                OR required_scope LIKE 'sales.%'
            )
        """
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE platform.approval_requests DROP CONSTRAINT IF EXISTS {_NAME}")

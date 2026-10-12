"""sales approval stamp refuses a null scope

Revision ID: d9e73228e7d7
Revises: 934101cde272
Create Date: 2026-10-12 06:53:59.382146+00:00

`ck_approval_requests_sales_stamped` (`a64b918fc1f2`) read
`approval_type NOT LIKE 'sales.%' OR required_scope LIKE 'sales.%'`. With
`required_scope` NULL on a `sales.` row that is `false OR NULL`, which is
NULL, and a CHECK that evaluates to NULL passes: the one case the constraint
exists for (an unstamped Sales request, shown to every member) got through.
`coalesce` makes a missing stamp read as the empty string, which is no
`sales.` scope, so the row is refused.

Same name, same table (`platform.approval_requests` is a plain table, not
partitioned), dropped and re-added in one statement. Rows already written are
checked by the ADD (not NOT VALID), as `a64b918fc1f2` did: an unstamped Sales
request already in the table stops the upgrade with Postgres's own "violated
by some row" naming this constraint, rather than staying visible. Downgrade
restores `a64b918fc1f2`'s definition; every row the new one admits, the old
one admits too, so it cannot fail.
"""

from __future__ import annotations

from alembic import op

revision = "d9e73228e7d7"
down_revision = "934101cde272"
branch_labels = None
depends_on = None

_TABLE = "platform.approval_requests"
_NAME = "ck_approval_requests_sales_stamped"
_REFUSES_NULL = "approval_type NOT LIKE 'sales.%' OR coalesce(required_scope, '') LIKE 'sales.%'"
_A64B918FC1F2 = "approval_type NOT LIKE 'sales.%' OR required_scope LIKE 'sales.%'"


def _replace(condition: str) -> None:
    op.execute(
        f"ALTER TABLE {_TABLE} DROP CONSTRAINT {_NAME},"
        f" ADD CONSTRAINT {_NAME} CHECK ({condition})"
    )


def upgrade() -> None:
    _replace(_REFUSES_NULL)


def downgrade() -> None:
    _replace(_A64B918FC1F2)

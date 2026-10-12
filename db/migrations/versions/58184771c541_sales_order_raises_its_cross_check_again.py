"""sales order raises its cross-check again

Revision ID: 58184771c541
Revises: a64b918fc1f2
Create Date: 2026-10-12 05:33:10.601238+00:00

Sales ticket 14. A cross-check decision is checked by the Sales guard before
the platform records it, and applied by DW1's run when it resumes. A case
version bumped in between (a finding acknowledged, a PC date recorded) makes
the apply refuse: the approval stays decided, the run fails, and the order
waited at `uploaded_to_bravo` with nothing left to decide. Two things make
that recoverable:

- **`order_cases.unapplied_decision`**: the decision recorded and not
  applied, said on the order while it still awaits its cross-check (the
  domain clears it when the cross-check is raised again or the case moves).
  Ids, the outcome, a version and a reason code only: the CHECK names every
  key the domain's `UnappliedDecision` writes and refuses any other, so a
  comment or an amount has no field to travel in (spec decision 8), and
  holds it to `uploaded_to_bravo` as the domain does.
- **`sales.order.resend_cross_check`**, granted to `sales_head` only. The
  route that reads it is `POST /orders/{id}/resend-cross-check` ("Gửi kiểm
  chéo lại"): whoever recorded the order's Bravo entry raises its
  cross-check again with `sales.order.prepare`; anyone else needs this scope.

The column is added to a table every Sales role already reads and writes, so
its grants and its RLS policy are the table's; nothing else changes.
"""

from __future__ import annotations

from alembic import op

revision = "58184771c541"
down_revision = "a64b918fc1f2"
branch_labels = None
depends_on = None

_CHECK = "ck_order_cases_unapplied_decision"
# `dw_sales.domain.orders.UnappliedDecision`'s fields: `test_sales_schema.py`
# compares the two, so they disagree loudly rather than quietly.
_KEYS = (
    "approval_id",
    "run_id",
    "decided_by",
    "approved",
    "decided_on",
    "reason_code",
    "at",
)
_SCOPE = "sales.order.resend_cross_check"
_ROLE = "sales_head"


def upgrade() -> None:
    op.execute("ALTER TABLE sales.order_cases ADD COLUMN unapplied_decision jsonb")
    keys = ", ".join(f"'{key}'" for key in _KEYS)
    op.execute(
        f"""
        ALTER TABLE sales.order_cases ADD CONSTRAINT {_CHECK} CHECK (
            unapplied_decision IS NULL
            OR (
                status = 'uploaded_to_bravo'
                AND jsonb_typeof(unapplied_decision) = 'object'
                -- `?` first: a missing key makes the comparisons NULL, and a
                -- CHECK that evaluates to NULL passes.
                AND unapplied_decision ? 'run_id'
                AND unapplied_decision ? 'reason_code'
                AND (unapplied_decision ->> 'reason_code') ~ '^[a-z_]{{1,40}}$'
                AND (unapplied_decision - ARRAY[{keys}]::text[]) = '{{}}'::jsonb
            )
        )
        """
    )
    op.execute(
        f"UPDATE platform.roles SET scopes = scopes || '[\"{_SCOPE}\"]'::jsonb"
        f" WHERE key = '{_ROLE}' AND NOT scopes ? '{_SCOPE}'"
    )


def downgrade() -> None:
    op.execute(f"UPDATE platform.roles SET scopes = scopes - '{_SCOPE}' WHERE key = '{_ROLE}'")
    op.execute(f"ALTER TABLE sales.order_cases DROP CONSTRAINT IF EXISTS {_CHECK}")
    op.execute("ALTER TABLE sales.order_cases DROP COLUMN IF EXISTS unapplied_decision")

"""purchasing orders followed after drafting

Revision ID: 13bff35b038b
Revises: 2ba8d9cc436c
Create Date: 2026-11-04 02:42:23.470006+00:00

DW2, DW02 function 5: each drafted order followed by its `po_ref` (Bravo's
number, the supplier's confirmation, what arrived), held in the case's
`body` as `tracking` (`dw_purchasing.domain.tracking`):

- **`ck_cases_tracking`**: `tracking` is a list, and only a case with orders
  drafted (`po_drafted`) follows any. A row written before it has no key,
  which reads as the empty list.

No grant changes: following an order is the buyer's `purchasing.po.prepare`.
"""

from __future__ import annotations

from alembic import op

revision = "13bff35b038b"
down_revision = "2ba8d9cc436c"
branch_labels = None
depends_on = None

_TRACKING = "coalesce(body -> 'tracking', '[]'::jsonb)"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE purchasing.cases ADD CONSTRAINT ck_cases_tracking CHECK ("
        f" jsonb_typeof({_TRACKING}) = 'array'"
        f" AND (status = 'po_drafted' OR {_TRACKING} = '[]'::jsonb))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE purchasing.cases DROP CONSTRAINT ck_cases_tracking")

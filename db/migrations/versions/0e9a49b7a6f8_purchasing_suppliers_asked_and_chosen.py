"""purchasing suppliers asked and chosen

Revision ID: 0e9a49b7a6f8
Revises: 911fdfb96d5e
Create Date: 2026-11-01 18:00:00.000000+00:00

DW2, DW02 function 3: RFQs drafted to suppliers, offers recorded, a supplier
chosen per line (`dw_purchasing.application.sourcing`). Everything lives in the
case's `body`, so the schema changes only in what a status may be and what a
status must hold:

- **`ck_cases_status`** admits `rfq_drafted` and `supplier_selected`.
- **`ck_cases_sent`** is rewritten: a decision is held by `approved`,
  `rejected` and the two sourcing states (an approved request being sourced
  keeps its approval's decision), and only by them.
- **`ck_cases_sourced`**: the sourcing states hold their RFQ round, and
  `supplier_selected` its selection; no other state holds either. An absent
  key reads as absent, not as NULL, which a CHECK would let through.
- **Scope**: `purchasing.rfq.prepare` for `purchasing_buyer`.
"""

from __future__ import annotations

from alembic import op

revision = "0e9a49b7a6f8"
down_revision = "911fdfb96d5e"
branch_labels = None
depends_on = None

# `dw_purchasing.domain.cases.CaseStatus`, held to it by test.
_STATUSES = (
    "('received', 'awaiting_approval', 'approved', 'rejected', 'rfq_drafted', 'supplier_selected')"
)
_STATUSES_BEFORE = "('received', 'awaiting_approval', 'approved', 'rejected')"
_DECIDED = "('approved', 'rejected', 'rfq_drafted', 'supplier_selected')"
_DECIDED_BEFORE = "('approved', 'rejected')"
_SCOPE = "purchasing.rfq.prepare"


def _sent(decided: str) -> str:
    return (
        "ALTER TABLE purchasing.cases ADD CONSTRAINT ck_cases_sent CHECK ("
        " (status = 'received') = (approval_id IS NULL)"
        f" AND (status IN {decided}) = (body ? 'decision'"
        " AND jsonb_typeof(body -> 'decision') = 'object'))"
    )


def upgrade() -> None:
    op.execute("ALTER TABLE purchasing.cases DROP CONSTRAINT ck_cases_status")
    op.execute(
        f"ALTER TABLE purchasing.cases ADD CONSTRAINT ck_cases_status CHECK (status IN {_STATUSES})"
    )
    op.execute("ALTER TABLE purchasing.cases DROP CONSTRAINT ck_cases_sent")
    op.execute(_sent(_DECIDED))
    op.execute(
        "ALTER TABLE purchasing.cases ADD CONSTRAINT ck_cases_sourced CHECK ("
        " (status IN ('rfq_drafted', 'supplier_selected'))"
        " = (coalesce(jsonb_typeof(body -> 'rfq'), 'absent') = 'object')"
        " AND (status = 'supplier_selected')"
        " = (coalesce(jsonb_typeof(body -> 'selection'), 'absent') = 'object'))"
    )
    op.execute(
        "UPDATE platform.roles SET scopes = scopes || "
        f"'[\"{_SCOPE}\"]'::jsonb WHERE key = 'purchasing_buyer'"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE platform.roles SET scopes = scopes - '{_SCOPE}' WHERE key = 'purchasing_buyer'"
    )
    op.execute("ALTER TABLE purchasing.cases DROP CONSTRAINT ck_cases_sourced")
    op.execute("ALTER TABLE purchasing.cases DROP CONSTRAINT ck_cases_sent")
    op.execute(_sent(_DECIDED_BEFORE))
    op.execute("ALTER TABLE purchasing.cases DROP CONSTRAINT ck_cases_status")
    op.execute(
        "ALTER TABLE purchasing.cases ADD CONSTRAINT ck_cases_status"
        f" CHECK (status IN {_STATUSES_BEFORE})"
    )

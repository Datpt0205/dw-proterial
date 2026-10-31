"""purchasing orders drafted for bravo

Revision ID: 126b205278ad
Revises: 0e9a49b7a6f8
Create Date: 2026-11-01 21:00:00.000000+00:00

DW2, DW02 function 4: one draft purchase order per chosen supplier and the
file Bravo imports them from (`dw_purchasing.application.orders`). The orders
and the layout their file is drawn with live in the case's `body`:

- **`ck_cases_status`** admits `po_drafted`.
- **`ck_cases_sent`**, **`ck_cases_sourced`** are rewritten so `po_drafted`
  holds what the states before it hold: the approval's decision, the RFQ
  round, the selection.
- **`ck_cases_po`**: `po_drafted` holds its orders, and no other state does.
- **Scope**: `purchasing.po.prepare` for `purchasing_buyer`.
"""

from __future__ import annotations

from alembic import op

revision = "126b205278ad"
down_revision = "0e9a49b7a6f8"
branch_labels = None
depends_on = None

# `dw_purchasing.domain.cases.CaseStatus`, held to it by test.
_STATUSES = (
    "('received', 'awaiting_approval', 'approved', 'rejected', 'rfq_drafted',"
    " 'supplier_selected', 'po_drafted')"
)
_STATUSES_BEFORE = (
    "('received', 'awaiting_approval', 'approved', 'rejected', 'rfq_drafted', 'supplier_selected')"
)
_SCOPE = "purchasing.po.prepare"


def _object(key: str) -> str:
    return f"(coalesce(jsonb_typeof(body -> '{key}'), 'absent') = 'object')"


def _sent(decided: str) -> str:
    return (
        "ALTER TABLE purchasing.cases ADD CONSTRAINT ck_cases_sent CHECK ("
        " (status = 'received') = (approval_id IS NULL)"
        f" AND (status IN {decided}) = {_object('decision')})"
    )


def _sourced(sourcing: str, chosen: str) -> str:
    return (
        "ALTER TABLE purchasing.cases ADD CONSTRAINT ck_cases_sourced CHECK ("
        f" (status IN {sourcing}) = {_object('rfq')}"
        f" AND (status IN {chosen}) = {_object('selection')})"
    )


def _replace(statuses: str, decided: str, sourcing: str, chosen: str) -> None:
    for name in ("ck_cases_status", "ck_cases_sent", "ck_cases_sourced"):
        op.execute(f"ALTER TABLE purchasing.cases DROP CONSTRAINT {name}")
    op.execute(
        f"ALTER TABLE purchasing.cases ADD CONSTRAINT ck_cases_status CHECK (status IN {statuses})"
    )
    op.execute(_sent(decided))
    op.execute(_sourced(sourcing, chosen))


def upgrade() -> None:
    _replace(
        _STATUSES,
        "('approved', 'rejected', 'rfq_drafted', 'supplier_selected', 'po_drafted')",
        "('rfq_drafted', 'supplier_selected', 'po_drafted')",
        "('supplier_selected', 'po_drafted')",
    )
    op.execute(
        "ALTER TABLE purchasing.cases ADD CONSTRAINT ck_cases_po CHECK ("
        f" (status = 'po_drafted') = {_object('po')})"
    )
    op.execute(
        "UPDATE platform.roles SET scopes = scopes || "
        f"'[\"{_SCOPE}\"]'::jsonb WHERE key = 'purchasing_buyer'"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE platform.roles SET scopes = scopes - '{_SCOPE}' WHERE key = 'purchasing_buyer'"
    )
    op.execute("ALTER TABLE purchasing.cases DROP CONSTRAINT ck_cases_po")
    _replace(
        _STATUSES_BEFORE,
        "('approved', 'rejected', 'rfq_drafted', 'supplier_selected')",
        "('rfq_drafted', 'supplier_selected')",
        "('supplier_selected')",
    )

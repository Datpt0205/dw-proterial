"""purchasing cases delivered and late lines told

Revision ID: e13dd31820b5
Revises: ad62389cc25d
Create Date: 2026-11-04 10:30:00.000000+00:00

DW02 function 5b's rest (`dw_purchasing.application.follow_up`,
`automation_lane`):

- **`delivered`** (Đã nhận đủ hàng): the receipt that completes every line
  of every order moves the case there. `ck_cases_status` admits it, and
  `ck_cases_sent`, `ck_cases_sourced`, `ck_cases_po` and `ck_cases_tracking`
  give it what a case with orders holds (the decision, the RFQ round, the
  choice, the orders, their tracking).
- **`purchasing.automation_scopes_due()`** also returns a workspace with
  orders still followed (`po_drafted`): the lane tells their late lines.
  Still ids only, SECURITY DEFINER, EXECUTE to `dw_app` alone.

Held to the domain's values by `test_purchasing_store_db.py`. The downgrade
moves a delivered case back to `po_drafted`, which holds the same body.
"""

from __future__ import annotations

from alembic import op

revision = "e13dd31820b5"
down_revision = "ad62389cc25d"
branch_labels = None
depends_on = None

_BEFORE = (
    "'received', 'awaiting_approval', 'approved', 'rejected', 'rfq_drafted',"
    " 'awaiting_reapproval', 'supplier_selected', 'po_drafted'"
)
_DECIDED = (
    "'approved', 'rejected', 'rfq_drafted', 'awaiting_reapproval', 'supplier_selected',"
    " 'po_drafted'"
)
_SOURCING = "'rfq_drafted', 'awaiting_reapproval', 'supplier_selected', 'po_drafted'"
_CHOSEN = "'supplier_selected', 'po_drafted'"
_ORDERED = "'po_drafted'"
_TRACKING = "coalesce(body -> 'tracking', '[]'::jsonb)"
_FUNCTION = "purchasing.automation_scopes_due()"


def _object(key: str) -> str:
    return f"(coalesce(jsonb_typeof(body -> '{key}'), 'absent') = 'object')"


def _checks(extra: str) -> None:
    """The case CHECKs over the statuses before, plus ``extra`` ("" or
    ", 'delivered'") wherever a case holds its orders."""
    for name in (
        "ck_cases_status",
        "ck_cases_sent",
        "ck_cases_sourced",
        "ck_cases_po",
        "ck_cases_tracking",
    ):
        op.execute(f"ALTER TABLE purchasing.cases DROP CONSTRAINT {name}")
    op.execute(
        "ALTER TABLE purchasing.cases ADD CONSTRAINT ck_cases_status"
        f" CHECK (status IN ({_BEFORE}{extra}))"
    )
    op.execute(
        "ALTER TABLE purchasing.cases ADD CONSTRAINT ck_cases_sent CHECK ("
        " (status = 'received') = (approval_id IS NULL)"
        f" AND (status IN ({_DECIDED}{extra})) = {_object('decision')})"
    )
    op.execute(
        "ALTER TABLE purchasing.cases ADD CONSTRAINT ck_cases_sourced CHECK ("
        f" (status IN ({_SOURCING}{extra})) = {_object('rfq')}"
        f" AND (status IN ({_CHOSEN}{extra})) = {_object('selection')})"
    )
    op.execute(
        "ALTER TABLE purchasing.cases ADD CONSTRAINT ck_cases_po CHECK ("
        f" (status IN ({_ORDERED}{extra})) = {_object('po')})"
    )
    op.execute(
        "ALTER TABLE purchasing.cases ADD CONSTRAINT ck_cases_tracking CHECK ("
        f" jsonb_typeof({_TRACKING}) = 'array'"
        f" AND (status IN ({_ORDERED}{extra}) OR {_TRACKING} = '[]'::jsonb))"
    )


def _due(statuses: str) -> None:
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_FUNCTION}
        RETURNS TABLE (tenant_id uuid, workspace_id uuid)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, purchasing
        AS $$
            SELECT DISTINCT c.tenant_id, c.workspace_id
            FROM purchasing.cases c
            WHERE c.status IN ({statuses})
            ORDER BY c.tenant_id, c.workspace_id
        $$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {_FUNCTION} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_FUNCTION} TO dw_app")


def upgrade() -> None:
    _checks(", 'delivered'")
    _due("'received', 'approved', 'supplier_selected', 'po_drafted'")


def downgrade() -> None:
    _due("'received', 'approved', 'supplier_selected'")
    op.execute("UPDATE purchasing.cases SET status = 'po_drafted' WHERE status = 'delivered'")
    _checks("")

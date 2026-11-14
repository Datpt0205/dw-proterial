"""sales update loop on an order in Bravo

Revision ID: 0d1d0e4eb203
Revises: 91f83937dbf1
Create Date: 2026-11-14 21:32:16.546634+00:00

Sales ticket 29 (dw_sales ADR 0010 decision 3): a customer's change on an
order already in Bravo goes to PC and back to the customer before the order
changes, then through the Bravo update the PIC approves.

- **`sales.order_cases.update_loop`**: the loop (`UpdateLoop`: the change
  request it comes from, its step, since when, the changed lines with PC's
  answer, code's verdict on it, the approved Bravo update file by id and
  hash), an object, NULL while the order has none. The `sales_followups`
  lane reads its `since` as the start of a wait on PC (`waiting_pc`) or on
  the customer (`waiting_customer`), by its step; the domain moves `since`
  with every step and drops the loop when it ends, so no reminder outlives
  the answer.
- **`ck_order_cases_update_loop`**: an object whose step is one of the five
  the domain names, and only on an order in Bravo (`confirmed` while it talks
  with PC and the customer, `change_review` to `cross_checked` once the
  customer accepted). A scalar, an unknown step or a loop on an order not in
  Bravo is refused (failure-modes #7).

The column belongs to a table that already holds its grants, RLS policy and
FORCE: nothing about who may read or write it changes.

Downgrade drops the column, and with it any loop in progress.
"""

from __future__ import annotations

from alembic import op

revision = "0d1d0e4eb203"
down_revision = "91f83937dbf1"
branch_labels = None
depends_on = None

_STEPS = ("ask_pc", "waiting_pc", "answer_customer", "waiting_customer", "bravo_update")
_STATUSES = ("confirmed", "change_review", "uploaded_to_bravo", "cross_checked")


def _in(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    op.execute("ALTER TABLE sales.order_cases ADD COLUMN update_loop jsonb")
    op.execute(
        "ALTER TABLE sales.order_cases ADD CONSTRAINT ck_order_cases_update_loop CHECK ("
        " update_loop IS NULL OR ("
        " jsonb_typeof(update_loop) = 'object'"
        f" AND update_loop ->> 'step' IN {_in(_STEPS)}"
        f" AND status IN {_in(_STATUSES)}))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE sales.order_cases DROP COLUMN update_loop")

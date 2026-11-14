"""sales PC asked and PC's answer per line

Revision ID: 91f83937dbf1
Revises: c7d0730fcccd
Create Date: 2026-11-14 20:00:21.802733+00:00

Sales ticket 07: Sales asks PC for an order's delivery dates and DW1 reminds
the PIC while PC has not answered; PC's answer, which may split a line over
several dates, is recorded line by line by a person.

- **`sales.order_cases.pc_request`**: the open request to PC (`PcRequest`: the
  lines asked, who recorded asking and when), an object, NULL while the case
  waits on nobody at PC. The `sales_followups` lane reads its `at` as the
  start of the wait (`waiting_pc`); the domain clears it once every line
  asked has PC's answer, so no reminder outlives the answer.
- **`sales.order_lines.pc_answer`**: PC's answer for the line (`PcAnswer`:
  each delivery's quantity, the date PC confirmed first and the current one,
  who recorded it and when), an object, NULL until recorded.
- **`ck_followup_deliveries_followup`** takes `waiting_pc`
  (`test_sales_schema.py` holds the list equal to `Followup`).

Both columns belong to tables that already hold their grants, RLS policy and
FORCE: nothing about who may read or write them changes. A CHECK holds each
to an object, so an array or a scalar written by mistake is refused.

Downgrade deletes the `waiting_pc` records, restores the check, and drops
both columns.
"""

from __future__ import annotations

from alembic import op

revision = "91f83937dbf1"
down_revision = "c7d0730fcccd"
branch_labels = None
depends_on = None

_FOLLOWUPS_BEFORE = (
    "order_unconfirmed",
    "quote_waiting_design",
    "quote_deadline",
    "waiting_customer",
    "morning_brief",
    "your_turn",
)
_FOLLOWUPS = (*_FOLLOWUPS_BEFORE, "waiting_pc")

_UP = (
    "ALTER TABLE sales.order_cases ADD COLUMN pc_request jsonb",
    "ALTER TABLE sales.order_cases ADD CONSTRAINT ck_order_cases_pc_request"
    " CHECK (pc_request IS NULL OR jsonb_typeof(pc_request) = 'object')",
    "ALTER TABLE sales.order_lines ADD COLUMN pc_answer jsonb",
    "ALTER TABLE sales.order_lines ADD CONSTRAINT ck_order_lines_pc_answer"
    " CHECK (pc_answer IS NULL OR jsonb_typeof(pc_answer) = 'object')",
)


def _in(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"


def _followups(values: tuple[str, ...]) -> None:
    op.execute(
        f"""
        ALTER TABLE sales.followup_deliveries
            DROP CONSTRAINT ck_followup_deliveries_followup,
            ADD CONSTRAINT ck_followup_deliveries_followup CHECK (followup IN {_in(values)})
        """
    )


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)
    _followups(_FOLLOWUPS)


def downgrade() -> None:
    op.execute("DELETE FROM sales.followup_deliveries WHERE followup = 'waiting_pc'")
    _followups(_FOLLOWUPS_BEFORE)
    op.execute("ALTER TABLE sales.order_lines DROP COLUMN pc_answer")
    op.execute("ALTER TABLE sales.order_cases DROP COLUMN pc_request")

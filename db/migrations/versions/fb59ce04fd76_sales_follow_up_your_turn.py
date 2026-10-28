"""sales follow-up your turn

Revision ID: fb59ce04fd76
Revises: 1a21c3a78c93
Create Date: 2026-10-28

A case DW1 has done its part on and that now waits on a person is told to
them at once (`sales_followups@1.1.0`, `Followup.YOUR_TURN`, 2026-10-28: "nếu
dừng thì có noti cho họ thấy chưa"). Its delivery is recorded like every
follow-up's, once per (case, status entered):

- **`ck_followup_deliveries_followup`** takes `your_turn`, and
  **`ck_followup_deliveries_stage`** takes `notify` (`test_followups.py` and
  `test_sales_schema.py` hold the lists equal to `Followup` and `Stage`).
"""

from __future__ import annotations

from alembic import op

revision = "fb59ce04fd76"
down_revision = "1a21c3a78c93"
branch_labels = None
depends_on = None

_FOLLOWUPS_BEFORE = (
    "order_unconfirmed",
    "quote_waiting_design",
    "quote_deadline",
    "waiting_customer",
    "morning_brief",
)
_STAGES_BEFORE = ("remind", "escalate", "warn", "brief")
_FOLLOWUPS = (*_FOLLOWUPS_BEFORE, "your_turn")
_STAGES = (*_STAGES_BEFORE, "notify")


def _in(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"


def _checks(followups: tuple[str, ...], stages: tuple[str, ...]) -> None:
    op.execute(
        f"""
        ALTER TABLE sales.followup_deliveries
            DROP CONSTRAINT ck_followup_deliveries_followup,
            ADD CONSTRAINT ck_followup_deliveries_followup CHECK (followup IN {_in(followups)}),
            DROP CONSTRAINT ck_followup_deliveries_stage,
            ADD CONSTRAINT ck_followup_deliveries_stage CHECK (stage IN {_in(stages)})
        """
    )


def upgrade() -> None:
    _checks(_FOLLOWUPS, _STAGES)


def downgrade() -> None:
    op.execute("DELETE FROM sales.followup_deliveries WHERE followup = 'your_turn'")
    _checks(_FOLLOWUPS_BEFORE, _STAGES_BEFORE)

"""sales order lines confirmed per schedule

Revision ID: b2afb906fbf2
Revises: 13c687788955
Create Date: 2026-10-14 02:49:46.056904+00:00

Sales ticket 35. A PO line split over several delivery schedules (ticket 21)
is confirmed per schedule: Sales confirms one date for each, so the customer
is no longer told the whole quantity on one day.

- **`sales.order_lines.confirmed_delivery_dates date[]`** replaces
  `confirmed_delivery_date date`: one date per delivery, in the order of the
  line's schedules (one for a line delivered once), NULL until the order is
  confirmed. One column, so the line's date and its schedules' dates cannot
  disagree. `ck_order_lines_confirmed_delivery_dates`: a non-empty,
  one-dimensional list with no NULL in it (an empty array would satisfy a
  bare NOT NULL, failure-modes #7). How many dates a line needs is the
  domain's (`OrderLine.deliveries`), which refuses any other count.
- **Backfill.** A line confirmed before this revision holds its one date for
  each delivery: a split line was confirmed, and told to the customer, as
  every schedule on that day, so that is what it records. The touch trigger
  is held for the backfill: moving a value to its new column is not a change
  to the line, and `updated_at` keeps its time.

Downgrade restores the single date, and refuses (Postgres raises) while a
line holds different dates for its schedules: keeping only the first would
silently drop a date confirmed to a customer.
"""

from __future__ import annotations

from alembic import op

revision = "b2afb906fbf2"
down_revision = "13c687788955"
branch_labels = None
depends_on = None

_DATES = "confirmed_delivery_dates"


def upgrade() -> None:
    op.execute(f"ALTER TABLE sales.order_lines ADD COLUMN {_DATES} date[]")
    op.execute("ALTER TABLE sales.order_lines DISABLE TRIGGER touch_updated_at")
    op.execute(
        f"""
        UPDATE sales.order_lines
        SET {_DATES} = array_fill(
            confirmed_delivery_date,
            ARRAY[GREATEST(1, COALESCE(jsonb_array_length(po_line -> 'printed_schedules'), 0))]
        )
        WHERE confirmed_delivery_date IS NOT NULL
        """
    )
    op.execute("ALTER TABLE sales.order_lines ENABLE TRIGGER touch_updated_at")
    op.execute(
        f"""
        ALTER TABLE sales.order_lines ADD CONSTRAINT ck_order_lines_{_DATES} CHECK (
            {_DATES} IS NULL OR (
                cardinality({_DATES}) >= 1
                AND array_ndims({_DATES}) = 1
                AND array_position({_DATES}, NULL) IS NULL
            )
        )
        """
    )
    op.execute("ALTER TABLE sales.order_lines DROP COLUMN confirmed_delivery_date")


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM sales.order_lines AS line
                WHERE (
                    SELECT count(DISTINCT day) FROM unnest(line.{_DATES}) AS day
                ) > 1
            ) THEN
                RAISE EXCEPTION 'a line is confirmed with different dates per schedule';
            END IF;
        END
        $$
        """
    )
    op.execute("ALTER TABLE sales.order_lines ADD COLUMN confirmed_delivery_date date")
    op.execute("ALTER TABLE sales.order_lines DISABLE TRIGGER touch_updated_at")
    op.execute(
        f"UPDATE sales.order_lines SET confirmed_delivery_date = {_DATES}[1]"
        f" WHERE {_DATES} IS NOT NULL"
    )
    op.execute("ALTER TABLE sales.order_lines ENABLE TRIGGER touch_updated_at")
    op.execute(f"ALTER TABLE sales.order_lines DROP COLUMN {_DATES}")

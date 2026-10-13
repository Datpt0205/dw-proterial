"""sales open work indexes and received at

Revision ID: 6d0252a87a6c
Revises: 63242ec52c4b
Create Date: 2026-10-13 12:48:19.919763+00:00

Sales ticket 24: the work list ("my work") is a keyset page instead of every
case of the workspace, ordered by (due date, received, id). Each ORDER BY it
pages on is carried by an index leading with the columns RLS supplies
(`tenant_id`, `workspace_id`), so page 50 costs what page 1 costs:

- **`sales.order_cases.received_at`**: the current revision's, kept on the
  case (the repository writes it on every save from the case it saves;
  `order_revisions` stays its record). Backfilled from the current revision.
- **`sales.quote_cases.received_at`**: the request's, written the same way,
  backfilled from `body`. A plain column, not generated: a text-to-timestamptz
  cast is not immutable.
- **`sales.quote_cases.quote_due`**: the request's due date as ISO text,
  GENERATED from `body` like `ycbg_no` (so it cannot disagree with it); ISO
  dates sort as text the way they sort as dates.
- **`ix_order_cases_open_work`**, **`ix_quote_cases_open_work`**: partial,
  on the cases that are not settled (an order confirmed or closed, a
  quotation recorded in the master list or declined), which no work list
  step is on. The history of settled cases is then outside the index and a
  page never walks it. `dw_sales.adapters.persistence.overview` writes the
  same predicate into its statements, as literals, so the planner can match
  it in a generic plan as well as a custom one.
- **`ix_messages_routed_work`**: partial, on messages routed to Sales, by
  when they were processed.

The backfills keep `updated_at`: `touch_updated_at` is disabled on the two
case tables for the UPDATE only (an UPDATE stating the old value would not be
kept, `0004`).
"""

from __future__ import annotations

from alembic import op

revision = "6d0252a87a6c"
down_revision = "63242ec52c4b"
branch_labels = None
depends_on = None

_SETTLED_ORDERS = "('confirmed', 'closed')"
_SETTLED_QUOTES = "('master_list_recorded', 'declined')"
_NO_DUE = "'9999-12-31'"


def upgrade() -> None:
    op.execute("ALTER TABLE sales.order_cases ADD COLUMN received_at timestamptz")
    op.execute("ALTER TABLE sales.order_cases DISABLE TRIGGER touch_updated_at")
    op.execute(
        "UPDATE sales.order_cases c SET received_at = r.received_at"
        " FROM sales.order_revisions r"
        " WHERE r.case_id = c.id AND r.superseded_at IS NULL"
    )
    op.execute("ALTER TABLE sales.order_cases ENABLE TRIGGER touch_updated_at")
    op.execute("ALTER TABLE sales.order_cases ALTER COLUMN received_at SET NOT NULL")

    op.execute("ALTER TABLE sales.quote_cases ADD COLUMN received_at timestamptz")
    op.execute("ALTER TABLE sales.quote_cases DISABLE TRIGGER touch_updated_at")
    op.execute(
        "UPDATE sales.quote_cases"
        " SET received_at = (body #>> '{request,received_at}')::timestamptz"
    )
    op.execute("ALTER TABLE sales.quote_cases ENABLE TRIGGER touch_updated_at")
    op.execute("ALTER TABLE sales.quote_cases ALTER COLUMN received_at SET NOT NULL")
    op.execute(
        "ALTER TABLE sales.quote_cases ADD COLUMN quote_due text"
        " GENERATED ALWAYS AS (body #>> '{request,document,quote_due,value}') STORED"
    )

    op.execute(
        "CREATE INDEX ix_order_cases_open_work ON sales.order_cases"
        " (tenant_id, workspace_id, received_at, id)"
        f" WHERE status NOT IN {_SETTLED_ORDERS}"
    )
    op.execute(
        "CREATE INDEX ix_quote_cases_open_work ON sales.quote_cases"
        f" (tenant_id, workspace_id, (coalesce(quote_due, {_NO_DUE})), received_at, id)"
        f" WHERE status NOT IN {_SETTLED_QUOTES}"
    )
    op.execute(
        "CREATE INDEX ix_messages_routed_work ON sales.messages"
        " (tenant_id, workspace_id, processed_at, id)"
        " WHERE disposition = 'routed_to_sales'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX sales.ix_messages_routed_work")
    op.execute("DROP INDEX sales.ix_quote_cases_open_work")
    op.execute("DROP INDEX sales.ix_order_cases_open_work")
    op.execute("ALTER TABLE sales.quote_cases DROP COLUMN quote_due")
    op.execute("ALTER TABLE sales.quote_cases DROP COLUMN received_at")
    op.execute("ALTER TABLE sales.order_cases DROP COLUMN received_at")

"""sales order cases carry their due date

Revision ID: 2dd12f5b9c88
Revises: 218118b8f0e5
Create Date: 2026-10-15 03:03:36.773369+00:00

The work list (G22, ticket 08) sorts by due date, then by when a case came
in. A quotation's due date is `quote_cases.quote_due` (`6d0252a87a6c`); an
order had none, so every order sorted last. An order is due on the requested
date of a line whose lead time is short (`requested_date_short_lt`), the
earliest when several are (`OrderCase.due`).

- **`sales.order_cases.due`**: that date as ISO text (sorts as the dates do,
  like `quote_due`), NULL when no line is short. Written by the repository on
  every save from the case it saves, as `received_at` is: the lines and
  findings live in other tables, so it cannot be GENERATED. A CHECK holds it
  to the ISO shape, since a value in another shape would sort wrongly and
  quietly.
- **`ix_order_cases_open_work`** is rebuilt to carry the new order,
  `(tenant_id, workspace_id, coalesce(due, '9999-12-31'), received_at, id)`,
  on the same predicate: the statement writes the same expression, so a page
  still reads the index in order and sorts nothing but the merge.
- **Backfill**: the current revision's short lines, each at its requested
  date as entered (a Sales correction of `requested_date` over the value as
  read; a split line's requested date is its first schedule's). With
  `touch_updated_at` disabled for the UPDATE so `updated_at` keeps its value,
  as `6d0252a87a6c` did.
"""

from __future__ import annotations

from alembic import op

revision = "2dd12f5b9c88"
down_revision = "218118b8f0e5"
branch_labels = None
depends_on = None

_SETTLED_ORDERS = "('confirmed', 'closed')"
_NO_DUE = "'9999-12-31'"
_CHECK = "ck_order_cases_due_iso_date"


def upgrade() -> None:
    op.execute("ALTER TABLE sales.order_cases ADD COLUMN due text")
    op.execute(
        f"ALTER TABLE sales.order_cases ADD CONSTRAINT {_CHECK}"
        r" CHECK (due ~ '^\d{4}-\d{2}-\d{2}$')"
    )
    op.execute("ALTER TABLE sales.order_cases DISABLE TRIGGER touch_updated_at")
    op.execute(
        """
        UPDATE sales.order_cases c SET due = d.due
        FROM (
            SELECT r.case_id,
                   to_char(
                       min(coalesce(fix.value, l.po_line ->> 'requested_date')::date),
                       'YYYY-MM-DD'
                   ) AS due
              FROM sales.order_revisions r
              JOIN sales.order_lines l ON l.revision_id = r.id
              JOIN sales.order_findings f
                ON f.revision_id = r.id
               AND f.line_no = l.line_no
               AND f.code = 'requested_date_short_lt'
              LEFT JOIN LATERAL (
                   SELECT x ->> 'value' AS value
                     FROM jsonb_array_elements(l.corrections) x
                    WHERE x ->> 'field' = 'requested_date'
              ) fix ON true
             WHERE r.superseded_at IS NULL
             GROUP BY r.case_id
        ) d
        WHERE d.case_id = c.id AND d.due IS NOT NULL
        """
    )
    op.execute("ALTER TABLE sales.order_cases ENABLE TRIGGER touch_updated_at")
    op.execute("DROP INDEX sales.ix_order_cases_open_work")
    op.execute(
        "CREATE INDEX ix_order_cases_open_work ON sales.order_cases"
        f" (tenant_id, workspace_id, (coalesce(due, {_NO_DUE})), received_at, id)"
        f" WHERE status NOT IN {_SETTLED_ORDERS}"
    )


def downgrade() -> None:
    op.execute("DROP INDEX sales.ix_order_cases_open_work")
    op.execute(
        "CREATE INDEX ix_order_cases_open_work ON sales.order_cases"
        " (tenant_id, workspace_id, received_at, id)"
        f" WHERE status NOT IN {_SETTLED_ORDERS}"
    )
    op.execute(f"ALTER TABLE sales.order_cases DROP CONSTRAINT {_CHECK}")
    op.execute("ALTER TABLE sales.order_cases DROP COLUMN due")

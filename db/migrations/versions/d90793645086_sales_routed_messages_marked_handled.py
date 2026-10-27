"""sales routed messages marked handled

Revision ID: d90793645086
Revises: e544ff20fad6
Create Date: 2026-10-27 10:38:56.452733+00:00

A message DW1 routes to Sales stayed on Việc cần làm for good: nothing closed
it. A person now marks it handled once they have dealt with it outside DW1
(`dw_sales.application.routed_mail`), and may reopen it.

- **`handled_at`, `handled_by`, `handled_note`** on `sales.messages`: the
  mark, all null while the message waits on someone. One CHECK holds the
  shape: the time and the person come together, only a message routed to
  Sales carries them, and a note only beside a mark, at most 500 characters
  (`char_length`, not a regex repetition: PostgreSQL refuses a count above
  255, failure-modes #4). Recording a disposition again writes all three
  null, so processing a message again opens it.
- **`ix_messages_routed_work`** is rebuilt to leave handled messages out: the
  work list reads open ones only, and its statement now names the same
  predicate so the planner matches the index in a generic plan too.

No grant changes: `dw_app` already holds UPDATE on `sales.messages`, which
a re-processed routed message has always needed. `handled_by` names a user
the way `assigned_to` does, without a key into the platform's tables.
"""

from __future__ import annotations

from alembic import op

revision = "d90793645086"
down_revision = "e544ff20fad6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE sales.messages"
        " ADD COLUMN handled_at timestamptz,"
        " ADD COLUMN handled_by uuid,"
        " ADD COLUMN handled_note text"
    )
    op.execute(
        "ALTER TABLE sales.messages ADD CONSTRAINT ck_messages_handled CHECK ("
        " (handled_at IS NULL) = (handled_by IS NULL)"
        " AND (handled_at IS NULL OR disposition = 'routed_to_sales')"
        " AND (handled_note IS NULL"
        "      OR (handled_at IS NOT NULL AND char_length(handled_note) BETWEEN 1 AND 500))"
        ")"
    )
    op.execute("DROP INDEX sales.ix_messages_routed_work")
    op.execute(
        "CREATE INDEX ix_messages_routed_work ON sales.messages"
        " (tenant_id, workspace_id, processed_at, id)"
        " WHERE disposition = 'routed_to_sales' AND handled_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX sales.ix_messages_routed_work")
    op.execute(
        "CREATE INDEX ix_messages_routed_work ON sales.messages"
        " (tenant_id, workspace_id, processed_at, id)"
        " WHERE disposition = 'routed_to_sales'"
    )
    op.execute("ALTER TABLE sales.messages DROP CONSTRAINT ck_messages_handled")
    op.execute(
        "ALTER TABLE sales.messages"
        " DROP COLUMN handled_note,"
        " DROP COLUMN handled_by,"
        " DROP COLUMN handled_at"
    )

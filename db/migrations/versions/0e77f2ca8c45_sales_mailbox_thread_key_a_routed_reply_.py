"""sales mailbox thread key, a routed reply's thread cases

Revision ID: 0e77f2ca8c45
Revises: d94bf01066d2
Create Date: 2026-11-14 11:14:07.594158+00:00

Sales ticket 24, dw_sales ADR 0009 decisions 1-2: a customer conversation is
a mail thread read from its headers, and a thread may carry several cases.

- **`sales.mailbox_messages.thread_key`**: the thread a stored message is on,
  computed by code when it is stored (`dw_sales.application.threads.thread_key`):
  the key of the earliest already-stored message its `In-Reply-To` /
  `References` name in the workspace; else its own Message-ID; else its own
  mailbox id. Never from the subject, never from a model. `NOT NULL` and held
  to the shape of either id (`ck_mailbox_messages_thread_key`). The table is
  append-only for `dw_app` (no UPDATE, `e544ff20fad6`), so a key never changes
  once stored: a later message naming two threads joins the earliest, and no
  stored key is rewritten. `ix_mailbox_messages_thread_key` carries the
  look-up of a thread's messages, led by what RLS supplies.
- **Backfill**: the rows already stored are keyed in the order they were
  stored, by the same rule, inside each workspace (the migrator reads every
  tenant: each step names its own tenant and workspace).
- **`sales.messages.thread_cases`**: the cases a reply's thread holds when
  it names none of them, offered to Sales to pick ("Chọn hồ sơ"): an array
  of at least two, only on a message routed `reply_to_case`
  (`ck_messages_thread_cases`). NULL on every other message, never `[]`
  (failure-modes #7: an empty list would read as "offered nothing").

Downgrade drops both columns; a routed reply then offers no case, and the
thread keys are computed again on the next upgrade.
"""

from __future__ import annotations

from alembic import op

revision = "0e77f2ca8c45"
down_revision = "d94bf01066d2"
branch_labels = None
depends_on = None

_MAILBOX = "sales.mailbox_messages"
_KEY_CHECK = "ck_mailbox_messages_thread_key"
_KEY_INDEX = "ix_mailbox_messages_thread_key"
_MESSAGES = "sales.messages"
_CASES_CHECK = "ck_messages_thread_cases"

# Each stored message in the order it was stored, keyed by the rule the
# application applies when it stores one; "already stored" is a row keyed in
# an earlier step. Written out, not generated: `verify_invariants.py` reads
# migration text.
_BACKFILL = """
    DO $$
    DECLARE
        r record;
        found text;
    BEGIN
        FOR r IN
            SELECT tenant_id, workspace_id, message_id, received_at, internet_message_id,
                   COALESCE(message -> 'references', '[]'::jsonb) AS refs
            FROM sales.mailbox_messages
            ORDER BY stored_at, received_at, message_id
        LOOP
            SELECT m.thread_key INTO found
            FROM sales.mailbox_messages m
            WHERE m.tenant_id = r.tenant_id
              AND m.workspace_id = r.workspace_id
              AND m.thread_key IS NOT NULL
              AND m.internet_message_id IN (SELECT jsonb_array_elements_text(r.refs))
            ORDER BY m.received_at, m.message_id
            LIMIT 1;
            UPDATE sales.mailbox_messages
            SET thread_key = COALESCE(found, r.internet_message_id, r.message_id)
            WHERE tenant_id = r.tenant_id
              AND workspace_id = r.workspace_id
              AND message_id = r.message_id
              AND received_at = r.received_at;
        END LOOP;
    END
    $$
"""


def upgrade() -> None:
    op.execute(f"ALTER TABLE {_MAILBOX} ADD COLUMN thread_key text")
    op.execute(_BACKFILL)
    op.execute(
        f"ALTER TABLE {_MAILBOX} ALTER COLUMN thread_key SET NOT NULL,"
        f" ADD CONSTRAINT {_KEY_CHECK} CHECK ("
        " thread_key ~ '^[!-~]+$' AND char_length(thread_key) <= 996)"
    )
    op.execute(f"CREATE INDEX {_KEY_INDEX} ON {_MAILBOX} (tenant_id, workspace_id, thread_key)")
    op.execute(
        f"ALTER TABLE {_MESSAGES} ADD COLUMN thread_cases jsonb,"
        f" ADD CONSTRAINT {_CASES_CHECK} CHECK ("
        " thread_cases IS NULL OR ("
        " jsonb_typeof(thread_cases) = 'array'"
        " AND jsonb_array_length(thread_cases) BETWEEN 2 AND 50"
        " AND disposition = 'routed_to_sales'"
        " AND routing_reason = 'reply_to_case'))"
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE {_MESSAGES} DROP CONSTRAINT {_CASES_CHECK}, DROP COLUMN thread_cases")
    op.execute(f"DROP INDEX sales.{_KEY_INDEX}")
    op.execute(f"ALTER TABLE {_MAILBOX} DROP CONSTRAINT {_KEY_CHECK}, DROP COLUMN thread_key")

"""sales mailbox files refused, with their reason

Revision ID: 2b666371099a
Revises: c1c192e011e1
Create Date: 2026-10-29 02:10:00.000000+00:00

Đạt, 2026-10-29: "không thể làm hỏng luồng rồi im lặng luôn được". A file in
the drop folder the reader would not read, or one over the size limit, was
logged by name and nothing else: no one who works the mailbox was told a
customer's mail had not arrived, and a restart read it again and refused it
again. It is now handled like any other file, recorded with its reason, and
the lane tells the people who process the mailbox (`MailDrop`).

- **`ck_mailbox_files_outcome`** takes `refused`.
- **`reason`**: the words code wrote for the refusal, on a refused file and
  only there, bounded by `char_length` (failure-modes #4: never `{n,m}`).
- **`ck_mailbox_files_message_id`**: a refused file names no message either.

The table is partitioned by `handled_at`; a column and a CHECK added to the
parent reach every partition, the DEFAULT one included.
"""

from __future__ import annotations

from alembic import op

revision = "2b666371099a"
down_revision = "c1c192e011e1"
branch_labels = None
depends_on = None

_MESSAGE_ID = """
    (message_id IS NULL OR (
        message_id ~ '^[!-~]+$' AND char_length(message_id) <= 512
    ))
"""


def upgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE sales.mailbox_files
            ADD COLUMN reason text,
            DROP CONSTRAINT ck_mailbox_files_outcome,
            ADD CONSTRAINT ck_mailbox_files_outcome CHECK (
                outcome IN ('stored', 'duplicate', 'left_out', 'refused')
            ),
            DROP CONSTRAINT ck_mailbox_files_message_id,
            ADD CONSTRAINT ck_mailbox_files_message_id CHECK (
                (outcome IN ('left_out', 'refused')) = (message_id IS NULL)
                AND {_MESSAGE_ID}
            ),
            ADD CONSTRAINT ck_mailbox_files_reason CHECK (
                (outcome = 'refused') = (reason IS NOT NULL)
                AND (reason IS NULL OR char_length(reason) BETWEEN 1 AND 300)
            )
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM sales.mailbox_files WHERE outcome = 'refused'")
    op.execute(
        f"""
        ALTER TABLE sales.mailbox_files
            DROP CONSTRAINT ck_mailbox_files_reason,
            DROP CONSTRAINT ck_mailbox_files_message_id,
            ADD CONSTRAINT ck_mailbox_files_message_id CHECK (
                (outcome = 'left_out') = (message_id IS NULL)
                AND {_MESSAGE_ID}
            ),
            DROP CONSTRAINT ck_mailbox_files_outcome,
            ADD CONSTRAINT ck_mailbox_files_outcome CHECK (
                outcome IN ('stored', 'duplicate', 'left_out')
            ),
            DROP COLUMN reason
        """
    )

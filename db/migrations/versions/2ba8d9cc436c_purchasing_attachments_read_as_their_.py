"""purchasing attachments read as their mail is stored

Revision ID: 2ba8d9cc436c
Revises: da6950544c81
Create Date: 2026-11-03 04:15:18.745800+00:00

What DW2 read of each attachment, kept beside it
(`dw_purchasing.domain.attachments`): the `purchasing_mail_drop` lane scans
every attachment and reads a document's text in the reader sandbox before it
stores the mail, so the Excel PR form and the scanned paper are read once,
in the worker, and nothing after it parses the file.

- **`purchasing.mailbox_attachments.reading`** (jsonb): its pages, or the
  code why there are none. NULL for an attachment stored before this
  revision: never read, so its mail is read from its text alone.
- **`ck_mailbox_attachments_reading`**: pages or a reason, never both or
  neither; the reason one of the four the domain names.
- **`ck_mailbox_attachments_infected_not_kept`**: an infected file's bytes
  are never stored.

Both are added to the parent, so every partition, the DEFAULT one and each
month `platform.ensure_time_partitions` makes, carries them. Rows stay
append-only (no grant changes).
"""

from __future__ import annotations

from alembic import op

revision = "2ba8d9cc436c"
down_revision = "da6950544c81"
branch_labels = None
depends_on = None

_TABLE = "purchasing.mailbox_attachments"
# `dw_purchasing.domain.attachments.NotRead`.
_REASONS = "('infected', 'not_a_document', 'too_many', 'unreadable')"


def upgrade() -> None:
    op.execute(f"ALTER TABLE {_TABLE} ADD COLUMN reading jsonb")
    op.execute(
        f"""
        ALTER TABLE {_TABLE} ADD CONSTRAINT ck_mailbox_attachments_reading CHECK (
            reading IS NULL OR CASE
                WHEN jsonb_typeof(reading -> 'pages') = 'array' THEN
                    (jsonb_array_length(reading -> 'pages') = 0)
                        = (reading ->> 'not_read' IS NOT NULL)
                    AND coalesce(reading ->> 'not_read' IN {_REASONS}, true)
                ELSE false
            END
        )
        """
    )
    op.execute(
        f"""
        ALTER TABLE {_TABLE} ADD CONSTRAINT ck_mailbox_attachments_infected_not_kept CHECK (
            reading ->> 'not_read' IS DISTINCT FROM 'infected' OR octet_length(content) = 0
        )
        """
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE {_TABLE} DROP CONSTRAINT ck_mailbox_attachments_infected_not_kept")
    op.execute(f"ALTER TABLE {_TABLE} DROP CONSTRAINT ck_mailbox_attachments_reading")
    op.execute(f"ALTER TABLE {_TABLE} DROP COLUMN reading")

"""sales source served records the message text

Revision ID: 546a6a81e58c
Revises: 358bfa9b231f
Create Date: 2026-10-15 03:45:00.000000+00:00

Sales ticket 29, open item: confirming a value a model read was not gated on
the person having opened where it was read, as an order's prepare is
(`require_served`). A value read from a file is opened as a page or a sheet,
which `source_served` records; a value read from the mail's own text had no
record to check, because the text came inside the case view. The text is now
served on its own route and recorded here:

- **`attachment_id` NULL** is the message's text the case holds, with that
  text's sha256 in `attachment_sha256` and neither page nor sheet; only a
  quotation is read from it (`ck_source_served_region`).
- `ck_source_served_attachment` checks the id's shape when there is one.
- `uq_source_served_...` is UNIQUE NULLS NOT DISTINCT already, so the text is
  recorded once per person, case and version like any region.

The downgrade deletes the text rows: the old checks cannot hold them.
"""

from __future__ import annotations

from alembic import op

revision = "546a6a81e58c"
down_revision = "358bfa9b231f"
branch_labels = None
depends_on = None

_SHA256 = "'^[0-9a-f]{64}$'"
_ATTACHMENT_ID = "'^[A-Za-z0-9._-]{1,128}$'"
_FILE_REGION = "num_nonnulls(page, sheet) = 1 AND page >= 1 AND char_length(sheet) BETWEEN 1 AND 31"


def upgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE sales.source_served
            ALTER COLUMN attachment_id DROP NOT NULL,
            DROP CONSTRAINT ck_source_served_attachment,
            DROP CONSTRAINT ck_source_served_region,
            ADD CONSTRAINT ck_source_served_attachment CHECK (
                attachment_sha256 ~ {_SHA256}
                AND (attachment_id IS NULL OR attachment_id ~ {_ATTACHMENT_ID})
            ),
            ADD CONSTRAINT ck_source_served_region CHECK (
                CASE WHEN attachment_id IS NULL
                     THEN page IS NULL AND sheet IS NULL AND quote_case_id IS NOT NULL
                     ELSE {_FILE_REGION}
                END
            )
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM sales.source_served WHERE attachment_id IS NULL")
    op.execute(
        f"""
        ALTER TABLE sales.source_served
            DROP CONSTRAINT ck_source_served_region,
            DROP CONSTRAINT ck_source_served_attachment,
            ADD CONSTRAINT ck_source_served_attachment CHECK (
                attachment_id ~ {_ATTACHMENT_ID} AND attachment_sha256 ~ {_SHA256}
            ),
            ADD CONSTRAINT ck_source_served_region CHECK ({_FILE_REGION}),
            ALTER COLUMN attachment_id SET NOT NULL
        """
    )

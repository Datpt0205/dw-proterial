"""sales convert key is the customer's printed text

Revision ID: d7c11e671769
Revises: 66c90b900f4a
Create Date: 2026-11-14 04:23:27.060524+00:00

Ticket 36. Bravo's convert list (B04) keys a customer's item by its
converting description: their part number, or their words for the item
("UL1061(SPV004) AWG24(11/0.16) GRAY WIRE"), spaces and brackets included,
up to 84 characters in the real file. `ConvertEntry.customer_item_code` is
now text as a PO prints it (`PrintedText`: one line, no control character,
no padding, at most 200 characters), and a code Sales confirms for such a
line is kept the same way, so the CHECK on
`sales.recorded_convert_entries.customer_item_code` follows the model. The
length is bounded by `char_length`, not a regex repetition count (PostgreSQL
refuses one above 255, failure-modes #4).

Widened only: every row the old CHECK accepted, the new one accepts.
Downgrade restores the old CHECK and fails while a wider row exists, rather
than dropping it.
"""

from __future__ import annotations

from alembic import op

revision = "d7c11e671769"
down_revision = "66c90b900f4a"
branch_labels = None
depends_on = None

_TABLE = "sales.recorded_convert_entries"
_CHECK = "ck_recorded_convert_entries_customer_item_code"
_PRINTED = (
    r"customer_item_code ~ '^[^\s\x01-\x1f\x7f](?:[^\x01-\x1f\x7f]*[^\s\x01-\x1f\x7f])?$'"
    " AND char_length(customer_item_code) <= 200"
)
_CODE = "customer_item_code ~ '^[A-Za-z0-9][A-Za-z0-9._/-]{0,47}$'"


def upgrade() -> None:
    op.execute(f"ALTER TABLE {_TABLE} DROP CONSTRAINT {_CHECK}")
    op.execute(f"ALTER TABLE {_TABLE} ADD CONSTRAINT {_CHECK} CHECK ({_PRINTED})")


def downgrade() -> None:
    op.execute(f"ALTER TABLE {_TABLE} DROP CONSTRAINT {_CHECK}")
    op.execute(f"ALTER TABLE {_TABLE} ADD CONSTRAINT {_CHECK} CHECK ({_CODE})")

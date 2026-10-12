"""sales value corrections per field

Revision ID: 33f444c15062
Revises: d9e73228e7d7
Create Date: 2026-10-12 08:40:39.855007+00:00

Sales ticket 15. A value DW1 read from a place a person would not see (a
hidden row or sheet, font matching the fill, a formula with no cached value)
raises `value_uncertain`. Sales now corrects it field by field with a typed
value, and the upload file and the drafts print the corrected value. The value
as read stays where it was, as the evidence; the corrections are stored beside
it:

- **`order_lines.corrections`**: what Sales typed for the line's flagged
  values, one per field (`dw_sales.domain.orders.ValueCorrection`).
- **`order_revisions.header_corrections`**: the same for the header values and
  the printed total the PO-level `value_uncertain` flagged. On the revision,
  because a correction is of a value read from that revision's document; a
  later revision starts with none.

Both are arrays of objects holding exactly the keys `ValueCorrection` writes
(`field`, `value`, `by`, `at`), and the CHECK refuses any other key, so nothing
else travels in them (`test_sales_schema.py` compares the two lists). A value
may be an amount, as the line's own `po_line` holds one: the columns are read
through the same mapper that hides amounts without `sales.price.read`, and no
audit row or event carries them (ids and field names only).

The columns are added to tables every Sales role already reads and writes, so
their grants and RLS policies are the tables'; nothing else changes. Existing
rows get `[]`: a case read before this revision has no correction, which is
what it had.
"""

from __future__ import annotations

from alembic import op

revision = "33f444c15062"
down_revision = "d9e73228e7d7"
branch_labels = None
depends_on = None

# `dw_sales.domain.orders.ValueCorrection`'s fields: `test_sales_schema.py`
# compares the two, so they disagree loudly rather than quietly.
_KEYS = ("field", "value", "by", "at")
_COLUMNS = (("order_lines", "corrections"), ("order_revisions", "header_corrections"))


def _check(column: str) -> str:
    """An array of objects, each naming every key of a correction and no other.

    `jsonb_path_exists` answers false, never NULL, for an array whose elements
    all pass, so the CHECK cannot pass by evaluating to NULL.
    """
    named = " && ".join(f"exists(@.{key})" for key in _KEYS)
    known = " || ".join(f'@.key == "{key}"' for key in _KEYS)
    return f"""(
        jsonb_typeof({column}) = 'array'
        AND NOT jsonb_path_exists({column}, '$[*] ? (@.type() != "object")')
        AND NOT jsonb_path_exists({column}, '$[*] ? (!({named}))')
        AND NOT jsonb_path_exists({column}, '$[*].keyvalue() ? (!({known}))')
    )"""


def upgrade() -> None:
    for table, column in _COLUMNS:
        op.execute(
            f"ALTER TABLE sales.{table} ADD COLUMN {column} jsonb NOT NULL DEFAULT '[]'::jsonb"
        )
        op.execute(
            f"ALTER TABLE sales.{table} ADD CONSTRAINT ck_{table}_{column} CHECK {_check(column)}"
        )


def downgrade() -> None:
    for table, column in reversed(_COLUMNS):
        op.execute(f"ALTER TABLE sales.{table} DROP CONSTRAINT IF EXISTS ck_{table}_{column}")
        op.execute(f"ALTER TABLE sales.{table} DROP COLUMN IF EXISTS {column}")

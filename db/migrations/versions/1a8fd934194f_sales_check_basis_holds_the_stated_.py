"""sales check basis holds the stated attributes

Revision ID: 1a8fd934194f
Revises: 218118b8f0e5
Create Date: 2026-10-15 03:03:28.411107+00:00

The candidate picker compares each candidate with what the PO line's
description stated (spec, family, cores, gauge). What the description stated
is the input the candidates were computed from, so it is stamped on the
line's check basis when the line is mapped (`LineBasis.stated_attributes`),
next to the candidates, and the screen reads the stamp: reading the
description again on every view would be a second answer that drifts the day
DW1's vocabulary grows. `ck_order_lines_check_basis` names every key
`LineBasis` writes and refuses any other (`test_sales_schema.py` holds it to
the model's fields), so it takes the new one, an object or null, never a bare
string, as `a9977d62e09b` did for `description_reading`.

A line checked before this revision has no key and reads as null: "not
stamped", which the picker shows as it did before.

Downgrade restores `a9977d62e09b`'s key list. It fails, with Postgres's own
"violated by some row", while any line stores the key, even as null: a basis
is evidence, and stripping it to make a downgrade pass would rewrite what a
line was checked against.
"""

from __future__ import annotations

from alembic import op

revision = "1a8fd934194f"
down_revision = "218118b8f0e5"
branch_labels = None
depends_on = None

_TABLE = "sales.order_lines"
_NAME = "ck_order_lines_check_basis"
_BEFORE = (
    "convert_prv_code",
    "candidates",
    "item",
    "quotation",
    "lme",
    "lead_time_days",
    "lead_time_source",
    "checks_run",
    "description_reading",
)
_AFTER = (*_BEFORE, "stated_attributes")
# Keys whose value is an object or null, never a bare value.
_OBJECT_OR_NULL = ("description_reading", "stated_attributes")


def _replace(keys: tuple[str, ...]) -> None:
    listed = ", ".join(f"'{key}'" for key in keys)
    # Two comparisons, not IN: Postgres prints IN as `= ANY (ARRAY[...])`, and
    # the key list must stay the definition's one ARRAY (`test_sales_schema.py`
    # reads it back).
    shaped = "".join(
        f" AND (NOT check_basis ? '{key}'"
        f" OR jsonb_typeof(check_basis -> '{key}') = 'object'"
        f" OR jsonb_typeof(check_basis -> '{key}') = 'null')"
        for key in _OBJECT_OR_NULL
        if key in keys
    )
    op.execute(
        f"ALTER TABLE {_TABLE} DROP CONSTRAINT {_NAME},"
        f" ADD CONSTRAINT {_NAME} CHECK ("
        " jsonb_typeof(check_basis) = 'object'"
        " AND check_basis ? 'checks_run'"
        " AND jsonb_typeof(check_basis -> 'checks_run') = 'array'"
        " AND jsonb_array_length(check_basis -> 'checks_run') >= 1"
        f" AND (check_basis - ARRAY[{listed}]::text[]) = '{{}}'::jsonb"
        f"{shaped})"
    )


def upgrade() -> None:
    _replace(_AFTER)


def downgrade() -> None:
    _replace(_BEFORE)

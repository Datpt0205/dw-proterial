"""sales check basis holds a model reading

Revision ID: a9977d62e09b
Revises: f1980035d8de
Create Date: 2026-10-13 02:57:14.976994+00:00

Sales ticket 28, dw_sales ADR 0005. Where a tenant's rules turn it on, a local
model reads an item description DW1's own vocabulary does not, and the line's
check basis stamps what that reading did: `LineBasis.description_reading`
(the prompt, profile and route, the outcome, and the spans with who read each
value), or null when no model was asked. `ck_order_lines_check_basis` names
every key `LineBasis` writes and refuses any other (`test_sales_schema.py`
holds it to the model's fields), so it takes the new one, and the new key's
value is an object or null, never a bare string a later reader would have to
guess at.

Same name, same table (`sales.order_lines` is a plain table), dropped and
re-added in one statement and checked against the rows already there, as
`0d7fd21052a4` does for a finding code. The reading's own shape is the
domain's to refuse (`DescriptionReading`), as for every other basis key.

Downgrade restores the 0001-era key list. It fails, with Postgres's own
"violated by some row", while any line stores the key, even as null: a basis
is evidence, and stripping it to make a downgrade pass would rewrite what a
line was checked against.
"""

from __future__ import annotations

from alembic import op

revision = "a9977d62e09b"
down_revision = "f1980035d8de"
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
)
_AFTER = (*_BEFORE, "description_reading")


def _replace(keys: tuple[str, ...]) -> None:
    listed = ", ".join(f"'{key}'" for key in keys)
    reading = (
        " AND (NOT check_basis ? 'description_reading'"
        # Two comparisons, not IN: Postgres prints IN as `= ANY (ARRAY[...])`,
        # and the key list must stay the definition's one ARRAY
        # (`test_sales_schema.py` reads it back).
        " OR jsonb_typeof(check_basis -> 'description_reading') = 'object'"
        " OR jsonb_typeof(check_basis -> 'description_reading') = 'null')"
        if "description_reading" in keys
        else ""
    )
    op.execute(
        f"ALTER TABLE {_TABLE} DROP CONSTRAINT {_NAME},"
        f" ADD CONSTRAINT {_NAME} CHECK ("
        " jsonb_typeof(check_basis) = 'object'"
        " AND check_basis ? 'checks_run'"
        " AND jsonb_typeof(check_basis -> 'checks_run') = 'array'"
        " AND jsonb_array_length(check_basis -> 'checks_run') >= 1"
        f" AND (check_basis - ARRAY[{listed}]::text[]) = '{{}}'::jsonb"
        f"{reading})"
    )


def upgrade() -> None:
    _replace(_AFTER)


def downgrade() -> None:
    _replace(_BEFORE)

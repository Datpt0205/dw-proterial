"""sales finding code requested_date_missing

Revision ID: a459e2244a9c
Revises: 6d0252a87a6c
Create Date: 2026-10-13 13:45:32.883951+00:00

Sales ticket 34. A PO line printed with no requested date ("date to follow")
reads, and the line check raises `requested_date_missing`, a blocking finding
on that line which Sales decides by asking the customer or by going ahead with
the date to follow. `ck_order_findings_code` names every finding code the
domain has (`test_sales_schema.py` holds it to
`dw_sales.domain.orders.FindingCode`), so it takes the new one.

Same name, same table, dropped and re-added in one statement and checked
against the rows already there, as `0d7fd21052a4` does. Nothing else changes:
a line's requested date and a PO's PDF print (the other half of ticket 34)
live in the `po_line` and `document` jsonb the readers' models already write.

Downgrade restores `0d7fd21052a4`'s list. It fails, with Postgres's own
"violated by some row", while any `requested_date_missing` finding is stored:
deleting a case's findings to make a downgrade pass would make that case look
clean.
"""

from __future__ import annotations

from alembic import op

revision = "a459e2244a9c"
down_revision = "6d0252a87a6c"
branch_labels = None
depends_on = None

_TABLE = "sales.order_findings"
_NAME = "ck_order_findings_code"
_BEFORE = (
    "code_unmapped",
    "code_ambiguous",
    "price_mismatch",
    "currency_mismatch",
    "uom_mismatch",
    "quotation_missing",
    "lme_band_mismatch",
    "moq_violation",
    "pack_multiple",
    "line_total_mismatch",
    "value_uncertain",
    "customer_unknown",
    "duplicate_po",
    "requested_date_short_lt",
    "missing_noc_esf",
    "revised_po",
    "revision_without_base",
    "customer_temporary",
    "sender_unverified",
    "legacy_encoding",
)
_AFTER = (*_BEFORE, "requested_date_missing")


def _replace(codes: tuple[str, ...]) -> None:
    listed = ", ".join(f"'{code}'" for code in codes)
    op.execute(
        f"ALTER TABLE {_TABLE} DROP CONSTRAINT {_NAME},"
        f" ADD CONSTRAINT {_NAME} CHECK (code IN ({listed}))"
    )


def upgrade() -> None:
    _replace(_AFTER)


def downgrade() -> None:
    _replace(_BEFORE)

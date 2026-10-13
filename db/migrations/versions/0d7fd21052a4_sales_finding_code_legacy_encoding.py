"""sales finding code legacy_encoding

Revision ID: 0d7fd21052a4
Revises: 7c8ba908575f
Create Date: 2026-10-12 12:53:22.118892+00:00

Sales ticket 20. A PO typed in a TCVN3 or VNI font (`.VnTime`, `VNI-Times`)
holds Vietnamese as other characters; the readers detect the font and the
document check raises `legacy_encoding`, a blocking finding about the PO as a
whole whose only decision is `ask_customer`. `ck_order_findings_code` names
every finding code the domain has (`test_sales_schema.py` holds it to
`dw_sales.domain.orders.FindingCode`), so it takes the new one.

Same name, same table (`sales.order_findings` is a plain table), dropped and
re-added in one statement and checked against the rows already there, as
`d9e73228e7d7` does. Nothing else changes: the finding's level and its one
disposition are the domain's to refuse (`Finding`), as for every other code,
and what was read in a legacy font is kept in the `po_line` and `document`
jsonb the reader's model already writes.

Downgrade restores the 0001-era list. It fails, with Postgres's own "violated
by some row", while any `legacy_encoding` finding is stored: deleting a case's
findings to make a downgrade pass would make that case look clean.
"""

from __future__ import annotations

from alembic import op

revision = "0d7fd21052a4"
down_revision = "7c8ba908575f"
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
)
_AFTER = (*_BEFORE, "legacy_encoding")


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

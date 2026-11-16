"""sales finding code delivery_term_mismatch

Revision ID: e07b932e4516
Revises: 7c6ad2350566
Create Date: 2026-11-16 15:04:50.663031+00:00

Sales ticket 02, acceptance 2: the delivery term a PO prints is not the one
the customer's record holds (`delivery_term_mismatch`, order rules 1.15.0).
`ck_order_findings_code` names every finding code the domain has
(`test_sales_schema.py` holds it to `dw_sales.domain.orders.FindingCode`), so
it takes the new one.

Same name, same table, dropped and re-added in one statement and checked
against the rows already there, as `bc50e4985878` does.

Downgrade restores `3fcedec4e4f1`'s list. It fails, with Postgres's own
"violated by some row", while such a finding is stored: deleting a case's
findings to make a downgrade pass would make that case look clean.
"""

from __future__ import annotations

from alembic import op

revision = "e07b932e4516"
down_revision = "7c6ad2350566"
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
    "requested_date_missing",
    "reel_length_mismatch",
    "spec_mismatch",
    "files_disagree",
)
_AFTER = (*_BEFORE, "delivery_term_mismatch")


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

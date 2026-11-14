"""sales finding codes reel_length_mismatch and spec_mismatch

Revision ID: bc50e4985878
Revises: d7c11e671769
Create Date: 2026-11-14 09:07:56.878363+00:00

Sales ticket 38, the checks of customer 1's "hk & cable" sheet: a line's
description states a length per reel ("610X12") other than the item's
standard length (`reel_length_mismatch`), or a spec number other than the
item's (`spec_mismatch`). `ck_order_findings_code` names every finding code
the domain has (`test_sales_schema.py` holds it to
`dw_sales.domain.orders.FindingCode`), so it takes the two new ones.

Same name, same table, dropped and re-added in one statement and checked
against the rows already there, as `a459e2244a9c` does.

Downgrade restores `a459e2244a9c`'s list. It fails, with Postgres's own
"violated by some row", while either finding is stored: deleting a case's
findings to make a downgrade pass would make that case look clean.
"""

from __future__ import annotations

from alembic import op

revision = "bc50e4985878"
down_revision = "d7c11e671769"
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
)
_AFTER = (*_BEFORE, "reel_length_mismatch", "spec_mismatch")


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

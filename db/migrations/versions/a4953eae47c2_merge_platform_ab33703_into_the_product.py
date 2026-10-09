"""merge platform ab33703 into the product

Revision ID: a4953eae47c2
Revises: e63c8947a6b1, f1576bf82a5a
Create Date: 2026-10-08 00:00:00.000000+00:00

Joins the Sales chain (`e63c8947a6b1`) to the platform's security-debt and
support revisions (`ecb47f78702c` append-only approval decisions,
`983b509c3f0f` pending channel deliveries expire, `f381f1694395` SoD waiver
second person and role-scope recheck, `af8ee878b4ab` support staff and
grants, `f1576bf82a5a` support grants readable by the customer). The merge
itself changes nothing.
"""

from __future__ import annotations

revision = "a4953eae47c2"
down_revision = ("e63c8947a6b1", "f1576bf82a5a")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

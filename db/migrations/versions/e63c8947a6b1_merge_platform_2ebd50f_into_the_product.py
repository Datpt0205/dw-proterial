"""merge platform 2ebd50f into the product

Revision ID: e63c8947a6b1
Revises: ac31ff0f2087, 395acbcad324
Create Date: 2026-10-08 00:00:00.000000+00:00

Joins the Sales chain (`ac31ff0f2087`) to the platform's channel revisions
(`02930a73bbdf` link nonces, `9f2becb1bf80` inbound messages and preferences,
`5a25154e0296` deliveries, `e399be8c0a2d` view receipts and decision codes,
`395acbcad324` inbound updates). Those carry a twin check for another product's
revision ids, which never matches here. The merge itself changes nothing.
"""

from __future__ import annotations

revision = "e63c8947a6b1"
down_revision = ("ac31ff0f2087", "395acbcad324")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

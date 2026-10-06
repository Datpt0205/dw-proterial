"""merge platform 96f95ad into the product

Revision ID: 9c8b75ac5f91
Revises: 0d9e3f85d814, 6d4aed20ccf2
Create Date: 2026-10-06 18:45:17.864981+00:00

Joins the two heads the platform merge left: the Sales chain (`0d9e3f85d814`)
and the platform's approval revisions (`36dabf47619c` required_scope,
`6d4aed20ccf2` workspace keyset indexes). The merge itself changes nothing;
moving Sales onto the platform's stamp is the next revision, `ac31ff0f2087`.
"""

from __future__ import annotations

revision = "9c8b75ac5f91"
down_revision = ("0d9e3f85d814", "6d4aed20ccf2")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

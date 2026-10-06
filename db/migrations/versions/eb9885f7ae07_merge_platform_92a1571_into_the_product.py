"""merge platform 92a1571 into the product

Revision ID: eb9885f7ae07
Revises: 075dca5a6168, 7bbd071748ca
Create Date: 2026-10-06 15:07:55.798660+00:00

Joins the two heads the platform merge left: the Sales chain (`075dca5a6168`)
and the platform's memory and checkpoint revisions (`7bbd071748ca`). Neither
touches the other's tables, so the merge itself changes nothing.
"""

from __future__ import annotations

revision = "eb9885f7ae07"
down_revision = ("075dca5a6168", "7bbd071748ca")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

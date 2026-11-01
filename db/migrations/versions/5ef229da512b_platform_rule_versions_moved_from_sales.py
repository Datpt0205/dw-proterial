"""platform rule versions moved from sales

Revision ID: 5ef229da512b
Revises: 126b205278ad
Create Date: 2026-11-01 03:47:33.693160+00:00

ADR 0013 decision 3: the rule-version engine moves to the platform the day a
second context registers keys (Purchasing). Its table moves with it, rows
and all: `ALTER TABLE … SET SCHEMA` keeps every row, index, constraint, the
FORCEd row security and its tenant policy, the `touch_updated_at` trigger
and the grants, so nothing is copied and nothing is dropped. The key CHECK
still names Sales' keys only; a context that registers more widens it in
its own revision.
"""

from __future__ import annotations

from alembic import op

revision = "5ef229da512b"
down_revision = "126b205278ad"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sales.rule_versions SET SCHEMA platform")


def downgrade() -> None:
    op.execute("ALTER TABLE platform.rule_versions SET SCHEMA sales")

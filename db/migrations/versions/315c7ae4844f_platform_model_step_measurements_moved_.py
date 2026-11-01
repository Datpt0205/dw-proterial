"""platform model step measurements moved from sales

Revision ID: 315c7ae4844f
Revises: 633993a6d8b4
Create Date: 2026-11-01 06:00:00.000000+00:00

ADR 0014 decision 1: the model-step readiness check is the agent runtime's
(`dw_agent_runtime.model.readiness`), and the measurements it reads move with
it. `ALTER TABLE … SET SCHEMA` keeps every row, index, CHECK, the FORCEd row
security and its tenant policy, and the grants (SELECT and INSERT for
`dw_app`, UPDATE and DELETE revoked): nothing is copied and nothing dropped.
`ck_model_step_measurements_step` still names Sales' steps only; a context
that registers more widens it in its own revision.
"""

from __future__ import annotations

from alembic import op

revision = "315c7ae4844f"
down_revision = "633993a6d8b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sales.model_step_measurements SET SCHEMA platform")


def downgrade() -> None:
    op.execute("ALTER TABLE platform.model_step_measurements SET SCHEMA sales")

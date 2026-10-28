"""sales rules changed by the admin and the head only

Revision ID: 40266fbc98bf
Revises: fb59ce04fd76
Create Date: 2026-10-28

Đạt's decisions of 2026-10-28: a Sales PIC works to the company's settings and
does not change them ("các sales PIC chỉ nên theo config chung"); the rules are
changed by the admin and the Sales head ("giao hết cho admin cũng như sale
trưởng"), and a change the head makes applies at once ("Trưởng bộ phận tự áp
dụng luôn"), while the admin's waits for the head's approval.

- **`sales.rules.propose` leaves the role `sales_pic`.** The head keeps it with
  `sales.rules.approve`; the admin holds it through `sales_rules_editor`.
- **`applied_directly`**: a version the head applied themselves, with no
  approval. It is the one case where the proposer is also the decider, so
  `ck_rule_versions_checker_not_maker` yields to it, and
  `ck_rule_versions_applied_directly` holds it to its shape: decided, by its
  proposer, on no approval. Who may apply directly (a holder of
  `sales.rules.approve`) is the service's check; the row records that it
  happened and by whom, and the audit trail says `sales.rules.applied`.

Downgrade refuses while a directly applied version exists: turning it back
into a maker-checker row would claim an approval nobody gave.
"""

from __future__ import annotations

from alembic import op

revision = "40266fbc98bf"
down_revision = "fb59ce04fd76"
branch_labels = None
depends_on = None

_PROPOSE = "sales.rules.propose"


def upgrade() -> None:
    op.execute(f"UPDATE platform.roles SET scopes = scopes - '{_PROPOSE}' WHERE key = 'sales_pic'")
    op.execute(
        """
        ALTER TABLE sales.rule_versions
            ADD COLUMN applied_directly boolean NOT NULL DEFAULT false,
            DROP CONSTRAINT ck_rule_versions_checker_not_maker,
            ADD CONSTRAINT ck_rule_versions_checker_not_maker CHECK (
                decided_by IS NULL OR decided_by <> proposed_by OR applied_directly
            ),
            ADD CONSTRAINT ck_rule_versions_applied_directly CHECK (
                NOT applied_directly OR (
                    status IN ('approved', 'superseded')
                    AND approval_id IS NULL
                    AND decided_by = proposed_by
                )
            )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM sales.rule_versions WHERE applied_directly) THEN
                RAISE EXCEPTION 'a rule version was applied directly by the head';
            END IF;
        END $$
        """
    )
    op.execute(
        """
        ALTER TABLE sales.rule_versions
            DROP CONSTRAINT ck_rule_versions_applied_directly,
            DROP CONSTRAINT ck_rule_versions_checker_not_maker,
            ADD CONSTRAINT ck_rule_versions_checker_not_maker CHECK (
                decided_by IS NULL OR decided_by <> proposed_by
            ),
            DROP COLUMN applied_directly
        """
    )
    op.execute(
        f"UPDATE platform.roles SET scopes = scopes || '[\"{_PROPOSE}\"]'::jsonb"
        f" WHERE key = 'sales_pic' AND NOT scopes ? '{_PROPOSE}'"
    )

"""purchasing supplier mail settled and its two model steps

Revision ID: ad62389cc25d
Revises: 63b96e56db85
Create Date: 2026-11-04 06:53:18.555558+00:00

DW02 function 5b: DW2's lane reads a supplier's quote and an order's
confirmation on its own (`dw_purchasing.application.automation_lane`).

- **`ck_mail_outcomes_disposition`** admits `supplier`: a known supplier's
  verified mail handled at its case, read there or its buyer told, so it
  leaves the unread list. **`ck_mail_outcomes_shape`** gives it its shape:
  it names the case it was handled at and no reason.
- **`ck_model_step_measurements_step`** admits the two readings whose live
  measurement lets those steps run on their own:
  `purchasing_supplier_quote_reading`, `purchasing_order_confirmation_reading`.

Held to the domain's values by `test_purchasing_store_db.py`. The downgrade
deletes the rows the old checks cannot hold.
"""

from __future__ import annotations

from alembic import op

revision = "ad62389cc25d"
down_revision = "63b96e56db85"
branch_labels = None
depends_on = None

_STEPS_BEFORE = (
    "description_attributes",
    "message_intent",
    "rfq_extraction",
    "reply_intent",
    "request_handoff",
    "layout_proposal",
    "po_body_extraction",
    "purchasing_pr_mail_reading",
)
_NEW_STEPS = ("purchasing_supplier_quote_reading", "purchasing_order_confirmation_reading")

_SHAPE_BEFORE = (
    "(disposition = 'opened' AND case_id IS NOT NULL AND reason IS NULL)"
    " OR (disposition = 'to_person' AND case_id IS NULL AND reason IS NOT NULL)"
)
_SHAPE = f"{_SHAPE_BEFORE} OR (disposition = 'supplier' AND case_id IS NOT NULL AND reason IS NULL)"


def _listed(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _set(dispositions: tuple[str, ...], shape: str, steps: tuple[str, ...]) -> None:
    op.execute(
        "ALTER TABLE purchasing.mail_outcomes"
        " DROP CONSTRAINT ck_mail_outcomes_disposition,"
        " ADD CONSTRAINT ck_mail_outcomes_disposition"
        f" CHECK (disposition IN ({_listed(dispositions)})),"
        " DROP CONSTRAINT ck_mail_outcomes_shape,"
        f" ADD CONSTRAINT ck_mail_outcomes_shape CHECK ({shape})"
    )
    op.execute(
        "ALTER TABLE platform.model_step_measurements"
        " DROP CONSTRAINT ck_model_step_measurements_step,"
        f" ADD CONSTRAINT ck_model_step_measurements_step CHECK (step IN ({_listed(steps)}))"
    )


def upgrade() -> None:
    _set(("opened", "to_person", "supplier"), _SHAPE, (*_STEPS_BEFORE, *_NEW_STEPS))


def downgrade() -> None:
    op.execute("DELETE FROM purchasing.mail_outcomes WHERE disposition = 'supplier'")
    op.execute(
        f"DELETE FROM platform.model_step_measurements WHERE step IN ({_listed(_NEW_STEPS)})"
    )
    _set(("opened", "to_person"), _SHAPE_BEFORE, _STEPS_BEFORE)

"""sales messages keep a hand-off a model pre-filled

Revision ID: a970a6cbac29
Revises: aeb7a7241d75
Create Date: 2026-10-13 08:52:00.000000+00:00

Sales ticket 33, dw_sales ADR 0005. A message routed to Sales as a delivery
change, a complaint or a sample request carries, where the tenant's rules turn
it on, a hand-off to PC or QA pre-filled from the customer's own words: the
PO code resolved against the sender's own orders, the lines, quantities and
dates code located and parsed, the lot, the customer's sentences, and the
stamp of the call (`MessageDisposition.handoff`). New nullable column
`handoff`: null for every other message. An object or null, never a bare
string, and only on a message routed to Sales; its shape is the domain's to
refuse (`Handoff`), the kind matching the routing reason included.

Downgrade drops the column, and with it the pre-filled hand-offs; the
messages stay routed as they were.
"""

from __future__ import annotations

from alembic import op

revision = "a970a6cbac29"
down_revision = "aeb7a7241d75"
branch_labels = None
depends_on = None

_TABLE = "sales.messages"
_HANDOFF = "ck_messages_handoff"


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE {_TABLE} ADD COLUMN handoff jsonb,"
        f" ADD CONSTRAINT {_HANDOFF} CHECK ("
        " handoff IS NULL OR (jsonb_typeof(handoff) = 'object'"
        " AND disposition = 'routed_to_sales'"
        " AND routing_reason = handoff ->> 'kind'))"
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE {_TABLE} DROP CONSTRAINT {_HANDOFF}, DROP COLUMN handoff")

"""sales messages stamp a model reading of their intent

Revision ID: dab4fd83b8cb
Revises: a9977d62e09b
Create Date: 2026-10-13 04:13:10.621765+00:00

Sales ticket 31, dw_sales ADR 0005. Where a tenant's rules turn it on, a local
model gives the kind of a message no reader accepted, and code routes it. The
disposition stamps what that reading did (`MessageDisposition.reading`: the
prompt, profile and route, the rules whose switch asked, the outcome, the kind
and language read, and the numbers code resolved), in a new nullable column
`model_reading`: null when no model was asked, which is every message of a
tenant with the step off and every message whose attachment decided its kind.
The value is an object or null, never a bare string a later reader would have
to guess at; its shape is the domain's to refuse (`IntentReading`).

A reply about a case already in hand is a routing reason of its own,
`reply_to_case` (only a model reading gives it). `ck_messages_routing_reason`
names every reason the domain has (`test_sales_schema.py` holds it to
`RoutingReason`), so it takes the new one: dropped and re-added in one
statement and checked against the rows already there, as `0d7fd21052a4` does
for a finding code.

Downgrade restores both. It fails, with Postgres's own "violated by some row",
while any message is routed `reply_to_case`; it drops the readings, which are
a stamp of how a message was classified and are lost with the column.
"""

from __future__ import annotations

from alembic import op

revision = "dab4fd83b8cb"
down_revision = "a9977d62e09b"
branch_labels = None
depends_on = None

_TABLE = "sales.messages"
_REASON = "ck_messages_routing_reason"
_READING = "ck_messages_model_reading"
_BEFORE = (
    "delivery_change",
    "complaint",
    "design_reply_unmatched",
    "sample_request",
    "customer_unknown",
    "attachment_unreadable",
    "other",
)
_AFTER = (*_BEFORE, "reply_to_case")


def _reasons(reasons: tuple[str, ...]) -> None:
    listed = ", ".join(f"'{reason}'" for reason in reasons)
    op.execute(
        f"ALTER TABLE {_TABLE} DROP CONSTRAINT {_REASON},"
        f" ADD CONSTRAINT {_REASON} CHECK (routing_reason IN ({listed}))"
    )


def upgrade() -> None:
    _reasons(_AFTER)
    op.execute(
        f"ALTER TABLE {_TABLE} ADD COLUMN model_reading jsonb,"
        f" ADD CONSTRAINT {_READING} CHECK ("
        " model_reading IS NULL OR jsonb_typeof(model_reading) = 'object')"
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE {_TABLE} DROP CONSTRAINT {_READING}, DROP COLUMN model_reading")
    _reasons(_BEFORE)

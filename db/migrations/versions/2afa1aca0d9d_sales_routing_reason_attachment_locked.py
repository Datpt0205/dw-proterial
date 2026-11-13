"""sales routing reason attachment_locked

Revision ID: 2afa1aca0d9d
Revises: e13dd31820b5
Create Date: 2026-11-13

Sales ticket 17. A PO file locked with a password is opened in the reader
sandbox with the passwords its own mail carries; one that none of them opens
routes its message to Sales, as an unreadable file does, with the routing
reason `attachment_locked` ("Tệp có mật khẩu, DW không mở được").
`ck_messages_routing_reason` names every reason the domain has
(`test_sales_schema.py` holds it to `dw_sales.domain.dispositions.RoutingReason`),
so it takes the new one.

Same name, same table, dropped and re-added in one statement and checked
against the rows already there, as `13c687788955` did for `malware_detected`.
No column: no password is stored anywhere, and which attachment is locked is
in the message's `detail` and its audit row (ids and code's own words).

Downgrade restores `13c687788955`'s list. It fails, with Postgres's own
"violated by some row", while a message routed for a locked file is stored.
"""

from __future__ import annotations

from alembic import op

revision = "2afa1aca0d9d"
down_revision = "e13dd31820b5"
branch_labels = None
depends_on = None

_TABLE = "sales.messages"
_REASON = "ck_messages_routing_reason"
_BEFORE = (
    "delivery_change",
    "complaint",
    "design_reply_unmatched",
    "sample_request",
    "customer_unknown",
    "attachment_unreadable",
    "other",
    "reply_to_case",
    "malware_detected",
)
_AFTER = (*_BEFORE, "attachment_locked")


def _reasons(reasons: tuple[str, ...]) -> None:
    listed = ", ".join(f"'{reason}'" for reason in reasons)
    op.execute(
        f"ALTER TABLE {_TABLE} DROP CONSTRAINT {_REASON},"
        f" ADD CONSTRAINT {_REASON} CHECK (routing_reason IN ({listed}))"
    )


def upgrade() -> None:
    _reasons(_AFTER)


def downgrade() -> None:
    _reasons(_BEFORE)

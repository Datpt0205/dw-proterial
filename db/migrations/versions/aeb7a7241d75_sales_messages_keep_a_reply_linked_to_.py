"""sales messages keep a reply linked to its case by thread

Revision ID: aeb7a7241d75
Revises: dab4fd83b8cb
Create Date: 2026-10-13 07:21:12.988882+00:00

Sales ticket 32, dw_sales ADR 0005. A customer's reply whose thread headers
(`In-Reply-To`, `References`) name a message already on a case of the
sender's own customer is attached to that case, and the disposition says so
(`MessageDisposition.reply`: the message on the case the reply answers, and,
where the tenant's rules asked a local model, what it read the reply as and
the sentences code located). New nullable column `case_reply`: null for every
message that is no such reply. The value is an object or null, never a bare
string a later reader would have to guess at; its shape is the domain's to
refuse (`CaseReply`).

`attached_to_case` is a disposition the table already takes, with the order
or quote case column the reply's case kind names, so no other constraint
changes.

Downgrade drops the column, and with it what was read from the replies; the
replies stay attached to their cases.
"""

from __future__ import annotations

from alembic import op

revision = "aeb7a7241d75"
down_revision = "dab4fd83b8cb"
branch_labels = None
depends_on = None

_TABLE = "sales.messages"
_REPLY = "ck_messages_case_reply"


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE {_TABLE} ADD COLUMN case_reply jsonb,"
        f" ADD CONSTRAINT {_REPLY} CHECK ("
        " case_reply IS NULL OR (jsonb_typeof(case_reply) = 'object'"
        " AND disposition = 'attached_to_case'))"
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE {_TABLE} DROP CONSTRAINT {_REPLY}, DROP COLUMN case_reply")

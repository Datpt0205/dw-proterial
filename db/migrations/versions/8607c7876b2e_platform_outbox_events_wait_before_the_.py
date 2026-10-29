"""platform outbox events wait before the next attempt

Revision ID: 8607c7876b2e
Revises: 2b666371099a
Create Date: 2026-10-29 03:00:00.000000+00:00

Đạt, 2026-10-29: "đã có message queue hay retry gì để xử lý hết các exception
lỡ luồng gãy khi chạy chưa". The outbox retried a failed event on the next
poll, a second later, so its three attempts were spent in about three seconds:
a reader or scanner restarting for ten seconds was enough to strand a
master-data upload, a rule draft or a decided approval for good.

- **`next_attempt_at`**: when a failed event may be claimed again. NULL for an
  event never tried, or one an admin sent back to the queue. The dispatcher
  sets it from the attempts made (`dw_worker.consumers.outbox.retry_delay`);
  `claim_batch` skips an event whose time has not come.

No index: the claim already narrows by `ix_outbox_events_unprocessed`, and the
rows waiting at any moment are a handful.
"""

from __future__ import annotations

from alembic import op

revision = "8607c7876b2e"
down_revision = "2b666371099a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE platform.outbox_events ADD COLUMN next_attempt_at timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE platform.outbox_events DROP COLUMN next_attempt_at")

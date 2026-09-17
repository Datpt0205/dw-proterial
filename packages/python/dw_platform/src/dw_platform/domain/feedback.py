"""User feedback: a bug report a member sends to their org's admins.

Read models - the write path passes fields explicitly and the database stamps
``created_at`` (one clock), so these dataclasses only ever describe rows read
back. ``author_name`` is joined from ``users`` for the admin inbox.

Since spec 003 US5 a feedback names the module it is about, the page it was
sent from, an optional suggestion, and carries screenshots; the ``category``
column stays for the rows written before that and reads ``bug`` for the rest.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from dw_kernel.ids import TenantId, UserId, WorkspaceId


@dataclass(frozen=True, slots=True)
class FeedbackAttachment:
    """One screenshot. The bytes live in object storage under ``object_key``."""

    id: uuid.UUID
    feedback_id: uuid.UUID
    object_key: str
    content_type: str
    size_bytes: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Feedback:
    id: uuid.UUID
    tenant_id: TenantId
    workspace_id: WorkspaceId
    author_id: UserId
    author_name: str
    category: str
    message: str
    created_at: datetime
    module: str | None = None
    page_path: str | None = None
    suggestion: str | None = None
    attachments: tuple[FeedbackAttachment, ...] = ()

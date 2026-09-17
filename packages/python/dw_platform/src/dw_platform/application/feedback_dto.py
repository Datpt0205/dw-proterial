"""Limits and naming for feedback screenshots (spec 003 US5).

Constants rather than configuration, following ``MAX_DOCUMENT_BYTES`` in the
CRM: they bound a request, they do not vary per tenant or environment.
"""

from __future__ import annotations

import uuid

# A 4K PNG screenshot is 3-6 MB; ten leaves a full margin without letting a
# feedback become a file transfer.
MAX_FEEDBACK_IMAGE_BYTES = 10 * 1024 * 1024
# One bug rarely needs more than a handful of screens; five keeps the inbox
# readable and the request bounded.
MAX_FEEDBACK_IMAGES = 5
# Screenshots only. A PDF or a log file is not what the form asks for.
FEEDBACK_IMAGE_MIMES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})


def attachment_key(
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    feedback_id: uuid.UUID,
    attachment_id: uuid.UUID,
) -> str:
    """Tenant and workspace in the object path is a hard rule (cache-key law)."""
    return f"feedback/{tenant_id}/{workspace_id}/{feedback_id}/{attachment_id}"

"""What this context is about. No framework anywhere near it.

Replace `SalesRequest` with the real thing. What must NOT change is the
shape: a frozen model that refuses an invalid state in its constructor, so
nothing downstream has to ask whether it is valid.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class SalesRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: uuid.UUID
    tenant_id: uuid.UUID
    subject: str = Field(min_length=1, max_length=200)

    def summary(self) -> str:
        """A domain rule, here so the layer is not an empty folder."""
        return self.subject.strip()

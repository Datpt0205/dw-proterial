"""What the Purchasing integration tests share, under a name no other suite
uses (two `conftest` modules cannot both be imported by name)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Tenancy:
    """Two tenants; the first with two workspaces."""

    alpha: tuple[uuid.UUID, uuid.UUID]
    alpha_other: tuple[uuid.UUID, uuid.UUID]
    beta: tuple[uuid.UUID, uuid.UUID]

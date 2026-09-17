"""A tiny cache port the platform reads through.

Deliberately small: get a string, set a string with a TTL, drop a set of keys by
pattern. The pattern delete is how a mutation (a grant, a revoke, a manager
change) invalidates everything it could have affected without tracking each key.

Every implementation is **fail-open**: if the cache is unreachable, a get is a
miss and a set/delete is a no-op, so the caller falls back to the source of
truth. A cache outage must never deny a request.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


def membership_cache_key(tenant_id: UUID, workspace_id: UUID, issuer: str, subject: str) -> str:
    """Key for one signed-in identity's resolved AccessContext in one workspace."""
    return f"ml:{tenant_id}:{workspace_id}:{issuer}:{subject}"


def membership_cache_pattern(tenant_id: UUID, workspace_id: UUID) -> str:
    """Every cached AccessContext for one workspace — delete on any membership
    change there (grant, revoke, role change) to invalidate at once."""
    return f"ml:{tenant_id}:{workspace_id}:*"


def tenant_cache_pattern(tenant_id: UUID) -> str:
    """Every cached AccessContext across a tenant — delete on a tenant-wide change
    (e.g. record_visibility), which affects every workspace's contexts."""
    return f"ml:{tenant_id}:*"


class CachePort(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, *, ttl_seconds: int) -> None: ...

    async def delete_pattern(self, pattern: str) -> None:
        """Drop every key matching a glob pattern (e.g. ``ml:{tenant}:{ws}:*``)."""
        ...

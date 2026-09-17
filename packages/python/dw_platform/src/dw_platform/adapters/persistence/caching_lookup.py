"""Cache the membership lookup that builds every request's AccessContext.

``find_access`` runs several queries and fires on every authenticated request —
the largest per-request database cost. This wraps it: the resolved access (or a
"no membership" negative) is cached under
``ml:{tenant}:{workspace}:{issuer}:{subject}`` for a short TTL, so a burst of
requests from one signed-in user hits the database once.

Correctness rests on two things: the TTL is short (seconds), and a membership
change invalidates the workspace's cached lookups at the mutation site via
``membership_cache_pattern`` — so a grant, revoke or role change takes effect at
once, and the TTL only bounds anything an invalidation missed. Caching is a copy
with a short life, not a second source of truth (CLAUDE.md §5).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID

from dw_platform.application.cache import CachePort, membership_cache_key
from dw_platform.application.identity import MembershipAccess, MembershipLookupPort

# Default: short enough that stale authorization is bounded to seconds even if an
# invalidation is missed, long enough to absorb a page's burst of requests.
DEFAULT_TTL_SECONDS = 30
_NEGATIVE = "\x00"  # sentinel: "looked up, no membership" — cached to spare the DB


def _serialize(access: MembershipAccess) -> str:
    return json.dumps(
        {
            "tenant_id": str(access.tenant_id),
            "workspace_id": str(access.workspace_id),
            "principal_id": str(access.principal_id),
            "roles": sorted(access.roles),
            "scopes": sorted(access.scopes),
            "groups": sorted(access.groups),
            "clearance": access.clearance,
            "plan_id": access.plan_id,
            "feature_flags": sorted(access.feature_flags),
            "record_visibility": access.record_visibility,
            "visible_owners": (
                None
                if access.visible_owners is None
                else sorted(str(u) for u in access.visible_owners)
            ),
        }
    )


def _deserialize(raw: str) -> MembershipAccess:
    data = json.loads(raw)
    return MembershipAccess(
        tenant_id=UUID(data["tenant_id"]),
        workspace_id=UUID(data["workspace_id"]),
        principal_id=UUID(data["principal_id"]),
        roles=frozenset(data["roles"]),
        scopes=frozenset(data["scopes"]),
        groups=frozenset(data["groups"]),
        clearance=data["clearance"],
        plan_id=data["plan_id"],
        feature_flags=frozenset(data["feature_flags"]),
        record_visibility=data.get("record_visibility", "open"),
        visible_owners=(
            None
            if data.get("visible_owners") is None
            else frozenset(UUID(u) for u in data["visible_owners"])
        ),
    )


@dataclass(frozen=True)
class CachingMembershipLookup:
    """Implements ``MembershipLookupPort`` in front of another one."""

    inner: MembershipLookupPort
    cache: CachePort
    ttl_seconds: int = DEFAULT_TTL_SECONDS

    async def find_access(
        self, subject: str, issuer: str, tenant_id: UUID, workspace_id: UUID
    ) -> MembershipAccess | None:
        key = membership_cache_key(tenant_id, workspace_id, issuer, subject)
        cached = await self.cache.get(key)
        if cached is not None:
            return None if cached == _NEGATIVE else _deserialize(cached)

        access = await self.inner.find_access(subject, issuer, tenant_id, workspace_id)
        await self.cache.set(
            key,
            _NEGATIVE if access is None else _serialize(access),
            ttl_seconds=self.ttl_seconds,
        )
        return access

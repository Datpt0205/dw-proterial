"""Unit: the caching membership lookup serves from cache and invalidates.

Fakes for the cache and the inner lookup — no database. What matters: a second
identical lookup is served from cache (the inner is not called again), a "no
membership" answer is cached too, and a pattern delete forces a fresh lookup.
"""

from __future__ import annotations

import fnmatch
import uuid

from dw_platform.adapters.persistence.caching_lookup import CachingMembershipLookup
from dw_platform.application.cache import membership_cache_pattern
from dw_platform.application.identity import MembershipAccess

TENANT = uuid.uuid4()
WS = uuid.uuid4()
ISSUER = "https://issuer.test/realms/dw"
SUBJECT = "sub-abc"


class _FakeCache:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        self.store[key] = value

    async def delete_pattern(self, pattern: str) -> None:
        for key in [k for k in self.store if fnmatch.fnmatch(k, pattern)]:
            del self.store[key]


class _CountingLookup:
    def __init__(self, result: MembershipAccess | None) -> None:
        self.result = result
        self.calls = 0

    async def find_access(
        self, subject: str, issuer: str, tenant_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> MembershipAccess | None:
        self.calls += 1
        return self.result


def _access() -> MembershipAccess:
    return MembershipAccess(
        tenant_id=TENANT,
        workspace_id=WS,
        principal_id=uuid.uuid4(),
        roles=frozenset({"sales"}),
        scopes=frozenset({"crm.account.read", "crm.lead.write"}),
        groups=frozenset(),
        clearance="internal",
        plan_id="professional",
        feature_flags=frozenset({"knowledge_search"}),
    )


async def test_second_lookup_is_served_from_cache() -> None:
    access = _access()
    inner = _CountingLookup(access)
    lookup = CachingMembershipLookup(inner, _FakeCache())

    first = await lookup.find_access(SUBJECT, ISSUER, TENANT, WS)
    second = await lookup.find_access(SUBJECT, ISSUER, TENANT, WS)

    assert inner.calls == 1  # the database was hit once
    assert first == second == access  # and the round-trips the same value


async def test_restricted_visible_owners_survive_the_round_trip() -> None:
    # A restricted-tenant access carries the subtree it may see (ADR-003). The
    # cache serializes to JSON, so the frozenset of UUIDs has to come back intact
    # and typed — a str leaking through here would silently widen a query.
    owners = frozenset({uuid.uuid4(), uuid.uuid4()})
    access = MembershipAccess(
        tenant_id=TENANT,
        workspace_id=WS,
        principal_id=uuid.uuid4(),
        roles=frozenset({"sales"}),
        scopes=frozenset({"crm.account.read"}),
        groups=frozenset(),
        clearance="internal",
        plan_id="professional",
        feature_flags=frozenset(),
        record_visibility="restricted",
        visible_owners=owners,
    )
    inner = _CountingLookup(access)
    lookup = CachingMembershipLookup(inner, _FakeCache())

    await lookup.find_access(SUBJECT, ISSUER, TENANT, WS)
    served = await lookup.find_access(SUBJECT, ISSUER, TENANT, WS)

    assert inner.calls == 1
    assert served is not None
    assert served.record_visibility == "restricted"
    assert served.visible_owners == owners
    # The point of the next line is that a cache round-trip returns real UUIDs
    # rather than the strings JSON turns them into, so it has to iterate what
    # came BACK. `None` is a real answer from this field - it means the whole
    # workspace - and it is not the answer under test here.
    assert served.visible_owners is not None
    assert all(isinstance(u, uuid.UUID) for u in served.visible_owners)


async def test_a_no_membership_answer_is_cached_too() -> None:
    inner = _CountingLookup(None)
    lookup = CachingMembershipLookup(inner, _FakeCache())

    assert await lookup.find_access(SUBJECT, ISSUER, TENANT, WS) is None
    assert await lookup.find_access(SUBJECT, ISSUER, TENANT, WS) is None
    assert inner.calls == 1  # default-deny is not re-queried every request


async def test_invalidation_forces_a_fresh_lookup() -> None:
    access = _access()
    inner = _CountingLookup(access)
    cache = _FakeCache()
    lookup = CachingMembershipLookup(inner, cache)

    await lookup.find_access(SUBJECT, ISSUER, TENANT, WS)
    await cache.delete_pattern(membership_cache_pattern(TENANT, WS))
    await lookup.find_access(SUBJECT, ISSUER, TENANT, WS)

    assert inner.calls == 2  # the grant/revoke invalidation was honoured

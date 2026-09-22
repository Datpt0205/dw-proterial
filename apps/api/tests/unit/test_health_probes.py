"""Ops hardening Phase 5: Redis and Qdrant readiness probes.

``database_probe`` already has no direct unit test of its own — only the
HTTP-level ``test_health_endpoints.py``, which fakes the probe entirely. These
two are new, so they get one: not_configured / ok / failed for each, against a
fake client rather than a real Redis/Qdrant connection (that belongs to the
integration suite).
"""

from __future__ import annotations

import pytest

from dw_api.health import qdrant_probe, redis_probe

pytestmark = pytest.mark.unit


class _FakeRedis:
    def __init__(self, *, fails: bool = False) -> None:
        self._fails = fails

    async def ping(self) -> bool:
        if self._fails:
            raise ConnectionError("boom")
        return True


class _FakeQdrant:
    def __init__(self, *, fails: bool = False) -> None:
        self._fails = fails

    async def get_collections(self) -> object:
        if self._fails:
            raise ConnectionError("boom")
        return object()


async def test_redis_probe_not_configured_without_a_client() -> None:
    assert await redis_probe(None)() == "not_configured"


async def test_redis_probe_ok_when_ping_succeeds() -> None:
    assert await redis_probe(_FakeRedis())() == "ok"  # type: ignore[arg-type]


async def test_redis_probe_failed_when_ping_raises() -> None:
    assert await redis_probe(_FakeRedis(fails=True))() == "failed"  # type: ignore[arg-type]


async def test_qdrant_probe_not_configured_without_a_client() -> None:
    assert await qdrant_probe(None)() == "not_configured"


async def test_qdrant_probe_ok_when_reachable() -> None:
    assert await qdrant_probe(_FakeQdrant())() == "ok"  # type: ignore[arg-type]


async def test_qdrant_probe_failed_when_unreachable() -> None:
    assert await qdrant_probe(_FakeQdrant(fails=True))() == "failed"  # type: ignore[arg-type]

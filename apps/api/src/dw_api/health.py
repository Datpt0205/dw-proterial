"""Liveness/readiness checks with injectable probes (no globals)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

import redis.asyncio as aioredis
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql import text

CheckState = Literal["ok", "failed", "not_configured"]

DependencyProbe = Callable[[], Awaitable[CheckState]]


@dataclass(frozen=True)
class ReadinessReport:
    checks: dict[str, CheckState]

    @property
    def ready(self) -> bool:
        return all(state == "ok" for state in self.checks.values())


class HealthService:
    """Aggregates dependency probes; the composition root wires real ones."""

    def __init__(self, probes: dict[str, DependencyProbe]) -> None:
        self._probes = probes

    async def readiness(self) -> ReadinessReport:
        results: dict[str, CheckState] = {}
        for name, probe in self._probes.items():
            try:
                results[name] = await probe()
            except Exception:
                results[name] = "failed"
        return ReadinessReport(checks=results)


def database_probe(engine: AsyncEngine | None) -> DependencyProbe:
    async def probe() -> CheckState:
        if engine is None:
            return "not_configured"
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return "ok"
        except Exception:
            return "failed"

    return probe


def redis_probe(client: aioredis.Redis | None) -> DependencyProbe:
    """``client`` is the already-built Valkey/Redis client, or ``None`` when
    no ``REDIS_URL`` is configured — same convention as ``database_probe``.
    """

    async def probe() -> CheckState:
        if client is None:
            return "not_configured"
        try:
            await client.ping()
            return "ok"
        except Exception:
            return "failed"

    return probe


def qdrant_probe(client: AsyncQdrantClient | None) -> DependencyProbe:
    async def probe() -> CheckState:
        if client is None:
            return "not_configured"
        try:
            await client.get_collections()
            return "ok"
        except Exception:
            return "failed"

    return probe

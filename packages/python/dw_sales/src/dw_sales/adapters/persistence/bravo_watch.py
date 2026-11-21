"""The Bravo change watch's tables in PostgreSQL (ticket 65, migration 6b0f375184fb).

The one place that reads and writes `bravo.watch_*`: the lane's side
(`WatchStore` of `dw_bravo.watch_lane`, bound to the one tenant whose Bravo
the gateway reaches) and the people's side (`BravoWatchStorePort`). The
gateway only reads `bravo.watch_pauses`, before each write. Every
transaction binds its tenant (`tenant_session`), and RLS is forced.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_bravo.watch import Component, Fingerprint
from dw_bravo.watch_lane import Environment
from dw_kernel.errors import ConflictError
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.domain.audit import AuditEvent
from dw_sales.adapters.persistence.uow import AuditFactory
from dw_sales.application.bravo_watch import WatchPause, WatchState


def _components(fingerprint: Fingerprint) -> str:
    return json.dumps(
        [
            {**asdict(c), "screens": sorted(c.screens), "unknown": list(c.unknown)}
            for c in fingerprint.components
        ]
    )


def _fingerprint(
    environment: str, taken_at: datetime, components: Sequence[Mapping[str, Any]]
) -> Fingerprint:
    return Fingerprint(
        "uat" if environment == "uat" else "production",
        taken_at,
        tuple(
            Component(
                kind=c["kind"],
                name=str(c["name"]),
                digest=str(c["digest"]),
                modified_at=c.get("modified_at"),
                modified_by=c.get("modified_by"),
                table=c.get("table"),
                screens=frozenset(c.get("screens") or ()),
                unknown=tuple(c.get("unknown") or ()),
            )
            for c in components
        ),
    )


_LATEST = sa.text(
    "SELECT id, digest, taken_at FROM bravo.watch_fingerprints WHERE environment = :environment"
    " ORDER BY taken_at DESC LIMIT 1"
)


@dataclass(frozen=True)
class SqlBravoWatch:
    session_factory: async_sessionmaker[AsyncSession]
    audit: AuditFactory

    # --------------------------------------------------------- the people

    async def state(self, tenant_id: uuid.UUID) -> WatchState:
        async with tenant_session(
            self.session_factory, TenantScope(tenant_id=tenant_id)
        ) as session:
            pauses = (
                (
                    await session.execute(
                        sa.text(
                            "SELECT kind, reasons, paused_at FROM bravo.watch_pauses ORDER BY kind"
                        )
                    )
                )
                .mappings()
                .all()
            )
            latest = (
                (await session.execute(_LATEST, {"environment": "production"})).mappings().first()
            )
            baseline = (
                (
                    await session.execute(
                        sa.text(
                            "SELECT fingerprint_id, accepted_at FROM bravo.watch_baselines"
                            " WHERE environment = 'production' ORDER BY accepted_at DESC LIMIT 1"
                        )
                    )
                )
                .mappings()
                .first()
            )
            read_at = await session.scalar(
                sa.text("SELECT read_at FROM bravo.watch_reads WHERE environment = 'production'")
            )
        return WatchState(
            pauses=tuple(
                WatchPause(p["kind"], tuple(p["reasons"]), p["paused_at"]) for p in pauses
            ),
            latest_fingerprint=latest["id"] if latest else None,
            latest_taken_at=latest["taken_at"] if latest else None,
            baseline_fingerprint=baseline["fingerprint_id"] if baseline else None,
            baseline_accepted_at=baseline["accepted_at"] if baseline else None,
            last_read=read_at,
        )

    async def accept(
        self,
        tenant_id: uuid.UUID,
        *,
        baseline_id: uuid.UUID,
        fingerprint_id: uuid.UUID,
        accepted_by: uuid.UUID,
        reason: str,
        at: datetime,
        audit: AuditEvent,
    ) -> None:
        async with tenant_session(
            self.session_factory, TenantScope(tenant_id=tenant_id)
        ) as session:
            latest = (
                (await session.execute(_LATEST, {"environment": "production"})).mappings().first()
            )
            if latest is None or latest["id"] != fingerprint_id:
                raise ConflictError(
                    "đây không còn là lần đo Bravo mới nhất: mở lại trang để xem lần mới nhất",
                    details={"fingerprint_id": str(fingerprint_id)},
                )
            await session.execute(
                sa.text(
                    "INSERT INTO bravo.watch_baselines (tenant_id, id, environment, fingerprint_id,"
                    " accepted_by, accepted_at, reason) VALUES (:tenant, :id, 'production',"
                    " :fingerprint, :by, :at, :reason)"
                ),
                {
                    "tenant": tenant_id,
                    "id": baseline_id,
                    "fingerprint": fingerprint_id,
                    "by": accepted_by,
                    "at": at,
                    "reason": reason,
                },
            )
            await session.execute(sa.text("DELETE FROM bravo.watch_pauses"))
            await self.audit(session).append(audit)

    # ------------------------------------------------------------ the lane

    def for_tenant(self, tenant_id: uuid.UUID) -> LaneStore:
        return LaneStore(self.session_factory, tenant_id)


@dataclass(frozen=True)
class LaneStore:
    """`dw_bravo.watch_lane.WatchStore` for the one tenant whose Bravo it is."""

    session_factory: async_sessionmaker[AsyncSession]
    tenant_id: uuid.UUID

    def _bound(self) -> TenantScope:
        return TenantScope(tenant_id=self.tenant_id)

    async def last_read(self, environment: Environment) -> datetime | None:
        async with tenant_session(self.session_factory, self._bound()) as session:
            return await session.scalar(  # type: ignore[no-any-return]
                sa.text("SELECT read_at FROM bravo.watch_reads WHERE environment = :e"),
                {"e": environment},
            )

    async def baseline(self, environment: Environment) -> Fingerprint | None:
        async with tenant_session(self.session_factory, self._bound()) as session:
            row = (
                (
                    await session.execute(
                        sa.text(
                            "SELECT f.environment, f.taken_at, f.components"
                            " FROM bravo.watch_baselines b JOIN bravo.watch_fingerprints f"
                            " ON f.tenant_id = b.tenant_id AND f.id = b.fingerprint_id"
                            " WHERE b.environment = :e ORDER BY b.accepted_at DESC LIMIT 1"
                        ),
                        {"e": environment},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return _fingerprint(row["environment"], row["taken_at"], row["components"])

    async def record(self, fingerprint: Fingerprint, digest: str) -> uuid.UUID:
        async with tenant_session(self.session_factory, self._bound()) as session:
            await session.execute(
                sa.text(
                    "INSERT INTO bravo.watch_reads (tenant_id, environment, read_at)"
                    " VALUES (:t, :e, :at) ON CONFLICT (tenant_id, environment)"
                    " DO UPDATE SET read_at = excluded.read_at"
                ),
                {"t": self.tenant_id, "e": fingerprint.environment, "at": fingerprint.taken_at},
            )
            latest = (
                (await session.execute(_LATEST, {"environment": fingerprint.environment}))
                .mappings()
                .first()
            )
            if latest is not None and latest["digest"] == digest:
                return latest["id"]  # type: ignore[no-any-return]
            new_id = uuid.uuid4()
            await session.execute(
                sa.text(
                    "INSERT INTO bravo.watch_fingerprints"
                    " (tenant_id, id, environment, taken_at, digest, components)"
                    " VALUES (:t, :id, :e, :at, :d, CAST(:c AS jsonb))"
                ),
                {
                    "t": self.tenant_id,
                    "id": new_id,
                    "e": fingerprint.environment,
                    "at": fingerprint.taken_at,
                    "d": digest,
                    "c": _components(fingerprint),
                },
            )
            return new_id

    async def pause(
        self, paused: Mapping[str, Sequence[str]], fingerprint_id: uuid.UUID | None, at: datetime
    ) -> None:
        async with tenant_session(self.session_factory, self._bound()) as session:
            for kind, reasons in sorted(paused.items()):
                await session.execute(
                    sa.text(
                        "INSERT INTO bravo.watch_pauses"
                        " (tenant_id, kind, reasons, fingerprint_id, paused_at)"
                        " VALUES (:t, :k, CAST(:r AS jsonb), :f, :at)"
                        " ON CONFLICT (tenant_id, kind) DO UPDATE SET reasons = ("
                        "  SELECT jsonb_agg(DISTINCT x) FROM jsonb_array_elements_text("
                        "   bravo.watch_pauses.reasons || excluded.reasons) AS x)"
                    ),
                    {
                        "t": self.tenant_id,
                        "k": kind,
                        "r": json.dumps(list(reasons)),
                        "f": fingerprint_id,
                        "at": at,
                    },
                )

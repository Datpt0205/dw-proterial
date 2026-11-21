"""The `bravo_watch` lane's adapters (ticket 65): the gateway's fingerprint
over HTTP, and the announcement to the watch's readers, audited as the lane.

The lane itself is `dw_bravo.watch_lane.BravoWatch`; the worker composes it
with these and `SqlBravoWatch.for_tenant` for the one tenant whose Bravo the
gateway reaches.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_bravo.watch import Component, Fingerprint, Notice, Replay
from dw_bravo.watch_lane import BRAVO_WATCH_LANE, Environment, FingerprintUnavailableError
from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import lane_audit_event, system_actor
from dw_sales.adapters.persistence.uow import AuditFactory
from dw_sales.application.access import SalesScopes
from dw_sales.application.ports import NotificationSenderPort, ScopeHoldersPort

WATCH_LINK: Final = "/sales/settings"
_TITLES: Final = {
    "pause": "Bravo thay đổi: tạm dừng ghi",
    "info": "Bravo thay đổi: DW1 vẫn ghi theo luật mới",
    "early_warning": "Bravo UAT khác bản thật",
    "could_not_check": "Chưa đọc được Bravo",
}
_ORDER: Final = ("pause", "could_not_check", "early_warning", "info")


@dataclass(frozen=True)
class GatewayFingerprints:
    """`FingerprintSource` over the gateway's `/v1/fingerprint/<env>`.

    The nightly replay of recorded saves is not built yet, so `replays`
    answers nothing: a changed layout pauses its screen until a person
    accepts it (fail closed)."""

    client: httpx.AsyncClient
    base_url: str
    timeout_seconds: float = 30.0

    async def fingerprint(self, environment: Environment) -> Fingerprint:
        try:
            response = await self.client.get(
                f"{self.base_url.rstrip('/')}/v1/fingerprint/{environment}",
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as failed:
            raise FingerprintUnavailableError(type(failed).__name__) from None
        if response.status_code != 200:
            raise FingerprintUnavailableError(f"gateway answered {response.status_code}")
        return parse_fingerprint(response.json())

    async def replays(self) -> Mapping[str, Replay]:
        return {}


def parse_fingerprint(body: Mapping[str, Any]) -> Fingerprint:
    try:
        return Fingerprint(
            "uat" if body["environment"] == "uat" else "production",
            datetime.fromisoformat(body["taken_at"]),
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
                for c in body["components"]
            ),
        )
    except (KeyError, TypeError, ValueError):
        raise FingerprintUnavailableError("the gateway's fingerprint is malformed") from None


@dataclass(frozen=True)
class WatchAnnouncer:
    """`Announcer`: the holders of `sales.bravo.watch.read` told once per key,
    and the telling audited as the lane (`system:bravo_watch`)."""

    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    holders: ScopeHoldersPort
    notices: NotificationSenderPort
    session_factory: async_sessionmaker[AsyncSession]
    audit: AuditFactory

    async def tell(self, notices: Sequence[Notice], key: str) -> None:
        level = next(lv for lv in _ORDER if any(n.level == lv for n in notices))
        recipients = await self.holders.holding(
            self.tenant_id, self.workspace_id, frozenset({SalesScopes.BRAVO_WATCH_READ.value})
        )
        body = "\n".join(
            f"- {n.text}" + (f" ({', '.join(n.kinds)})" if n.kinds else "") for n in notices
        )[:2000]
        if recipients:
            await self.notices.deliver(
                AccessContext(
                    tenant_id=self.tenant_id,
                    workspace_id=self.workspace_id,
                    principal_id=system_actor(BRAVO_WATCH_LANE).value,
                    roles=frozenset(),
                    scopes=frozenset(),
                    plan_id="background",
                ),
                recipients=recipients,
                source_key=f"sales.bravo.watch:{key}",
                title=_TITLES[level],
                body=body,
                link=WATCH_LINK,
            )
        async with tenant_session(
            self.session_factory,
            TenantScope(tenant_id=self.tenant_id, workspace_id=self.workspace_id),
        ) as session:
            await self.audit(session).append(
                lane_audit_event(
                    lane=BRAVO_WATCH_LANE,
                    event_id=uuid.uuid4(),
                    tenant_id=TenantId(self.tenant_id),
                    workspace_id=WorkspaceId(self.workspace_id),
                    action=f"sales.bravo.watch.{level}",
                    resource_type="bravo_watch",
                    resource_id=key[:64],
                    occurred_at=datetime.now().astimezone(),
                    details={
                        "notices": [n.level for n in notices],
                        "kinds": sorted({k for n in notices for k in n.kinds}),
                        "told": len(recipients),
                    },
                )
            )

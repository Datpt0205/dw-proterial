"""`NoticesPort` over the platform's in-app inbox: who holds a scope is the
platform's `holding` (the function every access context is built by), and
delivery is the platform's notification store, once per source key."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from dw_platform.application.access_context import AccessContext


class _Holders(Protocol):
    async def holding(
        self, tenant_id: uuid.UUID, workspace_id: uuid.UUID, scopes: frozenset[str]
    ) -> list[uuid.UUID]: ...


class _Inbox(Protocol):
    async def deliver(
        self,
        context: AccessContext,
        *,
        recipients: Sequence[uuid.UUID],
        source_key: str,
        title: str,
        body: str,
        link: str | None,
    ) -> None: ...


@dataclass(frozen=True)
class PlatformNotices:
    """Implements `NoticesPort`."""

    holders: _Holders
    inbox: _Inbox

    async def tell(
        self,
        context: AccessContext,
        *,
        scopes: frozenset[str],
        people: Sequence[uuid.UUID] = (),
        excluding: Sequence[uuid.UUID] = (),
        source_key: str,
        title: str,
        body: str,
        link: str | None,
    ) -> None:
        holding = (
            await self.holders.holding(context.tenant_id, context.workspace_id, scopes)
            if scopes
            else []
        )
        recipients = sorted({*holding, *people} - set(excluding), key=str)
        if not recipients:
            return
        await self.inbox.deliver(
            context,
            recipients=recipients,
            source_key=source_key,
            title=title[:200],
            body=body[:1000],
            link=link,
        )

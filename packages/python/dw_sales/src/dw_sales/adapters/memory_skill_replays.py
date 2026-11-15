"""Replays of proposed skill versions in memory, for the eval world and the
tests (ticket 40): `SqlSkillReplays`' contract, one tenant's rows apart from
another's as the table's policy keeps them."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from dw_platform.domain.audit import AuditEvent
from dw_sales.application.ports import SalesScope
from dw_sales.application.skills import SkillReplay


@dataclass
class MemorySkillReplays:
    """Implements `SkillReplayStorePort`, keyed by tenant then version."""

    held: dict[uuid.UUID, dict[uuid.UUID, SkillReplay]] = field(default_factory=dict)
    audits: list[AuditEvent] = field(default_factory=list)

    async def stored(
        self, scope: SalesScope, version_ids: Sequence[uuid.UUID]
    ) -> Mapping[uuid.UUID, SkillReplay]:
        own = self.held.get(scope.tenant_id.value, {})
        return {v: own[v] for v in version_ids if v in own}

    async def store(self, scope: SalesScope, replay: SkillReplay, audit: AuditEvent) -> bool:
        own = self.held.setdefault(scope.tenant_id.value, {})
        if replay.version_id in own:
            return False
        own[replay.version_id] = replay
        self.audits.append(audit)
        return True

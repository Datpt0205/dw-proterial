"""`NotationLedgerPort` in memory, for the unit tests and the evals: the same
contract as `SqlCustomerNotations` (one entry per customer and kind in one
scope, replaced only where its value or source changes, an audit event for
each write and none otherwise), keyed by the scope so another tenant's or
workspace's entries are never another's."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from dw_platform.domain.audit import AuditEvent
from dw_platform.domain.notation import NotationKind
from dw_sales.application.ports import SalesScope
from dw_sales.domain.customer_notation import NotationEntry

_Key = tuple[object, object, str, str]


@dataclass
class MemoryCustomerNotations:
    """Implements `NotationLedgerPort`."""

    rows: dict[_Key, NotationEntry] = field(default_factory=dict)
    events: list[AuditEvent] = field(default_factory=list)

    @classmethod
    def seeded(
        cls, scope: SalesScope, records: Mapping[str, Mapping[str, str]]
    ) -> MemoryCustomerNotations:
        """Each customer's kinds as a person set them, in ``scope``: the
        records an eval or a test reads with."""
        held = cls()
        for customer, kinds in records.items():
            for kind, value in kinds.items():
                entry = NotationEntry.model_validate(
                    {
                        "customer_code": customer,
                        "kind": kind,
                        "value": value,
                        "source": "set",
                        "by": uuid.UUID(int=0xA1),
                        "at": datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
                    }
                )
                held.rows[cls._key(scope, customer, kind)] = entry
        return held

    @staticmethod
    def _key(scope: SalesScope, customer_code: str, kind: str) -> _Key:
        return (scope.tenant_id.value, scope.workspace_id.value, customer_code, kind)

    async def entries(self, scope: SalesScope, customer_code: str) -> Sequence[NotationEntry]:
        mine = (scope.tenant_id.value, scope.workspace_id.value, customer_code)
        return sorted(
            (entry for key, entry in self.rows.items() if key[:3] == mine), key=lambda e: e.kind
        )

    async def keep(self, scope: SalesScope, entry: NotationEntry, event: AuditEvent) -> bool:
        key = self._key(scope, entry.customer_code, entry.kind)
        held = self.rows.get(key)
        if held is not None and (held.value, held.source) == (entry.value, entry.source):
            return False
        self.rows[key] = entry
        self.events.append(event)
        return True

    async def forget(
        self, scope: SalesScope, customer_code: str, kind: NotationKind, event: AuditEvent
    ) -> bool:
        if self.rows.pop(self._key(scope, customer_code, kind), None) is None:
            return False
        self.events.append(event)
        return True

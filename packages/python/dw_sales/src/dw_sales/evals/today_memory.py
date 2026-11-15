"""`ReminderMarkStoreFactory` in memory (tickets 47 and 48), for the eval
world and the unit tests: each person's marks apart, as the table's RLS keeps
them, and the customer's term refused as its CHECK refuses it."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from dw_platform.application.access_context import AccessContext
from dw_sales.application.today import Mark, ReminderMark, ReminderMarkStorePort
from dw_sales.domain.followups import CUSTOMER_TERM

_Owner = tuple[uuid.UUID, uuid.UUID, uuid.UUID]


@dataclass
class _Store:
    held: dict[uuid.UUID, ReminderMark]

    async def marks(self) -> Sequence[ReminderMark]:
        return sorted(self.held.values(), key=lambda m: (m.marked_at, m.notification_id))

    async def put(self, mark: ReminderMark) -> None:
        if mark.followup in CUSTOMER_TERM and mark.mark is not Mark.DONE:
            # `ck_reminder_marks_customer_term`.
            raise ValueError("a customer's term is marked done, or not at all")
        self.held[mark.notification_id] = mark


@dataclass
class MemoryReminderMarks:
    by_person: dict[_Owner, dict[uuid.UUID, ReminderMark]] = field(default_factory=dict)

    @asynccontextmanager
    async def __call__(self, context: AccessContext) -> AsyncIterator[ReminderMarkStorePort]:
        owner = (context.tenant_id, context.workspace_id, context.principal_id)
        yield _Store(self.by_person.setdefault(owner, {}))

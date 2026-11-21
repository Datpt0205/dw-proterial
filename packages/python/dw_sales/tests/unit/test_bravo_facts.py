"""Ticket 50: how fresh DW's copy of Bravo's facts is, per table, for whoever
may read cases; never read for, or by, another tenant."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from dw_kernel.errors import PermissionDeniedError
from dw_kernel.ports import FixedClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_sales.application.access import Gate
from dw_sales.application.bravo_facts import BravoFactsService, TableState

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 21, 3, tzinfo=UTC)
TENANT = uuid.uuid4()


class _Store:
    def __init__(self) -> None:
        self.asked: list[uuid.UUID] = []

    async def state(self, tenant_id: uuid.UUID) -> list[TableState]:
        self.asked.append(tenant_id)
        return [
            TableState("B20LME", 10, 0, NOW - timedelta(minutes=10), NOW, None, None),
            TableState(
                "B20BlackList", 5, 1, NOW - timedelta(hours=3), NOW, "Bravo did not answer", NOW
            ),
        ]


def _context(*scopes: str) -> AccessContext:
    return AccessContext(
        tenant_id=TENANT,
        workspace_id=uuid.uuid4(),
        principal_id=uuid.uuid4(),
        roles=frozenset(),
        scopes=frozenset(scopes),
        plan_id="professional",
    )


async def test_each_table_says_when_bravo_was_read_and_whether_that_is_stale() -> None:
    store = _Store()
    service = BravoFactsService(store, Gate(ScopeAuthorizationService()), FixedClock(NOW))

    views = await service.state(_context("sales.case.read"))

    assert [(v.table, v.stale) for v in views] == [("B20LME", False), ("B20BlackList", True)]
    assert views[1].last_error == "Bravo did not answer" and store.asked == [TENANT]


async def test_without_the_right_to_read_cases_nothing_is_read() -> None:
    store = _Store()
    service = BravoFactsService(store, Gate(ScopeAuthorizationService()), FixedClock(NOW))

    with pytest.raises(PermissionDeniedError):
        await service.state(_context())
    assert store.asked == []

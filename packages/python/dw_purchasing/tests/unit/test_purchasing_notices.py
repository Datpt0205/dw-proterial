"""DW2's notices over the platform's inbox: the scope's holders and the
people named, never those excluded, once per key; nobody, no delivery."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest

from dw_purchasing.adapters.notices import PlatformNotices
from dw_purchasing.testing.world import caller

pytestmark = pytest.mark.unit

A, B, C = (uuid.UUID(int=n) for n in (1, 2, 3))


@dataclass
class Holders:
    asked: list[frozenset[str]] = field(default_factory=list)

    async def holding(
        self, tenant_id: uuid.UUID, workspace_id: uuid.UUID, scopes: frozenset[str]
    ) -> list[uuid.UUID]:
        self.asked.append(scopes)
        return [A, B]


@dataclass
class Inbox:
    sent: list[dict[str, Any]] = field(default_factory=list)

    async def deliver(self, context: Any, *, recipients: Sequence[uuid.UUID], **rest: Any) -> None:
        self.sent.append({"recipients": list(recipients), **rest})


async def test_holders_and_people_are_told_and_the_excluded_never() -> None:
    holders, inbox = Holders(), Inbox()
    notices = PlatformNotices(holders, inbox)
    await notices.tell(
        caller(),
        scopes=frozenset({"purchasing.approve.tier1"}),
        people=(C,),
        excluding=(B,),
        source_key="k",
        title="t" * 300,
        body="b",
        link="/purchasing",
    )
    (sent,) = inbox.sent
    assert sent["recipients"] == sorted([A, C], key=str)
    assert len(sent["title"]) == 200 and sent["source_key"] == "k"


async def test_nobody_to_tell_delivers_nothing() -> None:
    inbox = Inbox()
    notices = PlatformNotices(Holders(), inbox)
    await notices.tell(
        caller(),
        scopes=frozenset(),
        excluding=(A,),
        source_key="k",
        title="t",
        body="b",
        link=None,
    )
    assert inbox.sent == []

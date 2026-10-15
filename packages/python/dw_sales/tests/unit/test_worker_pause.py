"""The stop control's pause and its notification (ticket 05).

A pause commits before its notification is sent. A notification that then
fails must not turn the committed pause into an error: the caller would be
told DW1 is not paused while it is, and their retry refused as a second pause.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from dw_platform.application.access_context import AccessContext
from dw_sales.evals.graders import AN, CALLERS
from dw_sales.evals.world import ALPHA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS)


class _InboxDown:
    """`NotificationSenderPort` whose delivery fails, as an outage would."""

    async def deliver(
        self,
        context: AccessContext,
        *,
        recipients: Sequence[uuid.UUID],
        source_key: str,
        title: str,
        body: str,
        link: str | None,
    ) -> None:
        raise RuntimeError("the notification inbox is down")


async def test_a_pause_notifies_the_heads_who_may_resume() -> None:
    world = _world()

    view = await world.services.worker.pause(AN.context(), None)

    assert view.paused
    (told,) = world.notifications.sent
    assert told.title == "DW1 đã tạm dừng" and told.recipients


async def test_a_pause_whose_notification_fails_is_still_a_pause(
    caplog: pytest.LogCaptureFixture,
) -> None:
    world = _world()
    worker = replace(world.services.worker, notifications=_InboxDown())

    view = await worker.pause(AN.context(), "kiểm tra hộp thư")

    assert view.paused
    assert (await world.services.worker.state(AN.context())).paused
    actions = [row.action for row in world.audit(ALPHA)]
    assert actions.count("sales.worker.paused") == 1
    assert "notification failed" in caplog.text

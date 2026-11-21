"""The `bravo_watch` lane ticks on its schedule only (sales ticket 65)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dw_worker.consumers.bravo_watch import build_bravo_watch_consumer, due

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("utc_hour", "minute", "expected"),
    [(0, 0, True), (11, 59, True), (12, 0, False), (19, 10, True), (19, 40, False), (23, 0, False)],
    ids=["07h", "18h59", "19h", "02h10", "02h40", "06h"],
)
def test_due_in_working_hours_and_once_at_night(utc_hour: int, minute: int, expected: bool) -> None:
    assert due(datetime(2026, 11, 21, utc_hour, minute, tzinfo=UTC)) is expected


async def test_a_tick_outside_the_schedule_does_nothing() -> None:
    ticks: list[datetime] = []

    class Watch:
        async def tick(self, now: datetime) -> None:
            ticks.append(now)

    night = datetime(2026, 11, 21, 15, tzinfo=UTC)  # 22:00 in Vietnam
    morning = datetime(2026, 11, 21, 2, tzinfo=UTC)  # 09:00 in Vietnam
    await build_bravo_watch_consumer(Watch(), lambda: night)()
    await build_bravo_watch_consumer(Watch(), lambda: morning)()

    assert ticks == [morning]


def test_empty_watch_settings_from_compose_read_as_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dw_worker.settings import WorkerSettings

    for name in ("BRAVO_GATEWAY_URL", "BRAVO_TENANT_ID", "BRAVO_WORKSPACE_ID"):
        monkeypatch.setenv(f"DW_WORKER_{name}", "")

    settings = WorkerSettings()

    assert (settings.bravo_gateway_url, settings.bravo_tenant_id, settings.bravo_workspace_id) == (
        None,
        None,
        None,
    )

"""The stop control (spec "Who may stop DW1"): any PIC pauses DW1, only the
head resumes it, and pausing tells the people who can resume it, and nobody
else, who paused and when."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sales_api_harness import AN, DIEU, GIANG, HA, Api, user_id
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration


async def _recipients(migrator: AsyncEngine) -> set[object]:
    async with migrator.connect() as conn:
        rows = await conn.execute(
            sa.text(
                "SELECT recipient_user_id, title, body FROM platform.notifications"
                " WHERE source_key LIKE 'sales.worker.paused:%'"
            )
        )
        return {row.recipient_user_id for row in rows}


async def test_an_pauses_dw1_and_only_the_holders_of_resume_are_told(
    api: Api, migrator: AsyncEngine
) -> None:
    an = api.as_(AN)

    paused = await an.post("/worker/pause", {"reason": "Kiểm tra lại convert list"})

    assert paused.status_code == 200, paused.text
    assert paused.json()["paused"] is True
    assert paused.json()["changed_by"] == str(user_id(AN))
    assert await _recipients(migrator) == {user_id(GIANG)}
    inbox = await api.as_(GIANG).platform("/notifications")
    (note,) = [n for n in inbox.json()["items"] if n["title"] == "DW1 đã tạm dừng"]
    assert "Nguyễn Văn An" in note["body"] and "giờ Việt Nam" in note["body"]


async def test_processing_is_refused_while_paused_naming_who_and_when(api: Api) -> None:
    an, dieu = api.as_(AN), api.as_(DIEU)
    await an.post("/worker/pause")

    one = await dieu.post("/inbox/M01/process")
    every = await dieu.post("/inbox/process-all")

    for refused in (one, every):
        assert refused.status_code == 409
        assert refused.json()["details"]["paused_by"] == str(user_id(AN))
        assert refused.json()["details"]["paused_at"]


async def test_a_pic_cannot_resume_and_the_head_resumes_with_a_reason(
    api: Api, migrator: AsyncEngine
) -> None:
    an, giang = api.as_(AN), api.as_(GIANG)
    await an.post("/worker/pause")

    by_pic = await an.post("/worker/resume", {"reason": "Đã kiểm tra xong"})
    assert by_pic.status_code == 403

    no_reason = await giang.post("/worker/resume", {})
    assert no_reason.status_code == 422

    resumed = await giang.post("/worker/resume", {"reason": "Đã kiểm tra xong"})
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["paused"] is False
    assert (await an.post("/inbox/M11/process")).status_code == 200

    async with migrator.connect() as conn:
        (details,) = (
            await conn.execute(
                sa.text(
                    "SELECT details FROM platform.audit_events"
                    " WHERE action = 'sales.worker.resumed' AND actor_id = :giang"
                    " ORDER BY occurred_at DESC LIMIT 1"
                ),
                {"giang": user_id(GIANG)},
            )
        ).one()
    assert details == {"reason": "Đã kiểm tra xong"}


async def test_the_viewer_can_neither_pause_nor_resume(api: Api) -> None:
    ha = api.as_(HA)

    assert (await ha.post("/worker/pause")).status_code == 403
    assert (await ha.post("/worker/resume", {"reason": "x"})).status_code == 403

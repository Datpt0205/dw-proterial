"""A routed message marked handled, through the API and in PostgreSQL
(2026-10-27; the in-memory rules are `dw_sales/tests/unit/test_routed_mail.py`).

- An marks the message routed to him handled: it leaves his `/my-work` and
  the overview's waiting count, and the inbox still lists it, saying who.
- Diệu, another PIC, is refused An's message at the route; a reopen by An
  puts it back.
- Processing a routed message again clears its mark (the log's upsert).
- The table refuses a mark on a message that is on a case, and a mark
  without its person, whatever role writes it.
- Another tenant's PIC finds no such message.
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from sales_api_harness import AN, BAO, BETA, DIEU, Api, Persona
from sales_flow import process
from sqlalchemy.exc import IntegrityError

from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.adapters.persistence.repositories import (
    SqlApprovalRepository,
    SqlAuditRepository,
)
from dw_platform.adapters.persistence.tenant_session import TenantScope, bind_tenant
from dw_platform.testing.seed_env import sid
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.case_store import MessageHandled
from dw_sales.application.ports import SalesScope

pytestmark = pytest.mark.integration

# From the sample mailbox: routed to An by address, and a PO that opens a case.
ANS = "M11"
ON_A_CASE = "M01"

ALPHA = SalesScope(
    TenantId(sid("tenant", "tenant-alpha")), WorkspaceId(sid("workspace", "tenant-alpha:main"))
)


async def _work_ids(persona: Persona) -> set[str]:
    response = await persona.get("/my-work")
    assert response.status_code == 200, response.text
    return {i["id"] for i in response.json()["items"] if i["kind"] == "message"}


async def _waiting(persona: Persona) -> int:
    response = await persona.get("/overview")
    assert response.status_code == 200, response.text
    waiting: int = response.json()["messages"]["routed_to_sales"]
    return waiting


async def _disposition(persona: Persona, message_id: str) -> dict[str, Any]:
    inbox = await persona.get("/inbox")
    assert inbox.status_code == 200, inbox.text
    found: dict[str, Any] = next(
        m["disposition"] for m in inbox.json() if m["message_id"] == message_id
    )
    return found


async def test_a_handled_message_leaves_the_work_list_and_is_reopened(api: Api) -> None:
    an, dieu = api.as_(AN), api.as_(DIEU)
    routed = await process(an, ANS)
    assert routed["kind"] == "routed_to_sales" and routed["owner"] == "an.nguyen@alpha.local"
    await process(an, ON_A_CASE)
    assert ANS in await _work_ids(an)
    before = await _waiting(an)

    # Diệu's is not this message: refused where the change is made.
    refused = await dieu.post(f"/inbox/{ANS}/handled", {"note": "của tôi"})
    assert refused.status_code == 403, refused.text

    done = await an.post(f"/inbox/{ANS}/handled", {"note": "Đã trả lời khách"})
    assert done.status_code == 200, done.text
    assert done.json()["handled_note"] == "Đã trả lời khách"
    assert ANS not in await _work_ids(an)
    assert await _waiting(an) == before - 1
    shown = await _disposition(an, ANS)
    assert shown["handled_by"] == str(an.id) and shown["handled_note"] == "Đã trả lời khách"

    # A message on a case is not marked: 409 naming the rule.
    on_case = await an.post(f"/inbox/{ON_A_CASE}/handled", {})
    assert on_case.status_code == 409, on_case.text
    assert on_case.json()["details"]["rule"] == "message_not_routed"

    reopened = await an.post(f"/inbox/{ANS}/reopen")
    assert reopened.status_code == 200, reopened.text
    assert ANS in await _work_ids(an)
    assert (await _disposition(an, ANS))["handled_at"] is None


async def test_processing_a_routed_message_again_opens_it(api: Api) -> None:
    an = api.as_(AN)
    await process(an, ANS)
    assert (await an.post(f"/inbox/{ANS}/handled", {})).status_code == 200
    uow = SqlSalesUnitOfWorkFactory(
        api.sessions, audit=SqlAuditRepository, approvals=SqlApprovalRepository
    )
    async with uow(ALPHA) as work:
        logged = await work.messages.logged(ANS)
        assert logged is not None and logged.handled is not None
        await work.messages.record(logged.disposition, logged.processed_at)
        await work.commit()
    async with uow(ALPHA) as work:
        again = await work.messages.logged(ANS)
        assert again is not None and again.handled is None
        # A message on a case takes no mark: the log says so, nothing written.
        assert not await work.messages.set_handled(
            ON_A_CASE, MessageHandled(by=an.id, at=logged.processed_at)
        )


async def test_the_table_refuses_a_mark_out_of_shape(api: Api) -> None:
    an = api.as_(AN)
    await process(an, ANS)
    await process(an, ON_A_CASE)
    scope = TenantScope(tenant_id=ALPHA.tenant_id.value, workspace_id=ALPHA.workspace_id.value)
    async with api.sessions() as session:
        for message_id, columns in (
            (ON_A_CASE, "handled_at = now(), handled_by = gen_random_uuid()"),
            (ANS, "handled_at = now()"),
            (ANS, "handled_note = 'x'"),
        ):
            with pytest.raises(IntegrityError, match="ck_messages_handled"):
                async with session.begin():
                    # Written past the service, as the application's role:
                    # the table holds the shape whoever writes it.
                    await bind_tenant(session, scope)
                    await session.execute(
                        sa.text(f"UPDATE sales.messages SET {columns} WHERE message_id = :m"),
                        {"m": message_id},
                    )


async def test_another_tenant_finds_no_such_message(api: Api) -> None:
    an = api.as_(AN)
    await process(an, ANS)
    outsider = api.as_(BAO, BETA)
    response = await outsider.post(f"/inbox/{ANS}/handled", {})
    assert response.status_code == 404, response.text

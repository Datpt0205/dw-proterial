"""A routed message marked handled, and opened again (2026-10-27), over the
in-memory world: who may, what leaves Việc cần làm and the overview's count,
and the audit row each change writes.

The SQL log's update, its CHECK and the work list's index are held to this by
`apps/api/tests/integration/test_sales_routed_mail_sql.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_sales.domain.dispositions import SALES_PIC_POOL, DispositionKind
from dw_sales.evals.graders import AN, CALLERS, DIEU, GIANG, READER
from dw_sales.evals.world import ALPHA, Caller, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS)


async def _routed(world: World) -> tuple[World, str, str, str]:
    """A world with its mailbox processed: one message routed to An, one to
    the PICs' pool, and one on a case."""
    await world.process_each(AN)
    held = world.store.state(ALPHA).messages
    routed = [m for m in held.values() if m.disposition.kind is DispositionKind.ROUTED_TO_SALES]
    ans = next(m for m in routed if m.disposition.owner == AN.email)
    pool = next(m for m in routed if m.disposition.owner == SALES_PIC_POOL)
    on_case = next(m for m in held.values() if m.disposition.case_id is not None)
    return (
        world,
        ans.disposition.message_id,
        pool.disposition.message_id,
        on_case.disposition.message_id,
    )


async def _work_ids(world: World, caller: Caller) -> set[str]:
    items = (await world.services.overview.my_work(caller.context())).items
    return {i.id for i in items if i.kind == "message"}


async def test_a_handled_message_leaves_the_work_list_and_comes_back_when_reopened() -> None:
    world, mine, _, _ = await _routed(_world())
    assert mine in await _work_ids(world, AN)
    before = (await world.services.overview.overview(AN.context())).messages.routed_to_sales

    view = await world.services.routed_mail.handle(AN.context(), mine, "  Đã trả lời khách  ")
    assert view.handled_by == AN.user_id
    assert view.handled_note == "Đã trả lời khách"
    assert mine not in await _work_ids(world, AN)
    after = (await world.services.overview.overview(AN.context())).messages.routed_to_sales
    assert after == before - 1
    # The inbox still holds it, saying who handled it.
    inbox = {m.message_id: m for m in await world.services.inbox.messages(AN.context())}
    assert inbox[mine].disposition.handled_by == AN.user_id
    assert inbox[mine].disposition.kind == DispositionKind.ROUTED_TO_SALES.value

    reopened = await world.services.routed_mail.reopen(AN.context(), mine)
    assert reopened.handled_at is None
    assert mine in await _work_ids(world, AN)

    actions = [e.action for e in world.audit() if e.resource_id == mine]
    assert actions[-2:] == ["sales.message.handled", "sales.message.reopened"]
    # The note is the person's words: the audit row says only that one was left.
    handled = next(e for e in world.audit() if e.action == "sales.message.handled")
    assert handled.details == {"note": True}


async def test_marking_it_twice_keeps_the_first_mark() -> None:
    world, mine, _, _ = await _routed(_world())
    first = await world.services.routed_mail.handle(AN.context(), mine, None)
    second = await world.services.routed_mail.handle(AN.context(), mine, "khác")
    assert second == first
    assert [e.action for e in world.audit() if e.resource_id == mine].count(
        "sales.message.handled"
    ) == 1


async def test_any_pic_handles_the_pools_mail_but_a_pics_only_they_and_the_head() -> None:
    world, mine, pool, _ = await _routed(_world())
    # The pool's message is every PIC's: Diệu marks it and opens it again.
    await world.services.routed_mail.handle(DIEU.context(), pool, None)
    await world.services.routed_mail.reopen(DIEU.context(), pool)
    # An's message is not Diệu's work: refused where the change is made.
    with pytest.raises(PermissionDeniedError):
        await world.services.routed_mail.handle(DIEU.context(), mine, None)
    with pytest.raises(PermissionDeniedError):
        await world.services.routed_mail.reopen(DIEU.context(), mine)
    # The head decides whose work any message is, so may close An's.
    view = await world.services.routed_mail.handle(GIANG.context(), mine, None)
    assert view.handled_by == GIANG.user_id


async def test_someone_who_does_not_handle_the_mailbox_marks_nothing() -> None:
    world, _, pool, _ = await _routed(_world())
    with pytest.raises(PermissionDeniedError):
        await world.services.routed_mail.handle(READER.context(), pool, None)
    assert not [e for e in world.audit() if e.action == "sales.message.handled"]


async def test_a_message_on_a_case_or_unknown_is_refused() -> None:
    world, _, _, on_case = await _routed(_world())
    with pytest.raises(ConflictError) as refused:
        await world.services.routed_mail.handle(AN.context(), on_case, None)
    assert refused.value.details["rule"] == "message_not_routed"
    with pytest.raises(NotFoundError):
        await world.services.routed_mail.handle(AN.context(), "M-none", None)

"""The head reassigns a case (ticket 17, G22), over the in-memory world.

The API suite (`test_sales_api_assignment.py`) repeats what the database or
a route could break: the grant, the stored assignee, another tenant.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from dw_kernel.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    PermissionDeniedError,
)
from dw_platform.application.access_context import SupportScope
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import CloseReason
from dw_sales.evals.graders import AN, CALLERS, DIEU, GIANG, KHOA, READER
from dw_sales.evals.world import ALPHA, BETA, Caller, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS)


async def _order(world: World) -> uuid.UUID:
    """M01, opened and handed to its customer's Sales PIC (An)."""
    seen = await world.process_each(AN, ["M01"])
    case_id = seen["M01"][0].case_id
    assert case_id is not None
    return case_id


def _assigned(world: World, case_id: uuid.UUID) -> uuid.UUID | None:
    return world.store.state(ALPHA).orders[case_id].origin.assigned_to


async def _reassign(
    world: World,
    caller: Caller,
    case_id: uuid.UUID,
    assignee: uuid.UUID | None,
    kind: CaseKind = CaseKind.ORDER,
) -> None:
    case = world.order(case_id) if kind is CaseKind.ORDER else world.quote(case_id)
    await world.services.assignment.reassign(
        caller.context(), kind, case_id, assignee=assignee, case_version=case.case_version
    )


async def _work(world: World, caller: Caller, case_id: uuid.UUID) -> set[str]:
    items = await world.services.overview.my_work(caller.context())
    return {i.action for i in items if i.id == str(case_id)}


# ------------------------------------------ the head gives it to Diệu --


async def test_the_head_gives_an_order_to_another_pic_and_the_work_follows() -> None:
    world = _world()
    case_id = await _order(world)
    assert _assigned(world, case_id) == AN.user_id
    before = world.order(case_id).case_version
    assert await _work(world, AN, case_id) == {"self_check"}

    await _reassign(world, GIANG, case_id, DIEU.user_id)

    assert _assigned(world, case_id) == DIEU.user_id
    assert world.order(case_id).case_version == before + 1
    # My work follows the new assignee; the old one no longer sees it.
    assert await _work(world, DIEU, case_id) == {"self_check"}
    assert await _work(world, AN, case_id) == set()
    (row,) = [e for e in world.audit() if e.action == "sales.order.reassigned"]
    assert row.actor_id.value == GIANG.user_id
    assert row.details["assigned_from"] == str(AN.user_id)
    assert row.details["assigned_to"] == str(DIEU.user_id)
    assert row.details["case_version"] == before + 1
    (told,) = world.notifications.sent
    assert told.recipients == (DIEU.user_id,)
    assert told.source_key == f"sales.case.assigned:{case_id}:{before + 1}"
    assert told.link == f"/sales/orders/{case_id}"


async def test_null_unassigns_and_every_pic_may_take_it() -> None:
    world = _world()
    case_id = await _order(world)

    await _reassign(world, GIANG, case_id, None)

    assert _assigned(world, case_id) is None
    assert await _work(world, DIEU, case_id) == {"self_check"}
    assert await _work(world, AN, case_id) == {"self_check"}
    assert world.notifications.sent == []


async def test_a_quote_is_reassigned_the_same_way() -> None:
    world = _world()
    seen = await world.process_each(DIEU, ["M10"])
    case_id = seen["M10"][0].case_id
    assert case_id is not None

    await _reassign(world, GIANG, case_id, KHOA.user_id, CaseKind.QUOTE)

    assert world.store.state(ALPHA).quotes[case_id].origin.assigned_to == KHOA.user_id
    (told,) = world.notifications.sent
    assert told.link == f"/sales/quotes/{case_id}"


async def test_the_candidates_are_who_works_the_case_here() -> None:
    world = _world()
    case_id = await _order(world)

    listed = await world.services.assignment.candidates(GIANG.context(), CaseKind.ORDER, case_id)

    # Every PIC and the head hold `sales.order.prepare`; the viewer does not.
    assert {m.user_id for m in listed} == {AN.user_id, DIEU.user_id, GIANG.user_id, KHOA.user_id}


# ------------------------------------------------------- refusals --


async def test_a_pic_may_not_reassign() -> None:
    world = _world()
    case_id = await _order(world)

    with pytest.raises(PermissionDeniedError):
        await _reassign(world, AN, case_id, DIEU.user_id)
    with pytest.raises(PermissionDeniedError):
        await world.services.assignment.candidates(AN.context(), CaseKind.ORDER, case_id)
    assert _assigned(world, case_id) == AN.user_id


@pytest.mark.parametrize(
    "assignee",
    [
        READER.user_id,  # a member without the scope that works an order
        uuid.UUID(int=0xB0),  # another tenant's PIC
        uuid.uuid4(),  # nobody at all
    ],
)
async def test_an_assignee_who_does_not_work_orders_here_is_refused(assignee: uuid.UUID) -> None:
    world = _world()
    case_id = await _order(world)

    with pytest.raises(DomainError) as refused:
        await _reassign(world, GIANG, case_id, assignee)

    assert refused.value.details == {"field": "assignee", "rule": "assignee_not_eligible"}
    assert _assigned(world, case_id) == AN.user_id
    assert world.notifications.sent == []


async def test_a_stale_version_is_refused() -> None:
    world = _world()
    case_id = await _order(world)

    with pytest.raises(ConflictError) as refused:
        await world.services.assignment.reassign(
            GIANG.context(),
            CaseKind.ORDER,
            case_id,
            assignee=DIEU.user_id,
            case_version=world.order(case_id).case_version - 1,
        )
    assert refused.value.details["rule"] == "stale_case_version"


async def test_a_closed_case_is_refused() -> None:
    world = _world()
    case_id = await _order(world)
    await world.services.order_commands.close(
        AN.context(),
        case_id,
        case_version=world.order(case_id).case_version,
        reason=CloseReason.NOT_AN_ORDER,
        superseded_by=None,
    )

    with pytest.raises(ConflictError) as refused:
        await _reassign(world, GIANG, case_id, DIEU.user_id)
    assert refused.value.details["rule"] == "case_closed"


async def test_a_support_context_may_not_reassign_whatever_its_grant_stamped() -> None:
    world = _world()
    case_id = await _order(world)
    support = GIANG.context().model_copy(
        update={
            "support": SupportScope(
                grant_id=uuid.uuid4(),
                code="SUP-0001",
                resource_type="workspace",
                resource_id=None,
                scope_set_key="sales_support",
            )
        }
    )

    with pytest.raises(PermissionDeniedError):
        await world.services.assignment.reassign(
            support,
            CaseKind.ORDER,
            case_id,
            assignee=DIEU.user_id,
            case_version=world.order(case_id).case_version,
        )
    assert _assigned(world, case_id) == AN.user_id


async def test_another_workspaces_case_is_not_found() -> None:
    world = _world()
    case_id = await _order(world)

    with pytest.raises(NotFoundError):
        await world.services.assignment.reassign(
            GIANG.context(BETA),
            CaseKind.ORDER,
            case_id,
            assignee=None,
            case_version=world.order(case_id).case_version,
        )
    with pytest.raises(NotFoundError):
        await world.services.assignment.candidates(GIANG.context(BETA), CaseKind.ORDER, case_id)

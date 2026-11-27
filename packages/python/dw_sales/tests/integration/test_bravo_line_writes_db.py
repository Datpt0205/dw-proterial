"""Bravo line writes on a migrated PostgreSQL (ticket 53, af89f3f5d27d): one
open proposal per line held by the database, a settled row naming who and
when, a proposal of another tenant or workspace neither read nor settled."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sales_harness import OrderRun, World

from dw_kernel.errors import ConflictError
from dw_kernel.ids import UserId
from dw_platform.domain.approval import ApprovalRequest
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.bravo_line_writes import (
    BRAVO_WRITE_APPROVAL,
    CANCEL_REASON_CHARS,
    BravoLineWrite,
)
from dw_sales.application.ports import SalesScope

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 21, 9, tzinfo=UTC)
PIC = uuid.uuid4()


def _case_id(small_run: OrderRun) -> uuid.UUID:
    case = small_run.outcomes["M01"].case
    assert case is not None
    return case.case_id


async def _proposed(
    uow: SqlSalesUnitOfWorkFactory,
    scope: SalesScope,
    case_id: uuid.UUID,
    line_no: int = 1,
    *,
    after: str = "2026-12-08",
) -> BravoLineWrite:
    approval_id = uuid.uuid4()
    write = BravoLineWrite(
        approval_id=approval_id,
        case_id=case_id,
        line_no=line_no,
        so_no="SO2611-000161",
        item_code="PRV-1",
        field="confirmed_date",
        before="2026-12-01",
        after=after,
        kind="so.line.set_confirmed_date@1",
        command={"line": {"so_id": 10}, "confirmed_date": "2026-12-08"},
        content_hash="a" * 64,
        target="uat",
        proposed_by=PIC,
        proposed_at=NOW,
    )
    async with uow(scope) as work:
        await work.approvals.add(
            ApprovalRequest(
                id=approval_id,
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                approval_type=BRAVO_WRITE_APPROVAL,
                requested_by=UserId(PIC),
                reason="test",
                payload={"makers": []},
                required_scope="sales.bravo.write",
            )
        )
        await work.bravo_writes.add(write)
        await work.commit()
    return write


def _settled(write: BravoLineWrite) -> BravoLineWrite:
    return write.model_copy(update={"status": "written", "decided_by": PIC, "settled_at": NOW})


async def test_one_open_proposal_per_line_and_a_settled_one_frees_it(
    small_run: OrderRun, world: World, uow: SqlSalesUnitOfWorkFactory
) -> None:
    case_id = _case_id(small_run)
    first = await _proposed(uow, world.alpha, case_id)

    with pytest.raises(ConflictError) as refused:
        await _proposed(uow, world.alpha, case_id)
    assert refused.value.details["rule"] == "bravo_write_open"

    async with uow(world.alpha) as work:
        await work.bravo_writes.save(_settled(first), expected="proposed")
        await work.commit()
    await _proposed(uow, world.alpha, case_id)
    async with uow(world.alpha) as work:
        held = await work.bravo_writes.of_case(case_id)
    assert sorted(w.status for w in held) == ["proposed", "written"]


async def test_a_settled_row_names_who_and_when(
    small_run: OrderRun, world: World, uow: SqlSalesUnitOfWorkFactory
) -> None:
    write = await _proposed(uow, world.alpha, _case_id(small_run), line_no=2)

    async with uow(world.alpha) as work:
        with pytest.raises(ConflictError) as refused:
            await work.bravo_writes.save(
                write.model_copy(update={"status": "written"}), expected="proposed"
            )
    assert refused.value.details["constraint"] == "ck_bravo_line_writes_settled"
    async with uow(world.alpha) as work:
        await work.bravo_writes.save(_settled(write), expected="proposed")
        await work.commit()
    async with uow(world.alpha) as work:
        with pytest.raises(ConflictError):  # settled meanwhile
            await work.bravo_writes.save(_settled(write), expected="proposed")


async def test_a_cancel_shown_with_the_longest_reason_bravo_holds_is_stored(
    small_run: OrderRun, world: World, uow: SqlSalesUnitOfWorkFactory
) -> None:
    # "Hủy: " and CancelRemark's 192 (0662b6f0a31c); one more is refused.
    case_id = _case_id(small_run)
    longest = "Hủy: " + "ý" * CANCEL_REASON_CHARS
    await _proposed(uow, world.alpha, case_id, line_no=3, after=longest)
    async with uow(world.alpha) as work:
        held = await work.bravo_writes.of_case(case_id)
    assert [w.after for w in held if w.line_no == 3] == [longest]

    with pytest.raises(ConflictError) as refused:
        await _proposed(uow, world.alpha, case_id, line_no=4, after=longest + "x")
    assert refused.value.details["constraint"] == "ck_bravo_line_writes_values"


@pytest.mark.parametrize("who", ["other tenant", "other workspace of the same tenant"])
async def test_an_outsider_neither_reads_nor_settles_a_proposal(
    who: str, small_run: OrderRun, world: World, uow: SqlSalesUnitOfWorkFactory
) -> None:
    case_id = _case_id(small_run)
    write = await _proposed(uow, world.alpha, case_id, line_no=3)
    outsider = world.beta if who == "other tenant" else world.alpha_other

    async with uow(outsider) as work:
        assert await work.bravo_writes.get(write.approval_id) is None
        assert await work.bravo_writes.of_case(case_id) == []
        with pytest.raises(ConflictError):
            await work.bravo_writes.save(_settled(write), expected="proposed")
    async with uow(world.alpha) as work:
        held = await work.bravo_writes.get(write.approval_id)
    assert held is not None and held.status == "proposed"

"""What the database refuses whoever writes, run as the application role.

The domain refuses all of this first. These are the floor under it: a handler
that forgot a check, or a statement nobody reviewed, still meets the
constraint (spec decision 7, ticket 04).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
import sqlalchemy as sa
from sales_harness import DW1, T0, OrderRun, QuoteRun, user
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.errors import ConflictError
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.case_store import CaseEvent, CaseOrigin
from dw_sales.application.ports import SalesScope
from dw_sales.domain.orders import (
    Accepted,
    Actor,
    Finding,
    FindingCode,
    OrderCase,
    OrderStatus,
    Severity,
)

pytestmark = pytest.mark.integration

# Principal ids, as the verified access context carries them (fictional).
AN = Actor(user_id=uuid.UUID(int=0xA1))
BINH = Actor(user_id=uuid.UUID(int=0xB1))
CHI = Actor(user_id=uuid.UUID(int=0xC1))
DIEU = Actor(user_id=uuid.UUID(int=0xD1))


@asynccontextmanager
async def bound(
    sessions: async_sessionmaker[AsyncSession], scope: SalesScope
) -> AsyncIterator[AsyncSession]:
    async with tenant_session(
        sessions, TenantScope(scope.tenant_id.value, scope.workspace_id.value)
    ) as session:
        yield session


async def _refused(
    sessions: async_sessionmaker[AsyncSession], scope: SalesScope, statement: str, **params: object
) -> str | None:
    """The constraint a statement is refused on, run as dw_app in ``scope``."""
    try:
        async with bound(sessions, scope) as session:
            await session.execute(sa.text(statement), params)
    except IntegrityError as exc:
        return getattr(exc.orig.__cause__, "constraint_name", None)  # type: ignore[union-attr]
    return None


async def _save(
    uow: SqlSalesUnitOfWorkFactory,
    scope: SalesScope,
    steps: list[tuple[OrderCase, str, Actor]],
    start: OrderCase,
) -> OrderCase:
    before = start
    async with uow(scope) as work:
        for after, action, actor in steps:
            event = CaseEvent(action=action, actor=user(actor.user_id), occurred_at=T0)
            await work.orders.save(after, expected_version=before.case_version, event=event)
            before = after
        await work.commit()
    return before


def _m01(small_run: OrderRun) -> OrderCase:
    case = small_run.outcomes["M01"].case
    assert case is not None and not case.findings, "M01 is the clean order"
    return case


def _revision_of(case: OrderCase) -> OrderCase:
    """The customer's revision 1 of the same PO, checked on its own."""
    assert case.rules_version is not None and case.catalog_as_of is not None
    received = OrderCase(
        case_id=uuid.uuid4(),
        case_version=1,
        customer_code=case.customer_code,
        message_id=f"{case.message_id}-R1",
        received_at=T0,
        document=case.document,
        lines=case.lines,
        status=OrderStatus.RECEIVED,
    )
    return received.checked(
        findings=[
            Finding(
                code=FindingCode.REVISED_PO,
                severity=Severity.WARNING,
                expected="0",
                actual="0",
                rule_version=case.rules_version,
            )
        ],
        rules_version=case.rules_version,
        catalog_as_of=case.catalog_as_of,
        cross_check_required=True,
        export_control_mode="warn",
    )


async def _uploaded(small_run: OrderRun, uow: SqlSalesUnitOfWorkFactory) -> OrderCase:
    """M01 prepared by An and entered in Bravo by Bình, as stored."""
    m01 = _m01(small_run)
    review = m01.start_review()
    prepared = review.prepare(AN, T0)
    uploaded = prepared.record_bravo_entry("SO26-1001", BINH, T0, entry_compared=True)
    return await _save(
        uow,
        small_run.scope,
        [
            (review, "order.review_started", AN),
            (prepared, "order.prepared", AN),
            (uploaded, "order.bravo_recorded", BINH),
        ],
        m01,
    )


# ------------------------------------------------------------ maker/checker --


@pytest.mark.parametrize("maker", ["prepared_by", "bravo_recorded_by"])
async def test_a_maker_set_as_cross_checker_fails_on_the_constraint(
    small_run: OrderRun,
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    maker: str,
) -> None:
    case = await _uploaded(small_run, uow)
    refused = await _refused(
        app_sessions,
        small_run.scope,
        f"UPDATE sales.order_cases SET status = 'cross_checked', cross_checked_by = {maker},"
        " cross_checked_at = now() WHERE id = :id",
        id=case.case_id,
    )
    assert refused == "ck_order_cases_checker_not_maker"


async def test_someone_else_may_cross_check(
    small_run: OrderRun,
    uow: SqlSalesUnitOfWorkFactory,
) -> None:
    uploaded = await _uploaded(small_run, uow)
    crossed = uploaded.cross_check(DIEU, T0)
    await _save(uow, small_run.scope, [(crossed, "order.cross_checked", DIEU)], uploaded)
    async with uow(small_run.scope) as work:
        stored = await work.orders.get(crossed.case_id)
    assert stored is not None and stored.case.cross_checked_by == DIEU.user_id
    assert stored.case.makers == {AN.user_id, BINH.user_id}


async def test_an_earlier_bravo_recorder_cannot_cross_check_a_revised_order(
    small_run: OrderRun,
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """After a revision, `apply_change` replaces `bravo_recorded_by`. Bình,
    who keyed the first entry, stays a maker: the case read back carries him
    among its earlier makers and refuses him itself (409, ticket 05), and a
    writer that dropped him still meets the CHECK on the stored makers."""
    uploaded = await _uploaded(small_run, uow)
    review = uploaded.revise(_revision_of(uploaded))
    decided = review.dispose(
        "revised_po:-", Accepted(reason="Đã đọc thay đổi", by=AN.user_id, at=T0), AN
    )
    applied = decided.apply_change(CHI, T0, entry_compared=True)
    stored_applied = await _save(
        uow,
        small_run.scope,
        [
            (review, "order.revised", AN),
            (decided, "order.finding_disposed", AN),
            (applied, "order.change_applied", CHI),
        ],
        uploaded,
    )
    async with uow(small_run.scope) as work:
        stored = await work.orders.get(applied.case_id)
    assert stored is not None
    assert stored.case == stored_applied
    assert stored.case.makers == {AN.user_id, BINH.user_id, CHI.user_id}

    with pytest.raises(ConflictError) as by_the_case:
        stored.case.cross_check(BINH, T0)
    assert by_the_case.value.details["rule"] == "maker_checker"

    # A writer that lost the history: the case it holds names no earlier
    # maker, so nothing in it refuses Bình. The store still does.
    forgetful = OrderCase.model_validate(
        {
            **dict(applied),
            "earlier_makers": frozenset(),
            "status": OrderStatus.CROSS_CHECKED,
            "cross_checked_by": BINH.user_id,
            "cross_checked_at": T0,
            "case_version": applied.case_version + 1,
        }
    )
    crossed = forgetful
    async with uow(small_run.scope) as work:
        with pytest.raises(ConflictError) as refused:
            await work.orders.save(
                crossed,
                expected_version=applied.case_version,
                event=CaseEvent(
                    action="order.cross_checked", actor=user(BINH.user_id), occurred_at=T0
                ),
            )
    assert refused.value.details["rule"] == "maker_checker"
    # Nothing of the row reaches the error: ids and the constraint only.
    assert set(refused.value.details) == {"case_id", "constraint", "rule"}
    assert "SO26-1001" not in str(refused.value) and refused.value.__cause__ is None

    # Writing `makers` directly scrubs nothing: the trigger owns it.
    assert (
        await _refused(
            app_sessions,
            small_run.scope,
            "UPDATE sales.order_cases SET makers = '{}', cross_checked_by = :binh,"
            " cross_checked_at = now(), status = 'cross_checked' WHERE id = :id",
            id=applied.case_id,
            binh=BINH.user_id,
        )
        == "ck_order_cases_checker_not_maker"
    )


async def test_the_pricer_set_as_approver_fails_on_the_constraint(
    quote_run: QuoteRun, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    final = quote_run.steps[-1]
    assert final.approval is not None and final.pricing is not None
    refused = await _refused(
        app_sessions,
        quote_run.scope,
        "UPDATE sales.quote_cases SET body = jsonb_set(body, '{approval,approved_by}',"
        " to_jsonb(priced_by::text)) WHERE id = :id",
        id=final.case_id,
    )
    assert refused == "ck_quote_cases_approver_not_pricer"


# ------------------------------------------------------------- other floors --


async def test_a_line_without_its_check_basis_or_with_a_stranger_key_is_refused(
    small_run: OrderRun, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    case = _m01(small_run)
    target = (
        "UPDATE sales.order_lines SET check_basis = {basis} WHERE revision_id ="
        " (SELECT id FROM sales.order_revisions WHERE case_id = :id AND superseded_at IS NULL)"
    )
    for basis in (
        "check_basis - 'checks_run'",
        "jsonb_set(check_basis, '{checks_run}', '[]')",
        'check_basis || \'{"current_price": "0.70"}\'',
    ):
        refused = await _refused(
            app_sessions, small_run.scope, target.format(basis=basis), id=case.case_id
        )
        assert refused == "ck_order_lines_check_basis", basis
    with pytest.raises(DBAPIError, match="null value"):
        async with bound(app_sessions, small_run.scope) as session:
            await session.execute(sa.text(target.format(basis="NULL")), {"id": case.case_id})


@pytest.mark.parametrize(
    ("column", "value", "constraint"),
    [
        ("actor_kind", "'robot'", "ck_case_events_actor_kind"),
        ("finding_key", "'price_mismatch:0.658'", "ck_case_events_finding_key"),
        ("reason_code", "'0.6980 USD'", "ck_case_events_reason_code"),
        ("field", "'unit_price=0.658'", "ck_case_events_field"),
        ("worker_id", "'sales-dw1'", "ck_case_events_actor"),
    ],
)
async def test_an_event_holds_ids_and_codes_only(
    small_run: OrderRun,
    app_sessions: async_sessionmaker[AsyncSession],
    column: str,
    value: str,
    constraint: str,
) -> None:
    scope = small_run.scope
    values = {
        "actor_kind": "'user'",
        "finding_key": "NULL",
        "reason_code": "NULL",
        "field": "NULL",
        "worker_id": "NULL",
        column: value,
    }
    refused = await _refused(
        app_sessions,
        scope,
        "INSERT INTO sales.case_events (id, tenant_id, workspace_id, case_kind, case_id,"
        " case_version, action, to_status, actor_kind, actor_id, worker_id, finding_key,"
        " field, reason_code, occurred_at) VALUES (gen_random_uuid(), :t, :w, 'order',"
        f" gen_random_uuid(), 1, 'order.probe', 'checked', {values['actor_kind']},"
        f" 'dev|an.nguyen', {values['worker_id']}, {values['finding_key']}, {values['field']},"
        f" {values['reason_code']}, now())",
        t=scope.tenant_id.value,
        w=scope.workspace_id.value,
    )
    assert refused == constraint


async def test_an_artifact_key_always_carries_its_tenant_and_workspace(
    small_run: OrderRun, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    case = _m01(small_run)
    scope = small_run.scope
    refused = await _refused(
        app_sessions,
        scope,
        "INSERT INTO sales.artifacts (id, tenant_id, workspace_id, order_case_id, case_version,"
        " kind, template_ref, object_key, sha256, content_type, size_bytes, created_by)"
        " VALUES (gen_random_uuid(), :t, :w, :c, 1, 'bravo_upload', 'sales_bravo_upload@1.0.0',"
        " 'shared/bravo.xlsx', repeat('a', 64), 'application/pdf', 10,"
        " '00000000-0000-0000-0000-0000000000a1')",
        t=scope.tenant_id.value,
        w=scope.workspace_id.value,
        c=case.case_id,
    )
    assert refused == "ck_artifacts_object_key"


@pytest.mark.parametrize(
    ("change", "constraint"),
    [
        ("owner = NULL WHERE disposition = 'routed_to_sales'", "ck_messages_routed"),
        # Export-control status travels on a sample request only.
        ("compliance = '{}' WHERE disposition = 'case_created'", "ck_messages_compliance"),
    ],
)
async def test_a_message_disposition_names_what_it_must_and_nothing_else(
    small_run: OrderRun,
    app_sessions: async_sessionmaker[AsyncSession],
    change: str,
    constraint: str,
) -> None:
    refused = await _refused(app_sessions, small_run.scope, f"UPDATE sales.messages SET {change}")
    assert refused == constraint


async def test_the_application_cannot_rewrite_an_event(
    small_run: OrderRun, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    for statement in (
        "UPDATE sales.case_events SET action = 'order.rewritten'",
        "DELETE FROM sales.case_events",
        "UPDATE sales.case_events_default SET action = 'order.rewritten'",
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with bound(app_sessions, small_run.scope) as session:
                await session.execute(sa.text(statement))


async def test_a_second_original_case_for_one_po_number_is_refused(
    small_run: OrderRun, uow: SqlSalesUnitOfWorkFactory
) -> None:
    m01 = _m01(small_run)
    twin = OrderCase.model_validate(
        {**dict(m01), "case_id": uuid.uuid4(), "message_id": "M01-TWIN"}
    )
    async with uow(small_run.scope) as work:
        with pytest.raises(ConflictError) as refused:
            await work.orders.add(
                twin,
                CaseOrigin(assigned_to=None, release_manifest_ref=None),
                CaseEvent(action="order.checked", actor=DW1, occurred_at=T0),
            )
    assert refused.value.details["constraint"] == (
        "uq_order_cases_tenant_id_workspace_id_customer_code_po_no"
    )


# ---------------------------------------------------- the approval's stamp --


_APPROVAL = (
    "INSERT INTO platform.approval_requests"
    " (id, tenant_id, workspace_id, approval_type, requested_by, payload, status,"
    "  required_scope)"
    " VALUES (gen_random_uuid(), :t, :w, :type, :u, '{}'::jsonb, 'pending', :stamp)"
)


@pytest.mark.parametrize(
    ("approval_type", "scope"),
    [
        ("sales.quote", None),
        ("sales.order.cross_check", None),
        # A stamp outside Sales is no Sales stamp: `approvals.decide` would
        # pass it for every holder.
        ("sales.quote", "approvals.decide"),
    ],
)
async def test_a_sales_approval_without_a_sales_stamp_is_refused(
    small_run: OrderRun,
    app_sessions: async_sessionmaker[AsyncSession],
    approval_type: str,
    scope: str | None,
) -> None:
    refused = await _refused(
        app_sessions,
        small_run.scope,
        _APPROVAL,
        t=small_run.scope.tenant_id.value,
        w=small_run.scope.workspace_id.value,
        type=approval_type,
        u=AN.user_id,
        stamp=scope,
    )
    assert refused == "ck_approval_requests_sales_stamped"


@pytest.mark.parametrize(
    ("approval_type", "scope"),
    [("sales.quote", "sales.quote.approve"), ("memory.review", None)],
)
async def test_a_stamped_sales_approval_and_any_other_type_are_written(
    small_run: OrderRun,
    app_sessions: async_sessionmaker[AsyncSession],
    approval_type: str,
    scope: str | None,
) -> None:
    refused = await _refused(
        app_sessions,
        small_run.scope,
        _APPROVAL,
        t=small_run.scope.tenant_id.value,
        w=small_run.scope.workspace_id.value,
        type=approval_type,
        u=AN.user_id,
        stamp=scope,
    )
    assert refused is None

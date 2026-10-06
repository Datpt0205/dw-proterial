"""DW1 on the agent runtime, in one process (ticket 10, dw_sales ADR 0004).

The real runner, approval flow and DW1 graph over in-memory stores
(`open_world`), as the API composes them. Each acceptance line of the ticket
has its test here; the API suite (`test_sales_api_runtime.py`) repeats the
ones a database or a route could break.
"""

from __future__ import annotations

import inspect
import json
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from dw_agent_runtime.adapters.run_store import RunStatus
from dw_agent_runtime.registry import parse_worker_file
from dw_kernel.errors import ConflictError, PermissionDeniedError, QuotaExceededError
from dw_kernel.pagination import PageQuery, page_request
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.domain.approval import ApprovalStatus
from dw_sales.application.quotes_service import PricedLine
from dw_sales.application.runs import DECIDE_SCOPES, DecisionType, subject_of
from dw_sales.application.support import DW1_WORKER_ID, DW1_WORKER_VERSION
from dw_sales.domain.catalog import LmeBand
from dw_sales.domain.dispositions import CaseKind
from dw_sales.evals.graders import AN, CALLERS, DIEU, GIANG, KHOA, READER
from dw_sales.evals.world import Caller, SampleSet, World, open_world
from dw_sales.workflows import graph

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
WORKER_FILE = REPO / "configs" / "workers" / "sales.yaml"
PRICE = "0.6890"
# The purchasing manager: the platform's approver authority, nothing of Sales.
BINH = Caller(
    uuid.UUID(int=0xB1),
    "Trần Thị Bình",
    "binh.tran@alpha.local",
    frozenset({"approvals.read", "approvals.decide"}),
)


def _world(**options: object) -> World:
    return open_world(REPO, SampleSet.of(REPO, None), (*CALLERS, BINH), **options)  # type: ignore[arg-type]


async def _pending_quote(world: World, pricer: Caller = DIEU) -> uuid.UUID:
    """M10 from the mailbox to `pending_approval`, priced by ``pricer``."""
    seen = await world.process_each(DIEU, ["M10"])
    case_id = seen["M10"][0].case_id
    assert case_id is not None
    commands = world.services.quote_commands

    def version() -> int:
        return world.quote(case_id).case_version

    await commands.ycbg(DIEU.context(), case_id, case_version=version(), ycbg_no=None)
    await commands.ycbg(DIEU.context(), case_id, case_version=version(), ycbg_no="YCBG-2609-030")
    await commands.design_sent(DIEU.context(), case_id, case_version=version())
    await world.process_each(DIEU, ["M25"])
    await _price(world, pricer, case_id, PRICE)
    await world.services.dw1.submit_quote(
        pricer.context(), case_id, case_version=version(), quote_no="Q26-0301"
    )
    return case_id


async def _price(world: World, pricer: Caller, case_id: uuid.UUID, price: str) -> None:
    band = LmeBand(
        kind="lme_band", low_usd_per_tonne=Decimal(10500), high_usd_per_tonne=Decimal(11000)
    )
    await world.services.quote_commands.price(
        pricer.context(),
        case_id,
        case_version=world.quote(case_id).case_version,
        lme_month="2026-09",
        lines=[
            PricedLine(
                line_no=item.line_no,
                unit_price=Decimal(price),
                moq=Decimal(3000),
                lead_time_days=45,
                copper_basis=band,
            )
            for item in world.quote(case_id).request.document.items
        ],
        management_guidance=None,
    )


async def _approve(world: World, caller: Caller, case_id: uuid.UUID) -> None:
    await world.decide(caller, CaseKind.QUOTE, case_id, approve=True, comment="Đã xem tài liệu")


# ---------------------------------------- 1. the decide scope, per type --


def test_each_approval_type_declares_its_decide_scope() -> None:
    assert dict(DECIDE_SCOPES) == {
        DecisionType.QUOTE_APPROVAL: "sales.quote.approve",
        DecisionType.ORDER_CROSS_CHECK: "sales.order.cross_check",
    }


async def test_a_submitted_quote_waits_on_an_approval_stamped_with_its_scope() -> None:
    world = _world()
    case_id = await _pending_quote(world)

    (request,) = world.runtime.approvals.rows.values()
    assert (request.approval_type, request.decide_scope) == ("sales.quote", "sales.quote.approve")
    # Requested by the maker who submitted it, and naming the pricer.
    assert request.requested_by.value == DIEU.user_id
    assert request.makers == {DIEU.user_id}
    assert request.payload["case_id"] == str(case_id)


async def test_the_purchasing_manager_cannot_decide_a_sales_quote() -> None:
    world = _world()
    case_id = await _pending_quote(world)

    with pytest.raises(PermissionDeniedError) as refused:
        await _approve(world, BINH, case_id)

    assert refused.value.details["action"] == "sales.quote.approve"
    assert world.quote(case_id).status.value == "pending_approval"


async def test_dieu_with_approver_boost_cannot_approve_a_quote_she_priced() -> None:
    world = _world()
    case_id = await _pending_quote(world, DIEU)

    with pytest.raises(PermissionDeniedError) as refused:
        await _approve(world, DIEU, case_id)

    assert refused.value.details["action"] == "sales.quote.approve"
    assert "approvals.decide" in DIEU.scopes


async def test_a_viewer_sees_no_sales_approval_and_the_approver_does() -> None:
    world = _world()
    await _pending_quote(world)
    authz = ScopeAuthorizationService()
    request = page_request(limit=50, cursor=None, query=PageQuery(key="approvals.pending"))
    inbox = world.runtime.approvals.scoped(READER.context().tenant_id)

    async def listed(caller: Caller) -> int:
        audience = world.runtime.approval_flow.audience(caller.context(), authz)
        return len((await inbox.list_pending(request, audience)).items)

    # The viewer and the purchasing manager see none; the approver and the
    # requester see it.
    assert [await listed(c) for c in (READER, BINH, GIANG, DIEU)] == [0, 0, 1, 1]


# ------------------------------------------- 2. every maker is refused --


async def test_the_pricer_cannot_approve_and_another_approver_can() -> None:
    world = _world()
    case_id = await _pending_quote(world, GIANG)

    with pytest.raises(ConflictError) as refused:
        await _approve(world, GIANG, case_id)
    assert refused.value.details["rule"] == "maker_checker"

    await _approve(world, KHOA, case_id)
    case = world.quote(case_id)
    assert case.status.value == "approved"
    assert case.approval is not None and case.approval.approved_by == KHOA.user_id


async def test_an_order_names_every_maker_across_rounds() -> None:
    world = _world()
    seen = await world.process_each(AN, ["M01"])
    case_id = seen["M01"][0].case_id
    assert case_id is not None
    await world.walk_to_uploaded(AN, case_id, recorder=KHOA)
    await world.open_sources(DIEU, case_id)
    await world.decide(DIEU, CaseKind.ORDER, case_id, approve=False, comment="Sai số SO")
    assert world.order(case_id).status.value == "in_review"
    await world.walk_to_uploaded(GIANG, case_id)

    waiting = [
        r for r in world.runtime.approvals.rows.values() if r.status is ApprovalStatus.PENDING
    ]
    (request,) = waiting
    # Round one's preparer and Bravo recorder stay makers of the case.
    assert request.makers == {AN.user_id, KHOA.user_id, GIANG.user_id}
    for maker in (AN, KHOA, GIANG):
        await world.open_sources(maker, case_id)
        with pytest.raises(ConflictError) as refused:
            await world.decide(maker, CaseKind.ORDER, case_id, approve=True, comment="ok")
        assert refused.value.details["rule"] == "maker_checker"
    await world.cross_check(DIEU, case_id)
    assert world.order(case_id).cross_checked_by == DIEU.user_id


# ------------------------------------- 3. ids, a version and a hash only --


async def test_approvals_runs_and_audit_carry_no_amount() -> None:
    world = _world()
    case_id = await _pending_quote(world)
    await _approve(world, GIANG, case_id)

    (request,) = world.runtime.approvals.rows.values()
    assert set(request.payload) == {
        "approval_type",
        "decide_scope",
        "reason",
        "case_kind",
        "case_id",
        "case_version",
        "document_sha256",
        "makers",
    }
    runs = [{"input": r.input, "result": r.result} for r in world.runtime.runs.rows.values()]
    trail = json.dumps(
        [request.payload, runs, [e.details for e in world.runtime.audit.events]],
        ensure_ascii=False,
        default=str,
    )
    assert PRICE not in trail and str(Decimal(PRICE).normalize()) not in trail
    # The search can fail: the case holds the price.
    assert PRICE in world.quote(case_id).model_dump_json()


# --------------------------------------- 4. the plan's run allowance --


class _OneRunADay:
    def runs_per_day(self, plan_id: str) -> int | None:
        return 1

    def spend_usd_per_day(self, plan_id: str) -> Decimal | None:
        return None


async def test_processing_is_a_run_and_the_plans_allowance_refuses_the_next() -> None:
    world = _world(allowance=_OneRunADay())
    await world.process_each(AN, ["M01"])

    with pytest.raises(QuotaExceededError):
        await world.process_each(AN, ["M02"])
    with pytest.raises(QuotaExceededError):
        await world.services.dw1.process_all(AN.context())

    (run,) = world.runtime.runs.rows.values()
    assert (run.context.worker_id, run.input["task"]["kind"]) == (DW1_WORKER_ID, "process")


# ------------------------------------------- 5. the worker and its graph --


def test_the_worker_config_pins_dw1s_graph_and_names_dw1() -> None:
    definition, _ = parse_worker_file(WORKER_FILE)
    assert (definition.worker_id, definition.worker_version) == (DW1_WORKER_ID, DW1_WORKER_VERSION)
    assert definition.graph_version == graph.GRAPH_VERSION


# --------------------------------------- 6. no outbound tool (ADR 0007) --


def test_dw1_offers_a_model_no_outbound_tool() -> None:
    """SEC02: a turn that reads a document gets no outbound tool. Every DW1
    run reads customer mail, so the worker's toolset must hold none: today it
    has no toolset at all; one added later is held to this."""
    definition, _ = parse_worker_file(WORKER_FILE)
    if definition.toolset_version is None:
        return
    toolset = REPO / "configs" / "toolsets" / f"{DW1_WORKER_ID}@{definition.toolset_version}.yaml"
    pins = yaml.safe_load(toolset.read_text(encoding="utf-8"))["tools"]
    for pin in pins:
        spec = REPO / "configs" / "tools" / f"{pin['name']}@{pin['version']}.yaml"
        level = yaml.safe_load(spec.read_text(encoding="utf-8"))["side_effect_level"]
        assert level not in {"external", "critical"}, pin["name"]


def test_dw1s_graph_takes_no_model() -> None:
    """The graph is built from its steps alone: no gateway, no chat model,
    so no model turn exists in a DW1 run to read a document."""
    assert list(inspect.signature(graph.build_graph).parameters) == ["steps"]
    source = inspect.getsource(graph)
    assert not [w for w in ("ModelGateway", "ChatModel", "chat_models", "gateway") if w in source]


# ------------------------------------------------ withdrawal and staleness --


async def test_a_quote_priced_again_withdraws_the_approval_it_waited_on() -> None:
    world = _world()
    case_id = await _pending_quote(world)
    (first,) = world.runtime.approvals.rows.values()

    await _price(world, DIEU, case_id, "0.7000")

    assert first.status is ApprovalStatus.CANCELLED
    (run,) = [
        r for r in world.runtime.runs.rows.values() if r.input["task"]["kind"] == "quote_approval"
    ]
    assert run.status is RunStatus.CANCELLED
    assert await world.runs.pending(DIEU.context(), subject_of(CaseKind.QUOTE, case_id)) is None


@pytest.mark.parametrize(
    ("stamp", "refusal"),
    [(None, ConflictError), ("approvals.decide", PermissionDeniedError)],
)
async def test_an_approval_not_stamped_with_dw1s_scope_is_refused_by_the_guard(
    stamp: str | None, refusal: type[Exception]
) -> None:
    """A `sales.` approval stamped with no decide scope, or with the
    platform's, would be decided by `approvals.decide`; the context's guard
    refuses it (fails closed)."""
    world = _world()
    case_id = await _pending_quote(world)
    (request,) = world.runtime.approvals.rows.values()
    if stamp is None:
        del request.payload["decide_scope"]
    else:
        request.payload["decide_scope"] = stamp

    with pytest.raises(refusal):
        await _approve(world, BINH, case_id)
    assert request.status is ApprovalStatus.PENDING

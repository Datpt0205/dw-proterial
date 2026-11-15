"""Labelled cases (ticket 43, part 1; dw_sales ADR 0015 decision 5): what a
person kept of a model's proposal, written by the step's own service in the
transaction of the decision, one case per item decided.

Over the in-memory world (`dw_sales.evals.world`), with the fictional mail
and the recorded model answers the step's own tests use. The table, its RLS,
grants and partitions are `tests/integration/test_sales_labelled_cases.py`'s.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from dw_kernel.errors import PermissionDeniedError
from dw_kernel.ids import WorkspaceId
from dw_kernel.ports import FixedClock
from dw_sales.application.access import SalesScopes
from dw_sales.application.activity import ActivityService
from dw_sales.application.case_store import Stored
from dw_sales.application.labelled_cases import StepLabels, label_summary
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.labelled_cases import (
    MAX_VALUE_BYTES,
    LabelledCase,
    value_text,
    verdict_of,
)
from dw_sales.domain.layouts import as_proposal
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.orders import OrderCase
from dw_sales.domain.quotes import QuoteFindingCode, ValueConfirmation
from dw_sales.evals.graders import AN, CALLERS, OUTSIDER, READER
from dw_sales.evals.world import (
    ALPHA,
    BETA,
    Caller,
    SampleSet,
    SampleWith,
    World,
    open_world,
)
from dw_sales.testing.followups import platform_zone

from .test_activity import _reading
from .test_change_request_flow import _changes, _reply, _with_model
from .test_change_request_flow import _open as _open_change
from .test_layouts import M43_MAPPING, _mapping
from .test_layouts import _model as _layout_model
from .test_layouts import _world as _layout_world
from .test_po_body import VI, _process
from .test_po_body import _model as _po_model
from .test_rfq_requests import M37, _confirm, _world_with
from .test_rfq_requests import _open as _open_rfq

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
# Reads cases and nothing of the summary: neither `sales.overview.read` nor
# `sales.rules.propose`.
CASE_READER = Caller(
    uuid.UUID(int=0x4C), "Người đọc hồ sơ", "doc@alpha.local", frozenset({SalesScopes.CASE_READ})
)
AT = datetime(2026, 11, 16, 3, 0, tzinfo=UTC)


def _labels(world: World, scope: SalesScope = ALPHA) -> list[LabelledCase]:
    return list(world.store.state(scope).labelled_cases)


def _activity(world: World) -> ActivityService:
    """The activity routes' service over the world's store, as `build_dw1`
    wires it over the SQL readers."""
    gate = world.services.gate
    return ActivityService(
        world.store, gate, world.store, FixedClock(AT), platform_zone(), world.store
    )


# -------------------------------------------------------------- the rule --


@pytest.mark.parametrize(
    ("proposed", "kept", "verdict"),
    [
        ("2500", "2500", "confirmed"),
        ("2500", "2600", "corrected"),
        ("2500", None, "rejected"),
        (["CB-2005"], ["CB-2005"], "confirmed"),
        (["CB-2001", "CB-2002"], ["CB-2002"], "corrected"),
        ([], ["CB-2002"], "corrected"),
        ({"kind": "pdf", "a": 1}, {"a": 1, "kind": "pdf"}, "confirmed"),
    ],
)
def test_the_verdict_is_derived_from_the_two_values_alone(
    proposed: Any, kept: Any, verdict: str
) -> None:
    assert verdict_of(proposed, kept) == verdict


def _case(**changes: Any) -> LabelledCase:
    values: dict[str, Any] = {
        "label_id": uuid.uuid4(),
        "decided_at": AT,
        "step": ModelStep.CHANGE_REQUEST,
        "lane": CaseKind.ORDER,
        "case_id": uuid.uuid4(),
        "customer_code": "NRV",
        "message_id": "R1",
        "attachment_id": None,
        "line_no": 2,
        "field": "quantity",
        "proposed": "2500",
        "kept": "2500",
        "prompt": "sales.change_request@1.0.0",
        "model_profile": "onprem",
        "rules": "sales_order_rules@1.5.2",
        "decided_by": AN.user_id,
    }
    return LabelledCase.model_validate({**values, **changes})


def test_a_case_holds_a_proposal_and_values_of_a_bounded_size() -> None:
    assert _case(kept=None).verdict == "rejected"
    with pytest.raises(ValidationError, match="what the model proposed"):
        _case(proposed=None)
    with pytest.raises(ValidationError, match="longer than"):
        _case(kept="x" * MAX_VALUE_BYTES)
    with pytest.raises(ValidationError):
        _case(field="Quantity")


def test_one_value_is_one_text() -> None:
    assert value_text(Decimal("1000.00")) == value_text(Decimal("1E+3")) == "1000"
    assert value_text(Decimal("0.0420")) == "0.042"


def test_as_read_compares_as_the_fields_type() -> None:
    def confirmation(read: str, value: str) -> ValueConfirmation:
        return ValueConfirmation(field="quantity", read=read, value=value, by=AN.user_id, at=AT)

    assert confirmation("1200", "1200.0").as_read
    assert not confirmation("1200", "1250").as_read


def test_the_heads_view_is_every_step_with_its_counts_and_share() -> None:
    summary = label_summary(
        {ModelStep.RFQ_EXTRACTION: StepLabels(confirmed=3, corrected=1, rejected=0)}
    )

    assert [s.step for s in summary.steps] == list(ModelStep)
    rfq = next(s for s in summary.steps if s.step is ModelStep.RFQ_EXTRACTION)
    assert (rfq.total, rfq.confirmed, rfq.corrected, rfq.confirmed_share) == (4, 3, 1, 0.75)
    idle = next(s for s in summary.steps if s.step is ModelStep.MESSAGE_INTENT)
    assert (idle.total, idle.confirmed_share) == (0, None)


# ----------------------------------------------------- the mapping (PRV) --


async def _m05(*, model_read: bool) -> tuple[World, OrderCase]:
    """M05 (line 1 ambiguous, line 2 one candidate), with its candidates
    from a model's reading of each description when ``model_read``."""
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    _, case = (await world.process_each(AN, ["M05"]))["M05"]
    assert isinstance(case, OrderCase)
    if model_read:
        lines = tuple(
            line.model_copy(
                update={
                    "basis": line.basis.model_copy(update={"description_reading": _reading("read")})
                }
            )
            if line.line_no in (1, 2)
            else line
            for line in case.lines
        )
        case = case.model_copy(update={"lines": lines})
        stored = world.store.state(ALPHA).orders[case.case_id]
        world.store.state(ALPHA).orders[case.case_id] = Stored(case, stored.origin)
    return world, case


async def _confirm_code(world: World, case: OrderCase, line_no: int, code: str) -> None:
    await world.services.order_commands.confirm_mapping(
        AN.context(),
        case.case_id,
        line_no,
        case_version=world.order(case.case_id).case_version,
        prv_code=code,
    )


async def test_confirming_a_model_read_candidate_writes_exactly_one_labelled_case() -> None:
    world, case = await _m05(model_read=True)

    await _confirm_code(world, case, 2, "CB-2005")

    (label,) = _labels(world)
    assert (label.step, label.verdict, label.proposed, label.kept) == (
        ModelStep.DESCRIPTION_ATTRIBUTES,
        "confirmed",
        ["CB-2005"],
        ["CB-2005"],
    )
    assert (label.case_id, label.message_id, label.attachment_id, label.line_no) == (
        case.case_id,
        "M05",
        "M05-A1",
        2,
    )
    assert (label.customer_code, label.decided_by, label.field) == ("KMH", AN.user_id, "prv_code")
    assert (label.prompt, label.model_profile, label.rules) == (
        "sales.description_attributes@1.0.0",
        "onprem",
        "sales_order_rules@1.5.2",
    )


async def test_one_of_several_candidates_picked_is_a_correction_holding_both_values() -> None:
    world, case = await _m05(model_read=True)

    await _confirm_code(world, case, 1, "CB-2002")

    (label,) = _labels(world)
    assert (label.verdict, label.proposed, label.kept) == (
        "corrected",
        ["CB-2001", "CB-2002"],
        ["CB-2002"],
    )


async def test_a_line_code_mapped_without_a_model_labels_nothing() -> None:
    world, case = await _m05(model_read=False)

    await _confirm_code(world, case, 2, "CB-2005")

    assert _labels(world) == []
    assert world.order(case.case_id).line(2).mapping.status == "candidate_confirmed"


async def test_a_decision_refused_writes_no_case_and_another_scope_reads_none() -> None:
    world, case = await _m05(model_read=True)
    other_workspace = SalesScope(ALPHA.tenant_id, WorkspaceId(uuid.UUID(int=0xA1FC)))

    with pytest.raises(PermissionDeniedError):
        await world.services.order_commands.confirm_mapping(
            READER.context(), case.case_id, 2, case_version=case.case_version, prv_code="CB-2005"
        )
    assert _labels(world) == []
    await _confirm_code(world, case, 2, "CB-2005")

    for scope in (BETA, other_workspace):
        assert await world.store.latest(scope, ModelStep.DESCRIPTION_ATTRIBUTES) == []
        assert await world.store.counts(scope) == {}
    assert len(await world.store.latest(ALPHA, ModelStep.DESCRIPTION_ATTRIBUTES)) == 1
    # The head's view: another tenant counts none of them; a caller who may
    # not read the summary is refused.
    beta = await _activity(world).labels(OUTSIDER.context(BETA))
    assert {s.total for s in beta.steps} == {0}
    with pytest.raises(PermissionDeniedError):
        await _activity(world).labels(CASE_READER.context())


# -------------------------------------------------- a PO in the mail body --


async def test_a_po_value_typed_as_read_is_confirmed_and_another_is_a_correction() -> None:
    world, _, case = await _process(_po_model(VI["answer"]))
    assert isinstance(case, OrderCase)
    read = case.line(1).po_line.quantity

    async def correct(field: str, value: str) -> None:
        await world.services.order_commands.correct_value(
            AN.context(),
            case.case_id,
            "value_uncertain:1",
            case_version=world.order(case.case_id).case_version,
            field=field,
            value=value,
        )

    await correct("quantity", f"{read}.000" if "." not in str(read) else str(read))
    await correct("quantity", str(read + 1))

    first, second = _labels(world)
    assert (first.step, first.verdict, first.proposed, first.kept) == (
        ModelStep.PO_BODY_EXTRACTION,
        "confirmed",
        value_text(read),
        value_text(read),
    )
    assert (second.verdict, second.proposed, second.kept) == (
        "corrected",
        value_text(read),
        value_text(read + 1),
    )
    assert (second.line_no, second.field, second.attachment_id) == (1, "quantity", None)
    assert second.prompt == case.document.parser_version and second.model_profile is None


# ------------------------------------------------- a request for quotation --


async def test_each_value_of_a_request_confirmed_is_one_case_as_read_or_corrected() -> None:
    world, case_id = _world_with(await _open_rfq("M37", M37))
    await world.services.sources.quote_message_text(AN.context(), case_id)
    await _confirm(world, AN, case_id, 1, "quantity", "1250")
    await world.services.sources.quote_message_text(AN.context(), case_id)
    await world.services.quote_commands.answer_finding(
        AN.context(),
        case_id,
        "value_uncertain:2",
        case_version=world.quote(case_id).case_version,
        as_read=True,
    )

    corrected, *as_read = _labels(world)
    assert (corrected.step, corrected.lane, corrected.verdict) == (
        ModelStep.RFQ_EXTRACTION,
        CaseKind.QUOTE,
        "corrected",
    )
    assert (corrected.proposed, corrected.kept, corrected.line_no) == ("1200", "1250", 1)
    flagged = next(
        f for f in world.quote(case_id).findings if f.key == (QuoteFindingCode.VALUE_UNCERTAIN, 2)
    ).flagged
    assert sorted(c.field for c in as_read) == sorted(flagged)
    assert {c.verdict for c in as_read} == {"confirmed"} and {c.line_no for c in as_read} == {2}


# ------------------------------------------------------ a change request --


async def test_a_change_line_the_model_read_is_labelled_when_confirmed_or_rejected() -> None:
    body = "Hello,\n\nFor line 2 please send 2500 m and line 3 2000 m instead.\n\nHana"
    answer = _changes(("line 2", "quantity", "2500 m"), ("line 3", "quantity", "2000 m"))
    with SampleWith([_reply(html=None, body=body)]) as sample:
        world, _, case_id = await _with_model(sample, answer)
        opened = await _open_change(world, case_id)
        request_id = opened.request.request_id
        await world.services.change_requests.confirm(
            AN.context(), case_id, request_id, 1, case_version=world.order(case_id).case_version
        )
        await world.services.change_requests.reject(
            AN.context(),
            case_id,
            request_id,
            2,
            case_version=world.order(case_id).case_version,
            reason="Khách gọi lại, giữ nguyên",
        )

    confirmed, rejected = _labels(world)
    assert (confirmed.step, confirmed.line_no, confirmed.verdict) == (
        ModelStep.CHANGE_REQUEST,
        2,
        "confirmed",
    )
    assert (confirmed.proposed, confirmed.kept, confirmed.message_id) == ("2500", "2500", "R1")
    assert (rejected.line_no, rejected.verdict, rejected.proposed, rejected.kept) == (
        3,
        "rejected",
        "2000",
        None,
    )


async def test_a_change_line_read_from_a_table_labels_nothing() -> None:
    with SampleWith([_reply()]) as sample:
        world, _, case_id = await _with_model(sample, {})
        opened = await _open_change(world, case_id)
        assert {x.read_by for x in opened.request.lines} == {"table"}
        await world.services.change_requests.confirm(
            AN.context(),
            case_id,
            opened.request.request_id,
            1,
            case_version=world.order(case_id).case_version,
        )

    assert _labels(world) == []


# ------------------------------------------------------------ a PO layout --


async def test_a_layout_proposed_on_a_model_prefill_is_labelled_beside_it() -> None:
    world = _layout_world(_layout_model(as_proposal(M43_MAPPING)))
    await world.process_each(AN, ["M43"])
    (learned,) = world.store.state(ALPHA).layouts.values()
    assert learned.prefill is not None and learned.prefill.mapping is not None
    # The pre-fill on the mail, as a routed mail keeps it for Sales.
    logged = world.store.state(ALPHA).messages["M43"]
    world.store.state(ALPHA).messages["M43"] = replace(
        logged,
        disposition=logged.disposition.model_copy(update={"layout_prefill": learned.prefill}),
    )

    view = await world.services.layouts.propose(AN.context(), "M43", "M43-A1", _mapping())

    (label,) = _labels(world)
    assert (label.step, label.case_id, label.field, label.verdict) == (
        ModelStep.LAYOUT_PROPOSAL,
        None,
        "mapping",
        "confirmed",
    )
    assert (label.message_id, label.attachment_id, label.decided_by) == (
        "M43",
        "M43-A1",
        AN.user_id,
    )
    assert label.kept == world.store.state(ALPHA).layouts[view.layout_id].mapping.model_dump(
        mode="json"
    )


# ------------------------------------------------------------ the counts --


async def test_the_counts_and_the_heads_view_add_up_per_step() -> None:
    world, case = await _m05(model_read=True)
    await _confirm_code(world, case, 2, "CB-2005")
    await _confirm_code(world, case, 1, "CB-2002")

    counts = await world.store.counts(ALPHA)
    view = await _activity(world).labels(AN.context())

    assert counts == {ModelStep.DESCRIPTION_ATTRIBUTES: StepLabels(confirmed=1, corrected=1)}
    step = next(s for s in view.steps if s.step is ModelStep.DESCRIPTION_ATTRIBUTES)
    assert (step.total, step.confirmed_share) == (2, 0.5)
    # Both decided at the world's one instant: newest first, ties by id, as
    # the SQL reader orders (whose newest-first over distinct times is
    # `test_sales_labelled_cases.py`'s).
    latest = await world.store.latest(ALPHA, ModelStep.DESCRIPTION_ATTRIBUTES)
    assert {c.line_no for c in latest} == {1, 2}
    assert latest == sorted(latest, key=lambda c: (c.decided_at, c.label_id), reverse=True)
    assert (
        await world.store.latest(ALPHA, ModelStep.DESCRIPTION_ATTRIBUTES, customer_code="NRV") == []
    )
    assert len(await world.store.latest(ALPHA, ModelStep.DESCRIPTION_ATTRIBUTES, limit=1)) == 1

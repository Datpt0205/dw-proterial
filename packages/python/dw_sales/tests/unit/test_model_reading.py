"""DW1 reads a description through a model only where it may, and degrades
to a person whenever the answer is not usable (ticket 28, dw_sales ADR 0005).

`OrderIntake` over the mock mailbox with a scripted model (`Replayed`), and
`GatewayInterpretation` over a fake gateway: which lines are sent, under which
switch and run, and what each kind of failure leaves on the line.
"""

from __future__ import annotations

import itertools
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.budget import BudgetExceededError
from dw_agent_runtime.ports import ModelOutputInvalidError, ModelRequest
from dw_kernel.errors import InfrastructureError, NotFoundError
from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.mock.fixtures import DATA_DIR
from dw_sales.adapters.model_interpretation import GatewayInterpretation
from dw_sales.adapters.order_rules import PlatformOrderRules, load_tenant_order_rules
from dw_sales.adapters.policy_files import load_sales_policies
from dw_sales.adapters.readers import mock_po_readers
from dw_sales.application.model_reading import (
    DESCRIPTION_ATTRIBUTES,
    DescriptionReader,
    ModelUnavailableError,
)
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.ports import SalesScope
from dw_sales.domain.description_reading import ModelDescriptionReading
from dw_sales.domain.order_checks import OrderRules
from dw_sales.domain.orders import FindingCode, MappingStatus, OrderCase
from dw_sales.evals.descriptions import Replayed

pytestmark = pytest.mark.unit

SCOPE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
CATALOG = MockSalesCatalog.load(SCOPE)
INBOX = MockInbox.load(SCOPE)
REPO = Path(__file__).resolve().parents[5]
PLATFORM = load_sales_policies(REPO / "configs" / "policies", REPO / "configs" / "copy").order_rules
DEMO = load_tenant_order_rules(DATA_DIR / "policies")
RUN = RunContext(
    run_id=uuid.UUID(int=0x5EED),
    tenant_id=SCOPE.tenant_id.value,
    workspace_id=SCOPE.workspace_id.value,
    actor_id=uuid.UUID(int=0xA1),
    worker_id="sales-dw1",
    worker_version="1.0.0",
    channel="web",
    plan_id="professional",
    roles=frozenset(),
    scopes=frozenset(),
    trace_id="t28",
)
LINE_1 = "Dây điện AWG24 lõi xoắn, đồng mạ thiếc, không chống nhiễu, màu đỏ, reel 610m"
LINE_2 = "4C AWG22 TC BRD GRY 300M RL"
LINE_3 = "Cáp 2 lõi 0,5mm2 đồng mạ thiếc chống nhiễu lá nhôm màu đen, cuộn reel 300m"
# What a model that reads M36 well answers; line 2's `RL` left without a value.
ANSWERS: dict[str, Mapping[str, Any] | None] = {
    LINE_1: {
        "family_span": "Dây điện",
        "family": "hook_up_wire",
        "gauge_span": "AWG24",
        "stranding_span": "lõi xoắn",
        "stranding": "stranded",
        "conductor_span": "đồng mạ thiếc",
        "conductor": "tinned_copper",
        "shield_span": "không chống nhiễu",
        "shield": "none",
        "colour_span": "màu đỏ",
        "colour": "red",
        "packaging_span": "reel",
        "packaging": "reel",
        "pack_length_span": "610m",
    },
    LINE_2: {"cores_span": "4C", "gauge_span": "AWG22", "packaging_span": "RL"},
    LINE_3: {
        "family_span": "Cáp",
        "family": "multi_core_cable",
        "cores_span": "2 lõi",
        "gauge_span": "0,5mm2",
        "conductor_span": "đồng mạ thiếc",
        "conductor": "tinned_copper",
        "shield_span": "chống nhiễu lá nhôm",
        "shield": "foil",
        "colour_span": "màu đen",
        "colour": "black",
        "packaging_span": "cuộn reel",
        "packaging": "reel",
        "pack_length_span": "300m",
    },
}


def _intake(model: Any, rules: OrderRules | None = DEMO) -> OrderIntake:
    assert rules is not None
    ids = itertools.count(1)
    return OrderIntake(
        catalog=CATALOG,
        inbox=INBOX,
        reader=mock_po_readers(),
        rules=PlatformOrderRules(rules),
        cases=_NoCases(),
        new_case_id=lambda: uuid.UUID(int=next(ids)),
        descriptions=None if model is None else DescriptionReader(model),
    )


class _NoCases:
    async def cases_for_po(self, scope: SalesScope, customer_code: str, po_no: str) -> list[Any]:
        return []


async def _case(intake: OrderIntake, message_id: str, run: RunContext | None = RUN) -> OrderCase:
    message = await INBOX.get_message(SCOPE, message_id)
    assert message is not None
    outcome = await intake.process(SCOPE, message, run=run)
    assert outcome.case is not None
    return outcome.case


def test_the_demo_tenant_has_the_step_on_and_the_platform_has_it_off() -> None:
    assert DEMO is not None and DEMO.model_assist.description_attributes
    assert not PLATFORM.model_assist.description_attributes
    assert DEMO.version != PLATFORM.version


async def test_lines_read_by_the_model_are_candidates_with_the_reading_stamped() -> None:
    model = Replayed(answers=ANSWERS)
    case = await _case(_intake(model), "M36")

    lines = {line.line_no: line for line in case.lines}
    assert lines[1].mapping.candidates == ("HW-1002",)
    assert lines[1].mapping.status is MappingStatus.CANDIDATE
    assert lines[3].mapping.candidates == ("CB-2001",)
    # `RL` came with no value, so no span covers it: the line stays Sales'.
    assert lines[2].mapping.status is MappingStatus.UNMAPPED
    unmapped = {f.line_no for f in case.findings if f.code is FindingCode.CODE_UNMAPPED}
    assert unmapped == {2}

    reading = lines[1].basis.description_reading
    assert reading is not None and reading.outcome == "read"
    assert (reading.prompt, reading.model_profile, reading.route) == (
        str(DESCRIPTION_ATTRIBUTES),
        "onprem",
        "structured_extraction",
    )
    assert set(reading.model_read) == {
        "family",
        "stranding",
        "conductor",
        "shield",
        "colour",
        "packaging",
    }
    refused = lines[2].basis.description_reading
    assert refused is not None and (refused.outcome, refused.reason) == (
        "not_understood",
        "text_uncovered",
    )

    # One call for the PO's three lines, made in the run that processes it.
    ((prompt, run, _),) = model.calls
    assert (prompt, run) == (DESCRIPTION_ATTRIBUTES, RUN)


async def test_with_the_switch_off_the_model_is_never_called() -> None:
    model = Replayed(answers=ANSWERS)
    case = await _case(_intake(model, rules=PLATFORM), "M36")

    assert model.calls == []
    assert all(line.mapping.status is MappingStatus.UNMAPPED for line in case.lines)
    assert all(line.basis.description_reading is None for line in case.lines)


async def test_outside_a_run_the_model_is_never_called() -> None:
    model = Replayed(answers=ANSWERS)
    await _case(_intake(model), "M36", run=None)
    assert model.calls == []


async def test_a_line_the_convert_list_or_the_vocabulary_maps_is_never_sent() -> None:
    """M05: line 3 is in the convert list, line 2's description is read by
    DW1's own vocabulary. Neither is the model's to read."""
    model = Replayed(answers={})
    case = await _case(_intake(model), "M05")

    assert model.calls == []
    by_no = {line.line_no: line for line in case.lines}
    assert by_no[2].mapping.status is MappingStatus.CANDIDATE
    assert by_no[3].mapping.status is MappingStatus.EXACT


@pytest.mark.parametrize(
    "failure",
    [
        ModelUnavailableError("InfrastructureError"),
        ModelUnavailableError("ModelOutputInvalidError"),
    ],
)
async def test_no_usable_answer_leaves_every_line_unmapped_as_without_a_model(
    failure: Exception,
) -> None:
    case = await _case(_intake(Replayed(failure=failure)), "M36")

    assert all(line.mapping.status is MappingStatus.UNMAPPED for line in case.lines)
    assert {f.line_no for f in case.findings if f.code is FindingCode.CODE_UNMAPPED} == {1, 2, 3}
    for line in case.lines:
        reading = line.basis.description_reading
        assert reading is not None and reading.outcome == "unavailable"


async def test_a_spent_budget_stops_the_run_rather_than_reading_as_not_understood() -> None:
    model = Replayed(failure=BudgetExceededError("run budget exceeded"))
    with pytest.raises(BudgetExceededError):
        await _case(_intake(model), "M36")


# ------------------------------------------------ the gateway's adapter --


class _Gateway:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.requests: list[tuple[ModelRequest, RunContext]] = []

    async def generate_structured(
        self, request: ModelRequest, output_type: type[Any], *, run_context: RunContext
    ) -> Any:
        self.requests.append((request, run_context))
        if self.failure is not None:
            raise self.failure
        return output_type.model_validate({"lines": []})


async def _interpret(gateway: _Gateway) -> BaseModel:
    return await GatewayInterpretation(gateway, "onprem").interpret(
        DESCRIPTION_ATTRIBUTES,
        {"lines": "[]", "vocabulary": "{}"},
        ModelDescriptionReading,
        run=RUN,
        max_output_tokens=400,
    )


async def test_the_adapter_asks_the_gateway_on_dw1s_profile_for_the_run() -> None:
    gateway = _Gateway()
    await _interpret(gateway)

    ((request, run),) = gateway.requests
    assert run is RUN
    assert (request.prompt_id, request.prompt_version) == (
        DESCRIPTION_ATTRIBUTES.prompt_id,
        DESCRIPTION_ATTRIBUTES.version,
    )
    assert (request.model_profile, request.task, request.max_output_tokens) == (
        "onprem",
        "structured_extraction",
        400,
    )


@pytest.mark.parametrize(
    "failure",
    [
        InfrastructureError("model provider timed out"),
        ModelOutputInvalidError("model output failed schema validation"),
        NotFoundError("model provider not configured"),
    ],
)
async def test_every_way_of_getting_no_answer_is_model_unavailable(failure: Exception) -> None:
    with pytest.raises(ModelUnavailableError):
        await _interpret(_Gateway(failure))


async def test_a_budget_refusal_passes_through_the_adapter() -> None:
    with pytest.raises(BudgetExceededError):
        await _interpret(_Gateway(BudgetExceededError("run budget exceeded")))

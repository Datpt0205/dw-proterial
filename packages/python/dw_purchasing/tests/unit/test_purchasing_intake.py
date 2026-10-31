"""DW02 function 1: a purchase request received from a form or read from a
mail, over the in-memory world (`dw_purchasing.testing.world`).

The model's answers are the recorded ones the eval smoke replays
(`evals/fixtures/cases/purchasing_pr_intake.json`), plus the answers a misled
model could give; what is checked is what code makes of them.
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from dw_agent_runtime.model.interpretation import ModelUnavailableError
from dw_kernel.errors import (
    ConflictError,
    DomainError,
    InfrastructureError,
    NotFoundError,
    PermissionDeniedError,
)
from dw_purchasing.application.access import PurchasingScopes
from dw_purchasing.application.intake import PR_MAIL_READING
from dw_purchasing.application.ports import Disposition
from dw_purchasing.domain.requests import CaseStatus, PrLine, PrSource, PurchaseRequest
from dw_purchasing.testing.world import ALPHA, BETA, BUYER, World, caller, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
FIXTURE = json.loads(
    (REPO / "evals/fixtures/cases/purchasing_pr_intake.json").read_text(encoding="utf-8")
)
ANSWERS: dict[str, Any] = FIXTURE["answers"]


def _world(answers: dict[str, Any] | None = None, **kwargs: Any) -> World:
    return open_world(REPO, ANSWERS if answers is None else answers, **kwargs)


def _variant(name: str) -> dict[str, Any]:
    return {**ANSWERS, **FIXTURE["variants"][name]}


def _form(**changes: Any) -> PurchaseRequest:
    base: dict[str, Any] = {
        "pr_no": "PR-2611-020",
        "department": "Kho",
        "requester": "Trần Văn Kho",
        "budget_code": "CC-WH-01",
        "currency": "VND",
        "lines": [
            PrLine(line_no=1, description="Pallet nhựa 1200x1000", quantity=Decimal(20), unit="cái")
        ],
    }
    return PurchaseRequest.model_validate({**base, **changes})


# ---------------------------------------------------------------- the form --


async def test_a_complete_form_opens_a_case_stamped_with_the_rules_and_audited() -> None:
    world = _world()
    change = await world.service.submit_form(caller(), _form())

    case = await world.service.case(caller(), change.case_id)
    assert (case.status, case.source, case.source_ref) == (CaseStatus.RECEIVED, PrSource.FORM, None)
    assert case.rules_ref == "purchasing_rules@1.0.0"
    assert case.received_by == BUYER
    (event,) = world.store.rows(*ALPHA).audit
    assert event.action == "purchasing.request.received"
    assert event.details == {"source": "form", "rules_ref": "purchasing_rules@1.0.0", "lines": 1}


async def test_a_form_lacking_what_the_rules_require_is_refused_naming_it() -> None:
    world = _world()
    with pytest.raises(DomainError) as refused:
        await world.service.submit_form(caller(), _form(budget_code=None, currency="EUR"))

    assert refused.value.details["refusals"] == "missing:budget_code,currency_not_allowed"
    assert world.store.rows(*ALPHA).cases == {}


async def test_receiving_needs_the_intake_scope_and_stores_nothing_without_it() -> None:
    world = _world()
    reader = caller(scopes=frozenset({PurchasingScopes.REQUEST_READ.value}))
    with pytest.raises(PermissionDeniedError):
        await world.service.submit_form(reader, _form())
    with pytest.raises(PermissionDeniedError):
        await world.service.read_mail(reader, "P01")

    assert world.store.rows(*ALPHA).cases == {} and world.model.calls == []


async def test_reading_needs_the_read_scope() -> None:
    world = _world()
    intake_only = caller(scopes=frozenset({PurchasingScopes.REQUEST_INTAKE.value}))
    with pytest.raises(PermissionDeniedError):
        await world.service.cases(intake_only, limit=10, before=None)
    with pytest.raises(PermissionDeniedError):
        await world.service.mailbox(intake_only)


# ---------------------------------------------------------------- the mail --


async def test_a_request_in_a_mail_opens_a_case_from_the_spans_code_found() -> None:
    world = _world()
    item = await world.service.read_mail(caller(), "P01")

    assert item.disposition is Disposition.OPENED and item.case_id is not None
    case = await world.service.case(caller(), item.case_id)
    request = case.request
    assert (case.source, case.source_ref) == (PrSource.MAIL, "P01")
    assert (request.pr_no, request.department, request.budget_code, request.currency) == (
        "PR-2611-004",
        "Xưởng cắt",
        "CC-PROD-01",
        "VND",
    )
    # The requester is the verified sender, never a span.
    assert request.requester == "Nguyễn Thị Lan"
    assert [(line.quantity, line.unit, line.need_by) for line in request.lines] == [
        (Decimal(4), "cái", date(2026, 11, 20)),
        (Decimal(50), "đôi", date(2026, 11, 20)),
        (Decimal(120), "cuộn", None),
    ]
    assert request.lines[0].item_code == "DC-200"
    (prompt, inputs, run) = world.model.calls[0]
    assert prompt == PR_MAIL_READING
    assert inputs["mail"].startswith("Yêu cầu mua hàng PR-2611-004")
    assert (run.actor_id, run.worker_id, run.tenant_id) == (BUYER, "purchasing-dw2", ALPHA[0])


async def test_a_mail_is_settled_once_and_a_second_press_reads_nothing() -> None:
    world = _world()
    first = await world.service.read_mail(caller(), "P01")
    again = await world.service.read_mail(caller(), "P01")

    assert again == first and len(world.model.calls) == 1
    assert len(world.store.rows(*ALPHA).cases) == 1


async def test_an_instruction_in_the_mail_is_content_and_decides_nothing() -> None:
    world = _world()
    item = await world.service.read_mail(caller(), "P02")

    assert item.case_id is not None
    case = await world.service.case(caller(), item.case_id)
    assert case.status is CaseStatus.RECEIVED
    assert [line.description for line in case.request.lines] == ["Khuôn ép đầu cos KE-16"]


async def test_a_model_that_obeys_the_mail_has_its_reading_refused() -> None:
    world = _world(_variant("injection_obeyed"))
    item = await world.service.read_mail(caller(), "P02")

    assert (item.disposition, item.reason) == (Disposition.TO_PERSON, "line_unreadable")
    assert world.store.rows(*ALPHA).cases == {}


@pytest.mark.parametrize(
    ("variant", "reason"),
    [("invented_budget", "span_not_found"), ("invented_quantity", "line_unreadable")],
)
async def test_a_value_the_mail_does_not_hold_refuses_the_request(
    variant: str, reason: str
) -> None:
    world = _world(_variant(variant))
    item = await world.service.read_mail(caller(), "P01")

    assert (item.disposition, item.reason) == (Disposition.TO_PERSON, reason)
    (event,) = world.store.rows(*ALPHA).audit
    assert (event.action, event.details) == ("purchasing.mail.to_person", {"reason": reason})


@pytest.mark.parametrize(
    ("message_id", "reason"),
    [("P03", "sender_not_internal"), ("P04", "sender_unverified")],
)
async def test_a_sender_not_the_companys_and_verified_goes_to_a_person_unread(
    message_id: str, reason: str
) -> None:
    world = _world()
    item = await world.service.read_mail(caller(), message_id)

    assert (item.disposition, item.reason) == (Disposition.TO_PERSON, reason)
    assert world.model.calls == []


async def test_a_mail_that_is_no_request_goes_to_a_person() -> None:
    world = _world()
    item = await world.service.read_mail(caller(), "P05")
    assert (item.disposition, item.reason) == (Disposition.TO_PERSON, "no_pr_number")


async def test_a_mail_request_is_held_to_the_same_form_rules() -> None:
    world = _world()
    item = await world.service.read_mail(caller(), "P06")
    assert (item.disposition, item.reason) == (Disposition.TO_PERSON, "missing:budget_code")


@pytest.mark.parametrize("with_model", [True, False])
async def test_no_usable_answer_records_nothing_and_a_retry_reads_again(with_model: bool) -> None:
    world = _world(with_model=with_model)
    world.model.failure = ModelUnavailableError("down")
    with pytest.raises(InfrastructureError):
        await world.service.read_mail(caller(), "P01")
    assert world.store.rows(*ALPHA).outcomes == {}

    if with_model:
        world.model.failure = None
        item = await world.service.read_mail(caller(), "P01")
        assert item.disposition is Disposition.OPENED


async def test_the_mailbox_lists_each_mail_with_what_was_done_with_it() -> None:
    world = _world()
    await world.service.read_mail(caller(), "P03")
    items = {i.message_id: i for i in await world.service.mailbox(caller())}

    assert list(items) == ["P01", "P02", "P03", "P04", "P05", "P06"]
    assert items["P03"].reason == "sender_not_internal" and items["P01"].disposition is None


# ---------------------------------------------------------------- tenancy --


async def test_another_tenant_sees_no_mail_no_case_and_cannot_read_ours() -> None:
    world = _world()
    change = await world.service.submit_form(caller(), _form())
    other = caller(BETA)

    assert await world.service.mailbox(other) == []
    assert await world.service.cases(other, limit=10, before=None) == []
    with pytest.raises(NotFoundError):
        await world.service.case(other, change.case_id)
    with pytest.raises(NotFoundError):
        await world.service.read_mail(other, "P01")
    assert world.model.calls == []


async def test_another_workspace_of_the_same_tenant_does_not_see_the_case() -> None:
    world = _world()
    change = await world.service.submit_form(caller(), _form())
    with pytest.raises(NotFoundError):
        await world.service.case(caller((ALPHA[0], uuid.UUID(int=0xA3))), change.case_id)


# ---------------------------------------------------------- tenant rules --


def _tenant_rules(**changes: Any) -> dict[str, object]:
    document: dict[str, object] = {
        "version": "1.0.0-alpha.1",
        "pr_form": {
            "required": ["budget_code", "need_by"],
            "max_lines": 50,
            "currencies": ["VND"],
            "default_currency": "VND",
        },
        "internal_domains": ["seller.example"],
    }
    return {**document, **changes}


async def test_a_tenants_own_rules_decide_and_are_stamped() -> None:
    world = _world()
    world.tenant_policies.documents[(ALPHA[0], "purchasing_rules")] = _tenant_rules()

    item = await world.service.read_mail(caller(), "P01")
    assert (item.disposition, item.reason) == (Disposition.TO_PERSON, "missing:need_by")
    change = await world.service.submit_form(caller(), _form(need_by=date(2026, 12, 1)))
    case = await world.service.case(caller(), change.case_id)
    assert case.rules_ref == "purchasing_rules@1.0.0-alpha.1"


async def test_one_tenants_rules_never_reach_another() -> None:
    world = _world()
    world.tenant_policies.documents[(BETA[0], "purchasing_rules")] = _tenant_rules()
    item = await world.service.read_mail(caller(), "P01")
    assert item.disposition is Disposition.OPENED


@pytest.mark.parametrize(
    "document",
    [_tenant_rules(pr_form={"required": []}), _tenant_rules(version="1.0.0")],
    ids=["unreadable", "a-platform-version"],
)
async def test_a_tenant_version_that_cannot_be_used_refuses_rather_than_falls_back(
    document: dict[str, object],
) -> None:
    world = _world()
    world.tenant_policies.documents[(ALPHA[0], "purchasing_rules")] = document
    with pytest.raises(ConflictError):
        await world.service.submit_form(caller(), _form())
    assert world.store.rows(*ALPHA).cases == {}

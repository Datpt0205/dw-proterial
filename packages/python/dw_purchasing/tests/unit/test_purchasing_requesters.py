"""A requester writes their own request in DW2 ("Tôi cần mua…") and sees only
the requests they wrote; their name and department are the directory's, the
number is code's, and they never decide their own request."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml

from dw_kernel.errors import DomainError, NotFoundError, PermissionDeniedError
from dw_purchasing.application.access import PurchasingScopes
from dw_purchasing.application.ports import Person
from dw_purchasing.application.requesters import PR_FROM_WORDS, MyRequest
from dw_purchasing.domain.cases import PrSource
from dw_purchasing.domain.mail_reading import ModelPrMail, read_pr_words
from dw_purchasing.testing.world import ALPHA, BETA, World, caller, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
DATA = json.loads(
    (REPO / "evals/fixtures/cases/purchasing_pr_words.json").read_text(encoding="utf-8")
)
HOA = uuid.UUID(int=0x5EC1)
NAM = uuid.UUID(int=0x5EC2)
_OWN = frozenset({PurchasingScopes.REQUEST_CREATE.value, PurchasingScopes.REQUEST_READ_OWN.value})


def _requester(who: uuid.UUID = HOA, scope: tuple[uuid.UUID, uuid.UUID] = ALPHA) -> Any:
    return caller(scope, scopes=_OWN, principal=who)


def _world() -> World:
    world = open_world(REPO, DATA["answers"])
    world.people.people[HOA] = Person("Lê Thị Hoa", "Bảo trì")
    world.people.people[NAM] = Person("Phạm Văn Nam", "")
    return world


async def _sent(world: World, who: uuid.UUID = HOA, **form: Any) -> uuid.UUID:
    view = await world.requester.draft(_requester(who), DATA["words"]["gloves"])
    assert view.draft is not None
    change = await world.requester.submit(
        _requester(who),
        MyRequest(currency="VND", lines=view.draft.lines, budget_code="CC-1", **form),
    )
    return change.case_id


async def test_a_sentence_is_drafted_and_what_the_form_still_asks_is_named() -> None:
    world = _world()
    view = await world.requester.draft(_requester(), DATA["words"]["gloves"])
    assert view.draft is not None and view.not_read is None
    assert [(line.description, line.unit) for line in view.draft.lines] == [
        ("găng tay nitrile cỡ M", "hộp")
    ]
    # The platform's form rules require a budget code the words do not give.
    assert view.missing == ["budget_code"]
    assert world.store.rows(*ALPHA).cases == {}


async def test_the_case_is_numbered_by_code_and_named_by_the_directory() -> None:
    world = _world()
    case = await world.service.case(_requester(), await _sent(world, department="Kế toán"))
    assert case.source is PrSource.REQUESTER and case.requested_by == HOA
    assert case.request.pr_no.startswith("DW2-")
    # The directory's department, not the one the form sent.
    assert (case.request.requester, case.request.department) == ("Lê Thị Hoa", "Bảo trì")
    assert HOA in case.makers


async def test_a_department_the_directory_lacks_is_asked_and_then_taken() -> None:
    world = _world()
    with pytest.raises(DomainError) as refused:
        await _sent(world, NAM)
    assert refused.value.details["refusals"] == "missing:department"
    case = await world.service.case(_requester(NAM), await _sent(world, NAM, department="Kho"))
    assert case.request.department == "Kho"


async def test_a_person_the_directory_does_not_know_sends_nothing() -> None:
    world = _world()
    stranger = uuid.UUID(int=0xDEAD)
    with pytest.raises(DomainError) as refused:
        await _sent(world, stranger)
    assert refused.value.details["rule"] == "unknown_person"


async def test_a_requester_reads_their_own_cases_only_and_a_buyer_reads_all() -> None:
    world = _world()
    hoa = await _sent(world, HOA)
    nam = await _sent(world, NAM, department="Kho")
    mine = await world.service.cases(_requester(HOA), limit=50, before=None)
    assert [c.case_id for c in mine] == [hoa]
    with pytest.raises(NotFoundError):
        await world.service.case(_requester(HOA), nam)
    everyone = await world.service.cases(caller(), limit=50, before=None)
    assert {c.case_id for c in everyone} == {hoa, nam}
    with pytest.raises(NotFoundError):
        await world.service.case(caller(BETA), hoa)


async def test_a_requester_holds_no_buyers_scope() -> None:
    world = _world()
    case_id = await _sent(world)
    with pytest.raises(PermissionDeniedError):
        await world.approvals.submit(_requester(), case_id, case_version=1)
    with pytest.raises(PermissionDeniedError):
        await world.service.mailbox(_requester())
    nobody = caller(scopes=frozenset())
    with pytest.raises(PermissionDeniedError):
        await world.service.cases(nobody, limit=50, before=None)


async def test_the_requester_is_a_maker_of_the_approval_and_never_its_decider() -> None:
    world = _world()
    case_id = await _sent(world)
    await world.approvals.submit(caller(), case_id, case_version=1)
    (request,) = world.store.rows(*ALPHA).approvals.values()
    makers = request.payload["makers"]
    assert isinstance(makers, list) and str(HOA) in makers


def test_the_words_reader_keeps_only_lines_found_whole() -> None:
    words = "Cần 2 cuộn băng keo điện"
    answer = ModelPrMail.model_validate(
        {
            "pr_no_span": "PR-9",
            "department_span": "Kho",
            "budget_code_span": None,
            "currency_span": None,
            "need_by_span": None,
            "lines": [
                {
                    "line_span": "2 cuộn băng keo điện",
                    "item_code_span": None,
                    "description_span": "băng keo điện",
                    "quantity_span": "2",
                    "unit_span": "cuộn",
                    "need_by_span": None,
                }
            ],
        }
    )
    verdict = read_pr_words(words, answer, received_on=world_day(), default_currency="VND")
    # A PR number or department the model gives is not the words' to decide.
    assert verdict.draft is not None and verdict.draft.currency == "VND"
    budget = answer.model_copy(update={"budget_code_span": "CC-9"})
    assert read_pr_words(
        words, budget, received_on=world_day(), default_currency="VND"
    ).not_read == ("span_not_found")


def world_day() -> Any:
    from datetime import date

    return date(2026, 11, 2)


def test_the_prompt_file_is_the_one_the_step_names() -> None:
    path = REPO / "configs/prompts/purchasing" / f"pr_from_words@{PR_FROM_WORDS.version}.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert (raw["prompt_id"], raw["version"]) == (PR_FROM_WORDS.prompt_id, PR_FROM_WORDS.version)
    assert raw["variables"] == ["words"]


async def test_whoever_asked_is_a_maker_even_when_another_received_it() -> None:
    world = _world()
    case = await world.service.case(_requester(), await _sent(world))
    # A request a buyer received on someone's behalf still names who asked.
    received_by_buyer = case.model_copy(update={"received_by": uuid.UUID(int=0xB0B)})
    assert HOA in received_by_buyer.makers

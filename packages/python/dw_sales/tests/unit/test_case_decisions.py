"""A flag decided in the case's conversation (ticket 56): DW1 says back exactly
what it would record, and records it only when the PIC confirms that
statement's hash, on that case, at that version, through the page's own
command. Nothing a model writes names the case or the flag."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dw_kernel.errors import ConflictError, NotFoundError
from dw_sales.application.chat_prompts import QUESTION_INTENT
from dw_sales.domain.assistant import CaseKey, QuestionKind
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import DispositionKind, FindingCode, OrderCase
from dw_sales.evals.graders import AN, CALLERS, DIEU, OUTSIDER, READER
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.world import BETA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
SHORT = FindingCode.REQUESTED_DATE_SHORT_LT.value


class Reader(Recorded):
    """Reads every question as ``reading``, and keeps the FLAGS it was shown."""

    def __init__(self, reading: dict[str, Any]) -> None:
        super().__init__(raw={})
        self.reading = reading
        self.flags: list[Any] = []

    async def interpret(self, prompt: Any, inputs: Any, schema: Any, **kwargs: Any) -> Any:
        self.calls.append((prompt, kwargs["run"], inputs))
        if prompt == QUESTION_INTENT:
            self.flags.append(json.loads(inputs["flags"]))
            return schema.model_validate(self.reading)
        return schema.model_validate({"answer": "x"})


def _accept(reason: str | None = "khách đã đồng ý lead time") -> dict[str, Any]:
    return {
        "kind": "decide_finding",
        "finding_code": SHORT,
        "decision": "accepted",
        "reason": reason,
    }


async def _m06(reading: dict[str, Any]) -> tuple[World, Reader, OrderCase, CaseKey]:
    """M06: its line 3 is requested before its lead time allows."""
    model = Reader(reading)
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS, model=model, measured=False)
    ((_, case),) = (await world.process_each(AN, ["M06"])).values()
    assert isinstance(case, OrderCase)
    return world, model, world.order(case.case_id), CaseKey(CaseKind.ORDER, case.case_id)


def _short(case: OrderCase) -> Any:
    return next(f for f in case.findings if f.code.value == SHORT)


async def test_a_decision_is_said_back_and_recorded_only_once_confirmed() -> None:
    world, model, case, key = await _m06(_accept())
    turn = (await world.services.assistant.ask(AN.context(), "chấp nhận cờ ngày giao", key)).turn
    assert turn.kind is QuestionKind.DECIDE_FINDING
    proposal = turn.proposal
    assert proposal is not None
    assert proposal.finding_key == _short(case).key and proposal.decision == "accepted"
    assert proposal.case_version == case.case_version
    # The model was shown the case's open flags, codes and lines only.
    assert {"code": SHORT, "line": 3} in model.flags[-1]
    # Said, not done.
    assert _short(world.order(case.case_id)).disposition.kind is DispositionKind.OPEN
    done = await world.services.assistant.confirm(
        AN.context(), key, turn.seq, proposal.content_hash
    )
    after = world.order(case.case_id)
    decided = _short(after).disposition
    assert decided.kind is DispositionKind.ACCEPTED
    assert decided.by == AN.user_id and decided.reason == "khách đã đồng ý lead time"
    assert done.case_version == after.case_version == case.case_version + 1
    # Confirming again finds the case moved on: nothing is recorded twice.
    with pytest.raises(ConflictError):
        await world.services.assistant.confirm(AN.context(), key, turn.seq, proposal.content_hash)


async def test_a_hash_not_the_statements_records_nothing() -> None:
    world, _, case, key = await _m06(_accept())
    turn = (await world.services.assistant.ask(AN.context(), "chấp nhận", key)).turn
    assert turn.proposal is not None
    with pytest.raises(ConflictError):
        await world.services.assistant.confirm(AN.context(), key, turn.seq, "0" * 64)
    assert _short(world.order(case.case_id)).disposition.kind is DispositionKind.OPEN


async def test_a_case_that_moved_since_the_statement_records_nothing() -> None:
    world, _, case, key = await _m06(_accept())
    turn = (await world.services.assistant.ask(AN.context(), "chấp nhận", key)).turn
    assert turn.proposal is not None
    # The page's button decides it first.
    await world.services.order_commands.dispose(
        AN.context(),
        case.case_id,
        _short(case).key,
        case_version=case.case_version,
        disposition="accepted",
        reason="PIC chấp nhận trên trang",
    )
    with pytest.raises(ConflictError):
        await world.services.assistant.confirm(
            AN.context(), key, turn.seq, turn.proposal.content_hash
        )
    decided = _short(world.order(case.case_id)).disposition
    assert decided.kind is DispositionKind.ACCEPTED
    assert getattr(decided, "reason", None) == "PIC chấp nhận trên trang"


async def test_a_flag_the_case_does_not_hold_open_asks_which_and_states_nothing() -> None:
    world, _, _, key = await _m06(
        {
            "kind": "decide_finding",
            "finding_code": "price_mismatch",
            "decision": "accepted",
            "reason": "ok",
        }
    )
    turn = (await world.services.assistant.ask(AN.context(), "chấp nhận cờ giá", key)).turn
    assert turn.proposal is None
    assert SHORT in turn.answer


async def test_accepting_without_a_reason_asks_for_one() -> None:
    world, _, _, key = await _m06(_accept(reason=None))
    turn = (await world.services.assistant.ask(AN.context(), "chấp nhận cờ ngày giao", key)).turn
    assert turn.proposal is None and "lý do" in turn.answer


async def test_a_reader_who_may_not_decide_is_stated_nothing() -> None:
    world, _, _, key = await _m06(_accept())
    turn = (await world.services.assistant.ask(READER.context(), "chấp nhận", key)).turn
    assert turn.proposal is None


async def test_another_persons_turn_cannot_be_confirmed() -> None:
    world, _, case, key = await _m06(_accept())
    turn = (await world.services.assistant.ask(AN.context(), "chấp nhận", key)).turn
    assert turn.proposal is not None
    with pytest.raises(NotFoundError):
        await world.services.assistant.confirm(
            DIEU.context(), key, turn.seq, turn.proposal.content_hash
        )
    assert _short(world.order(case.case_id)).disposition.kind is DispositionKind.OPEN


async def test_a_turn_confirmed_on_another_cases_route_is_not_found() -> None:
    """Acceptance 2: no confirmation reaches another case, whatever the route names."""
    world, _, case, key = await _m06(_accept())
    turn = (await world.services.assistant.ask(AN.context(), "chấp nhận", key)).turn
    assert turn.proposal is not None
    seen = await world.process_each(AN, ["M01"])
    ((_, other),) = seen.values()
    assert other is not None and other.case_id != case.case_id
    other_key = CaseKey(CaseKind.ORDER, other.case_id)
    with pytest.raises(NotFoundError):
        await world.services.assistant.confirm(
            AN.context(), other_key, turn.seq, turn.proposal.content_hash
        )
    assert _short(world.order(case.case_id)).disposition.kind is DispositionKind.OPEN


async def test_in_the_general_conversation_a_decision_is_only_pointed_to_its_case() -> None:
    world, _, case, _ = await _m06(_accept())
    view = await world.services.assistant.ask(AN.context(), "chấp nhận cờ ngày giao")
    assert view.turn.proposal is None
    assert _short(world.order(case.case_id)).disposition.kind is DispositionKind.OPEN


async def test_another_tenant_naming_the_case_and_turn_finds_nothing() -> None:
    world, _, case, key = await _m06(_accept())
    turn = (await world.services.assistant.ask(AN.context(), "chấp nhận", key)).turn
    assert turn.proposal is not None
    with pytest.raises(NotFoundError):
        await world.services.assistant.confirm(
            OUTSIDER.context(BETA), key, turn.seq, turn.proposal.content_hash
        )
    assert _short(world.order(case.case_id)).disposition.kind is DispositionKind.OPEN


async def test_another_po_named_in_this_cases_conversation_is_not_decided_here() -> None:
    """A PIC naming another PO's flag in this case's chat: DW1 points
    elsewhere and states nothing, rather than decide this case's flag."""
    world, _, case, key = await _m06({**_accept(), "reference": "NRV-PO-26-0457"})
    turn = (
        await world.services.assistant.ask(
            AN.context(), "chấp nhận cờ ngày giao của PO NRV-PO-26-0457", key
        )
    ).turn
    assert turn.proposal is None
    assert _short(world.order(case.case_id)).disposition.kind is DispositionKind.OPEN

"""An SO line's value asked for in the case's conversation (ticket 56 over 53):
DW1 says back exactly what it would propose writing into Bravo, and opens
the write's approval only when the PIC confirms that statement's hash, on
that case, at that version, through ticket 53's own proposal. Nothing a
model writes names the case, the SO or the row, and nothing reaches Bravo
from the chat."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_platform.application.access_context import AccessContext
from dw_sales.adapters.bravo_contract import BravoContract
from dw_sales.application.access import SalesScopes
from dw_sales.application.bravo_line_writes import CANCEL_REASON_CHARS, BravoSo, BravoSoLine
from dw_sales.application.chat_prompts import QUESTION_INTENT
from dw_sales.domain.assistant import CaseKey, ProposedBravoWrite, QuestionKind
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import OrderCase
from dw_sales.evals.graders import AN, CALLERS, OUTSIDER
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.world import ALPHA, BETA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
SO_NO = "SO26-1001"
SO_UUID = uuid.UUID("00000000-0000-4000-8000-000000000071")


def _fields(proposal: ProposedBravoWrite) -> dict[str, Any]:
    return {f: getattr(proposal, f) for f in proposal.__slots__}


class Reader(Recorded):
    """Reads every question as ``reading``."""

    def __init__(self, reading: dict[str, Any]) -> None:
        super().__init__(raw={})
        self.reading = reading

    async def interpret(self, prompt: Any, inputs: Any, schema: Any, **kwargs: Any) -> Any:
        self.calls.append((prompt, kwargs["run"], inputs))
        if prompt == QUESTION_INTENT:
            return schema.model_validate(self.reading)
        return schema.model_validate({"answer": "x"})


class Bravo:
    """The SO as the gateway reads it: one Bravo row per PO line."""

    def __init__(self, lines: int) -> None:
        self.read = 0
        self.so = BravoSo(
            so_id=10,
            so_no=SO_NO,
            lines=tuple(
                BravoSoLine(
                    20 + n, n, f"PRV-{n}", Decimal(100), date(2026, 12, 1), f"0x{n:016X}", ""
                )
                for n in range(1, lines + 1)
            ),
            target="uat",
        )

    async def sales_order(self, tenant_id: object, so_no: str) -> BravoSo | None:
        self.read += 1
        return self.so if so_no == SO_NO else None


def _write(line: int = 1, field: str = "confirmed_date", value: str = "2026-12-08") -> Any:
    return {"kind": "propose_bravo_write", "line_no": line, "field": field, "new_value": value}


def _writer(context: AccessContext) -> AccessContext:
    """The PIC as the platform's `sales_pic` role holds it since ticket 53."""
    return context.model_copy(update={"scopes": context.scopes | {SalesScopes.BRAVO_WRITE.value}})


async def _uploaded(
    reading: dict[str, Any], *, connected: bool = True
) -> tuple[World, Bravo, OrderCase, CaseKey]:
    """M06, its flags decided, entered in Bravo as SO26-1001."""
    bravo = Bravo(lines=9)
    world = open_world(
        REPO,
        SampleSet.of(REPO, None),
        CALLERS,
        model=Reader(reading),
        measured=False,
        bravo_orders=bravo if connected else None,
        bravo_commands=BravoContract() if connected else None,
    )
    ((_, case),) = (await world.process_each(AN, ["M06"])).values()
    assert isinstance(case, OrderCase)
    for finding in world.order(case.case_id).findings:
        if finding.disposition.kind.value == "open":
            await world.services.order_commands.dispose(
                AN.context(),
                case.case_id,
                finding.key,
                case_version=world.order(case.case_id).case_version,
                disposition="accepted",
                reason="đã xem",
            )
    uploaded = await world.walk_to_uploaded(AN, case.case_id)
    assert uploaded.bravo_so_no == SO_NO
    return world, bravo, uploaded, CaseKey(CaseKind.ORDER, case.case_id)


def _writes(world: World) -> list[Any]:
    return list(world.store.state(ALPHA).bravo_writes.values())


async def _ask(
    world: World, key: CaseKey, question: str = "đổi ngày XN dòng 1 thành 08/12/2026"
) -> Any:
    return (await world.services.assistant.ask(_writer(AN.context()), question, key)).turn


async def test_a_write_is_said_back_and_proposed_only_once_confirmed() -> None:
    world, bravo, case, key = await _uploaded(_write())
    turn = await _ask(world, key)
    assert turn.kind is QuestionKind.PROPOSE_BRAVO_WRITE
    proposal = turn.proposal
    assert proposal is not None and proposal.action == "bravo_write"
    assert (proposal.line_no, proposal.field, proposal.value) == (1, "confirmed_date", "2026-12-08")
    assert proposal.case_version == case.case_version
    assert SO_NO in turn.answer and "08/12/2026" in turn.answer
    # Said, not done: nothing proposed, Bravo not even read.
    assert _writes(world) == [] and bravo.read == 0
    done = await world.services.assistant.confirm(
        _writer(AN.context()), key, turn.seq, proposal.content_hash
    )
    (write,) = _writes(world)
    assert (write.line_no, write.field, write.after) == (1, "confirmed_date", "2026-12-08")
    assert write.proposed_by == AN.user_id and write.status == "proposed"
    assert done.case_version == case.case_version
    # Confirming again: the line already has an open proposal.
    with pytest.raises(ConflictError):
        await world.services.assistant.confirm(
            _writer(AN.context()), key, turn.seq, proposal.content_hash
        )
    assert len(_writes(world)) == 1


async def test_a_quantity_is_said_back_as_a_plain_number() -> None:
    world, _, _, key = await _uploaded(_write(line=2, field="quantity", value="1200.0"))
    turn = await _ask(world, key, "số lượng dòng 2 là 1.200")
    assert turn.proposal is not None and turn.proposal.action == "bravo_write"
    assert turn.proposal.value == "1200"


async def test_a_hash_not_the_statements_proposes_nothing() -> None:
    world, _, _, key = await _uploaded(_write())
    turn = await _ask(world, key)
    with pytest.raises(ConflictError):
        await world.services.assistant.confirm(_writer(AN.context()), key, turn.seq, "0" * 64)
    assert _writes(world) == []


@pytest.mark.parametrize(
    ("reading", "asks"),
    [
        (_write(line=99), "dòng nào"),
        ({**_write(), "line_no": None}, "dòng nào"),
        ({**_write(), "field": None}, "hay hủy dòng"),
        (_write(value="08/12/2026"), "chưa đọc được"),
        (_write(field="quantity", value="0"), "chưa đọc được"),
        (_write(field="quantity", value="1.23456"), "chưa đọc được"),
        (_write(field="quantity", value="NaN"), "chưa đọc được"),
        ({**_write(), "new_value": None}, "chưa đọc được"),
    ],
)
async def test_what_code_cannot_take_exactly_asks_one_question_and_states_nothing(
    reading: dict[str, Any], asks: str
) -> None:
    world, _, _, key = await _uploaded(reading)
    turn = await _ask(world, key)
    assert turn.proposal is None and asks in turn.answer
    assert _writes(world) == []


async def test_another_po_named_in_this_cases_chat_states_nothing() -> None:
    world, _, _, key = await _uploaded({**_write(), "reference": "PO-KHAC-99"})
    turn = await _ask(world, key, "đổi ngày XN dòng 1 của PO-KHAC-99 thành 08/12/2026")
    assert turn.proposal is None and _writes(world) == []


async def test_someone_without_the_write_right_is_stated_nothing() -> None:
    world, _, _, key = await _uploaded(_write())
    turn = (await world.services.assistant.ask(AN.context(), "đổi ngày XN dòng 1", key)).turn
    assert turn.proposal is None and _writes(world) == []


async def test_an_order_with_no_so_yet_says_so() -> None:
    bravo_less = open_world(
        REPO, SampleSet.of(REPO, None), CALLERS, model=Reader(_write()), measured=False
    )
    ((_, case),) = (await bravo_less.process_each(AN, ["M06"])).values()
    assert isinstance(case, OrderCase)
    turn = await _ask(bravo_less, CaseKey(CaseKind.ORDER, case.case_id))
    assert turn.proposal is None and "chưa có số SO" in turn.answer


async def test_bravo_unreachable_at_confirmation_proposes_nothing() -> None:
    world, _, _, key = await _uploaded(_write(), connected=False)
    turn = await _ask(world, key)
    assert turn.proposal is not None
    with pytest.raises(ConflictError):
        await world.services.assistant.confirm(
            _writer(AN.context()), key, turn.seq, turn.proposal.content_hash
        )
    assert _writes(world) == []


async def test_the_right_is_checked_again_where_the_write_is_proposed() -> None:
    world, _, _, key = await _uploaded(_write())
    turn = await _ask(world, key)
    assert turn.proposal is not None
    # Stated to a writer; confirmed by the same person after losing the right.
    with pytest.raises(PermissionDeniedError):
        await world.services.assistant.confirm(
            AN.context(), key, turn.seq, turn.proposal.content_hash
        )
    assert _writes(world) == []


async def test_another_tenant_confirming_the_turn_finds_nothing() -> None:
    world, _, _, key = await _uploaded(_write())
    turn = await _ask(world, key)
    assert turn.proposal is not None
    with pytest.raises(NotFoundError):
        await world.services.assistant.confirm(
            _writer(OUTSIDER.context(BETA)), key, turn.seq, turn.proposal.content_hash
        )
    assert _writes(world) == []


# ------------------------------------------------------- a cancel (ticket 71)


def _cancel(line: int = 2, reason: str | None = "khách bỏ dòng") -> Any:
    return {"kind": "propose_bravo_write", "line_no": line, "field": "cancel", "reason": reason}


async def test_a_cancel_is_said_back_with_its_reason_and_proposed_only_once_confirmed() -> None:
    world, bravo, case, key = await _uploaded(_cancel(reason="  khách   bỏ dòng "))
    turn = await _ask(world, key, "hủy dòng 2 vì khách bỏ dòng")
    proposal = turn.proposal
    assert proposal is not None and proposal.action == "bravo_write"
    # Collapsed as the page's body is (`cancel_reason`): one rule, one owner.
    assert (proposal.line_no, proposal.field, proposal.value) == (2, "cancel", "khách bỏ dòng")
    assert SO_NO in turn.answer and "khách bỏ dòng" in turn.answer
    assert _writes(world) == [] and bravo.read == 0
    done = await world.services.assistant.confirm(
        _writer(AN.context()), key, turn.seq, proposal.content_hash
    )
    (write,) = _writes(world)
    assert (write.line_no, write.field, write.after) == (2, "cancel", "Hủy: khách bỏ dòng")
    assert write.kind == "so.line.cancel@1" and write.status == "proposed"
    assert "hủy dòng 2" in done.answer and done.case_version == case.case_version


async def test_a_turn_proposes_once_even_after_its_proposal_is_rejected() -> None:
    # A proposal leaves the case's version as it is, and the one-open rule
    # lapses once the first proposal is settled: the turn itself is spent.
    world, _, _, key = await _uploaded(_cancel(reason="khách bỏ dòng"))
    turn = await _ask(world, key, "hủy dòng 2 vì khách bỏ dòng")
    assert turn.proposal is not None
    await world.services.assistant.confirm(
        _writer(AN.context()), key, turn.seq, turn.proposal.content_hash
    )
    held = world.store.state(ALPHA).bravo_writes
    ((approval_id, first),) = held.items()
    held[approval_id] = first.model_copy(
        update={"status": "rejected", "decided_by": AN.user_id, "settled_at": first.proposed_at}
    )

    with pytest.raises(ConflictError) as refused:
        await world.services.assistant.confirm(
            _writer(AN.context()), key, turn.seq, turn.proposal.content_hash
        )

    assert refused.value.details["rule"] == "already_proposed"
    assert [w.status for w in _writes(world)] == ["rejected"]
    # A new statement of the same cancel is a new turn, and proposes.
    again = await _ask(world, key, "hủy dòng 2 vì khách bỏ dòng")
    assert again.proposal is not None
    await world.services.assistant.confirm(
        _writer(AN.context()), key, again.seq, again.proposal.content_hash
    )
    assert sorted(w.status for w in _writes(world)) == ["proposed", "rejected"]


async def test_a_question_the_case_chat_does_not_take_is_told_it_can_cancel_a_line() -> None:
    # A feature nobody is told about is not there: the case's own catalog,
    # said when a question is out of scope, names the cancel (copy 1.6.0).
    world, _, _, key = await _uploaded({"kind": "out_of_scope"})
    turn = await _ask(world, key, "thời tiết hôm nay thế nào")
    assert turn.proposal is None and "hủy một dòng SO" in turn.answer


@pytest.mark.parametrize(
    ("reason", "asks"),
    [
        (None, "cần một lý do"),
        ("   ", "cần một lý do"),
        ("x" * (CANCEL_REASON_CHARS + 1), f"tối đa {CANCEL_REASON_CHARS} ký tự"),
    ],
    ids=["no_reason", "blank_reason", "too_long"],
)
async def test_a_cancel_code_cannot_take_asks_for_its_reason_and_states_nothing(
    reason: str | None, asks: str
) -> None:
    world, _, _, key = await _uploaded(_cancel(reason=reason))
    turn = await _ask(world, key, "hủy dòng 2")
    assert turn.proposal is None and asks in turn.answer
    assert _writes(world) == []


async def test_a_cancel_reason_is_measured_once_its_spaces_are_collapsed() -> None:
    padded = "  " + "x" * CANCEL_REASON_CHARS + "  "
    world, _, _, key = await _uploaded(_cancel(reason=padded))
    turn = await _ask(world, key, "hủy dòng 2")
    assert turn.proposal is not None and turn.proposal.value == "x" * CANCEL_REASON_CHARS


async def test_the_right_is_checked_again_where_a_cancel_is_proposed() -> None:
    world, _, _, key = await _uploaded(_cancel())
    turn = await _ask(world, key, "hủy dòng 2 vì khách bỏ dòng")
    assert turn.proposal is not None
    with pytest.raises(PermissionDeniedError):
        await world.services.assistant.confirm(
            AN.context(), key, turn.seq, turn.proposal.content_hash
        )
    assert _writes(world) == []


def test_a_stated_cancel_binds_its_reason_and_reads_back_from_storage() -> None:
    stated = ProposedBravoWrite(
        case_kind=CaseKind.ORDER,
        case_id=SO_UUID,
        case_version=4,
        line_no=2,
        field="cancel",
        value="khách bỏ dòng",
        prompt="sales.question_intent@1.6.0",
    )
    other = ProposedBravoWrite(**{**_fields(stated), "value": "khách đổi ý"})
    # A confirmation of another reason's hash proposes nothing.
    assert stated.content_hash != other.content_hash
    assert ProposedBravoWrite.from_stored(stated.stored()) == stated
